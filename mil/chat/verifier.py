"""
mil/chat/verifier.py — MIL-42.

Post-synthesis verifier. Two-stage:

  1. In-code: every citation id must resolve to an Evidence item.
     Every quote must appear verbatim in some Evidence.text.
     Cheap, deterministic, runs first.

  2. LLM (Haiku via `ask_verifier`): one short prompt that asks whether
     any numeric claim or factual assertion in the answer is unsupported
     by the evidence bundle. Tripped only if stage 1 passes.

Violations accumulate in VerificationResult.violations. The orchestrator
either retries synthesis (once) or raises a FABRICATION_GUARD refusal.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from datetime import datetime, timezone

from mil.chat.retrievers.base import EvidenceBundle
from mil.chat.synthesis import SynthesisResult, _format_evidence_block
from mil.config.model_client import call_anthropic

logger = logging.getLogger(__name__)

_VERIFIER_SYSTEM = (
    "You audit draft answers produced by the Ask CJI Pro synthesiser. "
    "Given an answer and the evidence it was drawn from, decide whether every "
    "numeric claim, ranking, and factual assertion in the answer is supported "
    "by the evidence.\n\n"
    "The evidence is presented with a metadata header line (severity, rating, "
    "competitor, issue_type, journey_id, date, ...) followed by the raw text "
    "body. METADATA HEADERS ARE AUTHORITATIVE — if the header says "
    "`severity=P0` then an answer claim that the item is P0 IS supported. "
    "Do NOT flag claims that are grounded in the metadata header.\n\n"
    "Return strict JSON: "
    '{"supported": true|false, "violations": ["<short description>", ...]}. '
    "If supported, return violations: []. Do not add prose outside the JSON."
)

_CITATION_RE = re.compile(r"\[([^\[\]]+?)\]")


@dataclass
class VerificationResult:
    passed: bool
    violations: list[str] = field(default_factory=list)


def _check_citations_resolve(result: SynthesisResult, evidence: EvidenceBundle) -> list[str]:
    known = {ev.id for ev in evidence.items}
    violations: list[str] = []

    for cid in _CITATION_RE.findall(result.answer):
        for part in cid.split(","):
            part = part.strip()
            if part and part not in known:
                violations.append(f"citation '[{part}]' does not resolve to any evidence id")

    for cid in result.citations:
        if cid not in known:
            violations.append(f"declared citation '{cid}' does not resolve to any evidence id")

    return violations


_SMART_CHARS = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",  # single quotes
    "“": '"', "”": '"', "„": '"', "‟": '"',  # double quotes
    "–": "-", "—": "-", "―": "-",                  # dashes
    "…": "...", " ": " ",                               # ellipsis, nbsp
}


def _normalise(text: str) -> str:
    for src, dst in _SMART_CHARS.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def _check_quotes_verbatim(result: SynthesisResult, evidence: EvidenceBundle) -> list[str]:
    corpus = _normalise("\n".join(ev.text for ev in evidence.items))
    violations: list[str] = []
    for q in result.quotes:
        q_clean = _normalise(q.strip().strip('"').strip("'"))
        if len(q_clean) < 12:
            continue
        if q_clean not in corpus:
            violations.append(f"quote not found verbatim in evidence: {q_clean[:60]!r}")
    return violations


def _llm_support_check(result: SynthesisResult, evidence: EvidenceBundle) -> list[str]:
    if not result.answer.strip():
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    evidence_text = _format_evidence_block(evidence, max_items=15)

    user_prompt = (
        f"TODAY'S DATE: {today} (use this when judging 'future date' claims).\n\n"
        f"DRAFT ANSWER:\n{result.answer}\n\n"
        f"EVIDENCE:\n{evidence_text}\n\n"
        "Audit the answer. Return JSON only."
    )

    try:
        raw = call_anthropic(
            task="ask_verifier",
            system=_VERIFIER_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=256,
        )
    except Exception as exc:
        logger.warning("[verifier] LLM check skipped: %s", exc)
        return []

    import json
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    if parsed.get("supported") is False:
        violations = parsed.get("violations") or []
        return [str(v) for v in violations if v][:5]
    return []


def verify(result: SynthesisResult, evidence: EvidenceBundle) -> VerificationResult:
    """Run the two-stage audit. Stage 2 only runs if stage 1 passes."""
    violations: list[str] = []
    violations.extend(_check_citations_resolve(result, evidence))
    violations.extend(_check_quotes_verbatim(result, evidence))

    if not violations:
        violations.extend(_llm_support_check(result, evidence))

    return VerificationResult(passed=not violations, violations=violations)
