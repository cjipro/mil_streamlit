"""
mil/chat/pipeline.py — Ask CJI Pro orchestrator.

Chains: guardrail → cache → classify → retrieve → synthesise → verify → audit.

Single entry point: ask(query) -> AskResponse. Used by the Streamlit page
and any CLI / programmatic caller.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from mil.chat import audit, cache, refusals
from mil.chat.intent import Intent, IntentResult, classify, dispatch_plan
from mil.chat.refusals import RefusalClass
from mil.chat.retrievers.base import EvidenceBundle, Retriever
from mil.chat.retrievers.bm25 import BM25Retriever
from mil.chat.retrievers.embedding import EmbeddingRetriever
from mil.chat.retrievers.sql import SQLRetriever
from mil.chat.retrievers.status import StatusRetriever
from mil.chat.retrievers.structured import StructuredRetriever
from mil.chat.synthesis import Confidence, SynthesisResult, synthesise
from mil.chat.verifier import verify

logger = logging.getLogger(__name__)


# Single registry — name → Retriever instance. Built once per process.
_RETRIEVERS: dict[str, Retriever] = {
    "structured": StructuredRetriever(),
    "bm25":       BM25Retriever(),
    "embedding":  EmbeddingRetriever(),
    "sql":        SQLRetriever(),
    "status":     StatusRetriever(),
}


@dataclass
class AskResponse:
    trace_id: str
    answer: str
    confidence: str
    citations: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    chart_hint: Optional[str] = None
    refusal: Optional[str] = None
    intent: str = ""
    retrievers_used: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    verifier_violations: list[str] = field(default_factory=list)
    latency_ms: int = 0
    cache_hit: bool = False
    model_used: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # `response` alias for the briefing chat widget baked into publish.py
        # (it reads data.response, not data.answer). Keep both so the modern
        # UI keeps working and the legacy briefing popup doesn't show
        # "No response from Sonar." on every query.
        d["response"] = self.answer
        return d


def _refuse(trace_id: str, intent: str, cls: RefusalClass, query: str,
            detail: str = "", latency_ms: int = 0,
            partner_id: Optional[str] = None) -> AskResponse:
    r = refusals.build_refusal(cls, query, detail)
    response = AskResponse(
        trace_id=trace_id,
        answer=r.message,
        confidence=Confidence.UNKNOWN.value,
        refusal=cls.value,
        intent=intent,
        latency_ms=latency_ms,
    )
    audit.log(audit.AuditEntry(
        trace_id=trace_id, query=query, intent=intent,
        refusal_class=cls.value, latency_ms=latency_ms,
        partner_id=partner_id,
    ))
    return response


def _retrieve_all(names: list[str], query: str, entities: dict, k_each: int) -> EvidenceBundle:
    bundle = EvidenceBundle(query=query, retriever_chain=list(names))
    seen: set[str] = set()
    for name in names:
        retriever = _RETRIEVERS.get(name)
        if retriever is None:
            logger.warning("[pipeline] no retriever registered for %s", name)
            continue
        try:
            sub = retriever.retrieve(query, entities, k=k_each)
        except Exception as exc:
            logger.warning("[pipeline] retriever %s failed: %s", name, exc)
            continue
        for ev in sub.items:
            if ev.id in seen:
                continue
            seen.add(ev.id)
            bundle.add(ev)
        bundle.total_candidates += sub.total_candidates
    return bundle


def ask(query: str, deep: bool = False, k_each: int = 8,
        partner_id: Optional[str] = None) -> AskResponse:
    """
    Full pipeline for an /ask query.

    Args:
        query:       user question.
        deep:        route synthesis to Opus (ask_synthesis_deep). Defaults to Sonnet.
        k_each:      top-k items requested from each retriever.
        partner_id:  upstream-verified identity (e.g. Cloudflare Access email)
                     stamped into the audit log for attribution.
    """
    started = time.monotonic()
    trace_id = uuid.uuid4().hex[:10]
    query = (query or "").strip()

    if not query:
        return _refuse(trace_id, "", RefusalClass.INSUFFICIENT_EVIDENCE, query,
                       detail="Empty query.", partner_id=partner_id)

    # ── 1. Local scope guard (deterministic, runs before any LLM call) ───
    if refusals.check_logic_probe(query):
        return _refuse(trace_id, "pre_classify", RefusalClass.LOGIC_PROBE, query,
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)
    if refusals.check_pii(query):
        return _refuse(trace_id, "pre_classify", RefusalClass.PII, query,
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)

    # ── 2. Intent classification (Haiku) ──────────────────────────────────
    try:
        ir: IntentResult = classify(query)
    except Exception as exc:
        logger.warning("[pipeline] classify failed: %s", exc)
        return _refuse(trace_id, "unknown", RefusalClass.OUT_OF_SCOPE, query,
                       detail="Intent classification unavailable.",
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)

    intent = ir.intent

    if intent == Intent.OUT_OF_SCOPE:
        return _refuse(trace_id, intent.value, RefusalClass.OUT_OF_SCOPE, query,
                       detail=str(ir.entities.get("reason") or ""),
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)
    if intent == Intent.INSUFFICIENT:
        return _refuse(trace_id, intent.value, RefusalClass.INSUFFICIENT_EVIDENCE, query,
                       detail=str(ir.entities.get("reason") or ""),
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)
    if intent == Intent.UNKNOWN:
        return _refuse(trace_id, intent.value, RefusalClass.OUT_OF_SCOPE, query,
                       detail="Could not classify the query.",
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)

    # Enrich entities with the intent so SQLRetriever can branch on it.
    entities = {**ir.entities, "_intent": intent.value}

    # ── 3. Cache lookup ───────────────────────────────────────────────────
    ckey = cache.key_for(query, intent.value, entities)
    hit = cache.get(ckey)
    if hit:
        latency_ms = int((time.monotonic() - started) * 1000)
        response = AskResponse(**hit, trace_id=trace_id, cache_hit=True, latency_ms=latency_ms)
        audit.log(audit.AuditEntry(
            trace_id=trace_id, query=query, intent=intent.value,
            retrievers_hit=response.retrievers_used,
            evidence_ids=response.citations,
            confidence=response.confidence,
            model_used=response.model_used,
            cache_hit=True, latency_ms=latency_ms,
            partner_id=partner_id,
        ))
        return response

    # ── 4. Retrieval ──────────────────────────────────────────────────────
    retrievers = dispatch_plan(intent)
    bundle = _retrieve_all(retrievers, query, entities, k_each=k_each)

    if not bundle.items:
        return _refuse(trace_id, intent.value, RefusalClass.INSUFFICIENT_EVIDENCE, query,
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)

    # ── 5. Synthesis ──────────────────────────────────────────────────────
    try:
        syn: SynthesisResult = synthesise(query, bundle, deep=deep)
    except Exception as exc:
        logger.warning("[pipeline] synthesise failed: %s", exc)
        return _refuse(trace_id, intent.value, RefusalClass.INSUFFICIENT_EVIDENCE, query,
                       detail=f"Synthesis failed: {exc}",
                       latency_ms=int((time.monotonic() - started) * 1000),
                       partner_id=partner_id)

    # ── 6. Verification ───────────────────────────────────────────────────
    ver = verify(syn, bundle)
    if not ver.passed:
        logger.info("[pipeline] verifier violations: %s", ver.violations)

    # ── 7. Build response ─────────────────────────────────────────────────
    latency_ms = int((time.monotonic() - started) * 1000)
    evidence_brief = [
        {"id": ev.id, "source": ev.source, "score": ev.score,
         "text": ev.text[:300], "metadata": ev.metadata}
        for ev in bundle.items[:20]
    ]
    response = AskResponse(
        trace_id=trace_id,
        answer=syn.answer,
        confidence=syn.confidence.value if isinstance(syn.confidence, Confidence) else str(syn.confidence),
        citations=syn.citations,
        quotes=syn.quotes,
        chart_hint=syn.chart_hint,
        intent=intent.value,
        retrievers_used=retrievers,
        evidence=evidence_brief,
        verifier_violations=ver.violations,
        latency_ms=latency_ms,
        cache_hit=False,
        model_used=syn.model_used,
    )

    # ── 8. Cache + audit ──────────────────────────────────────────────────
    if ver.passed:
        cache.put(ckey, {k: v for k, v in response.to_dict().items()
                         if k not in ("trace_id", "latency_ms", "cache_hit")})

    audit.log(audit.AuditEntry(
        trace_id=trace_id, query=query, intent=intent.value,
        retrievers_hit=retrievers,
        evidence_ids=syn.citations,
        confidence=response.confidence,
        model_used=syn.model_used,
        cache_hit=False,
        latency_ms=latency_ms,
        partner_id=partner_id,
    ))
    return response


if __name__ == "__main__":
    import argparse
    import json as _json
    import logging as _logging
    _logging.basicConfig(level=_logging.WARNING)
    parser = argparse.ArgumentParser(description="Ask CJI Pro — pipeline smoke test")
    parser.add_argument("query")
    parser.add_argument("--deep", action="store_true")
    args = parser.parse_args()
    r = ask(args.query, deep=args.deep)
    print(_json.dumps(r.to_dict(), indent=2, default=str))
