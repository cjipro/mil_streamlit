"""
mil/chat/rerank.py — MIL-182.

Cross-encoder reranking stage for the Ask CJI Pro retrieval pipeline.

Why: `_retrieve_all` merges candidates from four retrievers (BM25 normalised
0–1, embedding cosine, SQL hardcoded 0.9, structured) whose scores are NOT
comparable, then synthesis takes the first N items in list order. This stage
re-scores every merged candidate against the query with a single cross-encoder
so the items handed to synthesis share one comparable ordering — the 2026
production-RAG default (hybrid retrieve → cross-encoder rerank → top-k).

Fail-soft: if the cross-encoder can't load (sentence-transformers issue, no
model), the bundle is returned UNCHANGED — reranking is an enhancement, never a
hard dependency of answering. The CPU pin matches the rest of the stack.
"""
from __future__ import annotations

import logging
import math
from dataclasses import replace

from mil.chat.retrievers.base import EvidenceBundle
from mil.config.retrieval_models import EMBEDDING_DEVICE, RERANKER_MODEL

logger = logging.getLogger(__name__)

# Bound cross-encoder cost: rerank at most this many merged candidates.
_MAX_CANDIDATES = 40

_MODEL = None  # CrossEncoder, or False when unavailable


def _load_cross_encoder():
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info("[rerank] loading %s (device=%s)", RERANKER_MODEL, EMBEDDING_DEVICE)
            _MODEL = CrossEncoder(RERANKER_MODEL, device=EMBEDDING_DEVICE)
        except Exception as exc:
            logger.warning("[rerank] cross-encoder unavailable (%s) — passthrough", exc)
            _MODEL = False
    return _MODEL


def rerank(bundle: EvidenceBundle, top_n: int | None = None) -> EvidenceBundle:
    """Re-order bundle.items by cross-encoder relevance to bundle.query.

    Sets each item's `score` to the sigmoid-normalised cross-encoder score so
    the bundle now carries ONE comparable ordering (both list-order and
    score-sort agree). Optionally truncates to top_n. Returns the bundle
    unchanged if there is nothing to rerank or the model is unavailable.
    """
    if len(bundle.items) < 2:
        return bundle

    ce = _load_cross_encoder()
    if not ce:
        return bundle  # fail-soft passthrough

    items = bundle.items[:_MAX_CANDIDATES]
    overflow = bundle.items[_MAX_CANDIDATES:]  # left as-is, appended after ranked head

    try:
        scores = ce.predict([(bundle.query, ev.text) for ev in items])
    except Exception as exc:
        logger.warning("[rerank] predict failed (%s) — passthrough", exc)
        return bundle

    ranked = sorted(zip(items, scores), key=lambda t: float(t[1]), reverse=True)
    reordered = [
        replace(ev, score=round(1.0 / (1.0 + math.exp(-float(s))), 4))
        for ev, s in ranked
    ]
    reordered.extend(overflow)

    if top_n is not None:
        reordered = reordered[:top_n]

    bundle.items = reordered
    if "rerank" not in bundle.retriever_chain:
        bundle.retriever_chain = bundle.retriever_chain + ["rerank"]
    return bundle
