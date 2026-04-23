"""
mil/chat/synthesis.py — MIL-42.

Forced-citation synthesis. Consumes an EvidenceBundle + the original query
and produces a cited answer.

Hard rules enforced by the prompt:
  - Every factual claim cites >=1 Evidence id as [id].
  - Customer voice quoted VERBATIM — no paraphrasing.
  - Three-tag confidence: EVIDENCED / DIRECTIONAL / UNKNOWN.
  - Never imply internal knowledge (scope guard belongs in refusals.py).

Routes: ask_synthesis (Sonnet, default), ask_synthesis_deep (Opus, opt-in).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from mil.chat.retrievers.base import Evidence, EvidenceBundle
from mil.config.get_model import get_model
from mil.config.model_client import call_anthropic

logger = logging.getLogger(__name__)


class Confidence(str, Enum):
    EVIDENCED = "evidenced"
    DIRECTIONAL = "directional"
    UNKNOWN = "unknown"


@dataclass
class SynthesisResult:
    answer: str
    citations: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    chart_hint: Optional[str] = None
    model_used: str = ""


_SYSTEM_PROMPT = (
    "You are Ask CJI Pro — a banking market intelligence analyst talking to the "
    "Barclays product/risk team about their own app and their peers'. You have an "
    "EVIDENCE list of app reviews, CHRONICLE ledger entries (banking incidents), "
    "live findings (signal clusters), and benchmark aggregates. Ground every claim in it.\n\n"

    "WRITE LIKE AN ANALYST, NOT A DATABASE.\n"
    "- Lead with the answer. One or two plain sentences at the top. No 'the evidence\n"
    "  indicates…', no 'it is possible that…'.\n"
    "- Use the words a product manager uses: 'customers', 'complaints', 'reviews',\n"
    "  'most severe' or 'critical' (NOT 'P0 signals'), 'login journey', 'payment flow'.\n"
    "  If you must mention a severity class, translate: P0 = 'critical / blocking',\n"
    "  P1 = 'significant friction', P2 = 'minor'.\n"
    "- Say what IS there. Don't hedge with 'directional picture', 'characterises',\n"
    "  'composite metric', 'baseline'. Say 'login is in trouble' or 'complaints have\n"
    "  doubled this week'. Be direct.\n"
    "- Short paragraphs. No internal-sounding lists of IDs. If you need numbers,\n"
    "  name the metric in English: '36 critical complaints between 2–4 April', not\n"
    "  'volume of 36 P0 signals from Apr 2-4 2026'.\n"
    "- Never say: 'signal cluster', 'findings cluster', 'chronicle anchor cosine', 'CAC',\n"
    "  'J_LOGIN_01', 'MIL-F-...'. Translate instead: 'the login journey', 'one of the\n"
    "  live issue clusters', etc. Keep the raw id INSIDE the square-bracket citation\n"
    "  ONLY — never in the prose itself.\n"
    "- If there isn't a clean numeric answer (e.g. 'login score'), explain WHAT we\n"
    "  CAN say about it in everyday language, not what the database lacks.\n"
    "- Bottom-line sentence at the end when useful: 'Net: login is actively\n"
    "  degrading.' Skip if repetitive.\n\n"

    "STYLE EXAMPLE — BAD (robotic)\n"
    "  'The evidence does not contain a single composite login score metric for\n"
    "   Barclays. CHR-019 identifies a login regression incident with 36 P0 signals\n"
    "   across Apr 2–4 2026 [CHR-019]. This pattern has a low Chronicle Anchor\n"
    "   Cosine (CAC) of 0.126 [CHR-019].'\n\n"
    "STYLE EXAMPLE — GOOD (human)\n"
    "  'There's no single \"login score\" — but the picture isn't good. Between\n"
    "   2–4 April, 36 customers wrote critical reviews about being completely locked\n"
    "   out of the app [CHR-019]. It's a new pattern — we haven't seen it match any\n"
    "   prior incident in the ledger [CHR-019]. Two more live issue clusters have\n"
    "   kicked off since, both flagging the same root cause [MIL-F-20260421-006,\n"
    "   MIL-F-20260421-061]. Net: login is actively degrading.'\n\n"

    "HARD RULES (non-negotiable)\n"
    "1. Every factual claim ends with one or more [evidence_id] citations. The ids\n"
    "   are ugly (CHR-019, google_play_barclays_enriched#233) — that's fine, they live\n"
    "   inside the brackets only. The UI renders them differently.\n"
    "2. Quote customers VERBATIM. Never paraphrase a review. Put each verbatim quote\n"
    '   in the "quotes" list exactly as it appears. No ellipses, no edits.\n'
    "3. If the question can't be answered from the evidence, say so in plain English\n"
    '   and set confidence="unknown". Do not guess or fill the gap.\n'
    "4. Scope: public banking signals only. No internal telemetry, no PII.\n"
    "5. Return STRICT JSON — no markdown fences, no prose outside the JSON object.\n\n"

    "JSON CONTRACT — return EXACTLY this shape:\n"
    "{\n"
    '  "answer":     "<plain-English prose with [id] citations inline>",\n'
    '  "citations":  ["id1", "id2"],\n'
    '  "quotes":     ["<verbatim review text>", ...],\n'
    '  "confidence": "evidenced" | "directional" | "unknown",\n'
    '  "chart_hint": "trend" | "compare" | "heatmap" | "quote" | "peer_rank" | null\n'
    "}\n"
    "CITATION RULES: `citations` is a FLAT list of plain id strings. Never nested\n"
    '(not [["id"]]), never stringified (not "[\\"id\\"]"). `answer` is prose — never\n'
    "a nested JSON object.\n\n"

    "CONFIDENCE CALIBRATION\n"
    "- evidenced:   the evidence numerically answers the question.\n"
    "- directional: the evidence supports a pattern but doesn't confirm it.\n"
    "- unknown:     the evidence is insufficient or off-topic.\n"
)


_FRONT_KEYS = ("severity", "signal_severity", "finding_tier", "rating",
               "competitor", "issue_type", "p0_count", "p1_count",
               "journey_id", "date")


def _format_evidence_block(evidence: EvidenceBundle, max_items: int = 20) -> str:
    """
    Render each Evidence as a self-describing block the synthesiser can cite.
    High-signal metadata (severity, rating, competitor, issue_type) is hoisted
    into the first line so both the synthesiser AND the verifier see it
    alongside the body text.
    """
    lines: list[str] = []
    for ev in evidence.items[:max_items]:
        front_bits: list[str] = []
        for key in _FRONT_KEYS:
            val = ev.metadata.get(key)
            if val not in (None, "", 0):
                front_bits.append(f"{key}={val}")
        other = ", ".join(
            f"{k}={v}" for k, v in ev.metadata.items()
            if k not in _FRONT_KEYS and v not in (None, "")
        )
        body = ev.text.replace("\n", " ")
        if len(body) > 400:
            body = body[:400].rstrip() + "…"
        parts = [f"[{ev.id}] ({ev.source}, score={ev.score:.2f}) " + " · ".join(front_bits)]
        if other:
            parts.append(f"  meta: {other}")
        parts.append(f"  body: {body}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_response(text: str) -> Optional[dict]:
    parsed = _json_loads_any(text)
    if not isinstance(parsed, dict):
        return None

    # Sonnet occasionally double-wraps the contract: {"answer": "{...}"} where
    # the inner string is the real payload. Unwrap once if we detect it.
    inner = parsed.get("answer")
    if isinstance(inner, str) and inner.strip().startswith("{"):
        maybe = _json_loads_any(inner)
        if isinstance(maybe, dict) and "answer" in maybe:
            parsed = maybe

    return parsed


def _json_loads_any(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _coerce_confidence(v) -> Confidence:
    try:
        return Confidence(str(v).lower())
    except (ValueError, TypeError):
        return Confidence.UNKNOWN


def _normalise_citations(raw: object) -> list[str]:
    """Flatten nested arrays and strip accidental list-wrapping.

    Sonnet sometimes returns ``[["id1"], ["id2"]]`` or ``['["id1"]', '["id2"]']``
    instead of ``["id1", "id2"]``. This accepts all three shapes.
    """
    out: list[str] = []
    stack: list[object] = [raw] if raw is not None else []
    while stack:
        item = stack.pop(0)
        if item is None:
            continue
        if isinstance(item, list):
            stack = list(item) + stack
            continue
        s = str(item).strip()
        if s.startswith("[") and s.endswith("]"):
            # String that contains a JSON array → parse and recurse
            try:
                parsed = json.loads(s)
                stack = [parsed] + stack
                continue
            except json.JSONDecodeError:
                s = s.strip("[] \"'")
        s = s.strip("\"' ")
        if s and s not in out:
            out.append(s)
    return out


def synthesise(
    query: str,
    evidence: EvidenceBundle,
    deep: bool = False,
) -> SynthesisResult:
    """Generate a cited answer from an evidence bundle. deep=True routes to Opus."""
    task = "ask_synthesis_deep" if deep else "ask_synthesis"
    cfg = get_model(task)

    if not evidence.items:
        return SynthesisResult(
            answer="No evidence retrieved for that question.",
            confidence=Confidence.UNKNOWN,
            model_used=cfg["model"],
        )

    user_prompt = (
        f"QUESTION: {query}\n\n"
        f"EVIDENCE ({len(evidence.items)} items, "
        f"from {evidence.total_candidates} candidates retrieved by "
        f"{' + '.join(evidence.retriever_chain) or 'unknown'}):\n\n"
        f"{_format_evidence_block(evidence)}\n\n"
        "Respond with one JSON object following the contract."
    )

    raw = call_anthropic(
        task=task,
        system=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=cfg["max_tokens"],
        cache_system=True,
    )

    # Dump the last raw response for debugging stuck parses
    import os
    try:
        from pathlib import Path
        Path(__file__).parent.parent.joinpath("data", "ask_last_raw.txt").write_text(
            raw, encoding="utf-8"
        )
    except Exception:
        pass

    parsed = _parse_response(raw)
    if parsed is None:
        logger.warning("[synthesis] could not parse JSON — %r", raw[:400])
        return SynthesisResult(
            answer=raw.strip(),
            confidence=Confidence.UNKNOWN,
            model_used=cfg["model"],
        )

    citations = _normalise_citations(parsed.get("citations"))
    quotes = [str(q) for q in (parsed.get("quotes") or []) if q]

    return SynthesisResult(
        answer=str(parsed.get("answer") or "").strip(),
        citations=citations,
        quotes=quotes,
        confidence=_coerce_confidence(parsed.get("confidence")),
        chart_hint=parsed.get("chart_hint") or None,
        model_used=cfg["model"],
    )
