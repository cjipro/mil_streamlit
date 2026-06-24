"""
mil/chat/retrievers/embedding.py — MIL-41 / MIL-183.

Dense retriever over the enriched review corpus. Model name comes from
mil/config/retrieval_models.CHAT_EMBEDDING_MODEL (MIL-183: moved from the
2021-era all-MiniLM-L6-v2 to BGE-small-en-v1.5).

Embeddings are cached to disk as an .npz next to the corpus. The cache is
keyed on BOTH the corpus max-mtime AND the model name (MIL-183): swapping the
model invalidates the cache and forces a re-encode, so we never silently serve
vectors from one model against query vectors from another.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from mil.chat.retrievers._corpus import corpus_mtime, load_review_records
from mil.chat.retrievers.base import Evidence, EvidenceBundle, Retriever
from mil.config.retrieval_models import CHAT_EMBEDDING_MODEL, EMBEDDING_DEVICE

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent.parent
_CACHE_PATH  = _MIL_ROOT / "data" / "ask_embedding_cache.npz"
_MODEL_NAME  = CHAT_EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer
    logger.info("[embedding] loading %s (device=%s)", _MODEL_NAME, EMBEDDING_DEVICE)
    return SentenceTransformer(_MODEL_NAME, device=EMBEDDING_DEVICE)


def _cached_model_name() -> str | None:
    """Model name the on-disk cache was built with, or None if absent/legacy."""
    if not _CACHE_PATH.exists():
        return None
    try:
        loaded = np.load(_CACHE_PATH, allow_pickle=False)
        if "model" in loaded:
            return str(loaded["model"])
    except Exception:
        return None
    return None  # legacy cache without a model stamp — treat as stale


def _cache_valid() -> bool:
    if not _CACHE_PATH.exists():
        return False
    if _cached_model_name() != _MODEL_NAME:
        return False  # MIL-183: model changed (or legacy unstamped cache) → rebuild
    return _CACHE_PATH.stat().st_mtime >= corpus_mtime()


def _build_cache(records: list[dict]) -> np.ndarray:
    model = _load_model()
    texts = [r["text"] for r in records]
    logger.info("[embedding] encoding %d documents — this can take a while", len(texts))
    vectors = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    ids = np.array([r["id"] for r in records])
    np.savez(_CACHE_PATH, ids=ids, vectors=vectors, model=np.array(_MODEL_NAME))
    logger.info("[embedding] cache written to %s (model=%s)", _CACHE_PATH, _MODEL_NAME)
    return vectors


@lru_cache(maxsize=1)
def _load_corpus_embeddings() -> tuple[list[dict], np.ndarray]:
    records = load_review_records()
    if not records:
        return records, np.zeros((0, 384), dtype=np.float32)

    if _cache_valid():
        loaded = np.load(_CACHE_PATH, allow_pickle=False)
        vectors = loaded["vectors"]
        if len(vectors) == len(records):
            logger.info("[embedding] using cached embeddings: %d vectors", len(vectors))
            return records, vectors
        logger.info("[embedding] cache size mismatch — rebuilding")

    vectors = _build_cache(records)
    return records, vectors


class EmbeddingRetriever(Retriever):
    name = "embedding"

    def retrieve(
        self,
        query: str,
        entities: Optional[dict[str, Any]] = None,
        k: int = 10,
    ) -> EvidenceBundle:
        entities = entities or {}
        bundle = EvidenceBundle(query=query, retriever_chain=[self.name])
        records, vectors = _load_corpus_embeddings()
        if not records:
            return bundle

        model = _load_model()
        qv = model.encode(query, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)

        sims = vectors @ qv  # cosine similarity (vectors are L2-normalised)

        competitors = self._competitors(entities)
        severity = entities.get("severity") or entities.get("severity_class")
        source_filter = entities.get("source")
        issue_type = entities.get("issue_type")

        order = np.argsort(-sims)
        taken = 0
        candidates = 0
        for i in order:
            score = float(sims[i])
            if score <= 0:
                break
            r = records[int(i)]
            if competitors and r["competitor"] not in competitors:
                continue
            if severity and r["severity"] != severity:
                continue
            if source_filter and r["source"] != source_filter:
                continue
            if issue_type and r["issue_type"] != issue_type:
                continue
            candidates += 1
            bundle.add(Evidence(
                source="reviews",
                id=r["id"],
                text=r["text"],
                score=round(score, 4),
                metadata={
                    "competitor":    r["competitor"],
                    "review_source": r["source"],
                    "issue_type":    r["issue_type"],
                    "severity":      r["severity"],
                    "date":          r["date"],
                    "rating":        r["rating"],
                    "journey":       r["journey"],
                },
            ))
            taken += 1
            if taken >= k:
                break

        bundle.total_candidates = candidates
        return bundle

    @staticmethod
    def _competitors(entities: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        if entities.get("competitor"):
            out.add(str(entities["competitor"]).lower())
        for c in entities.get("competitors") or []:
            if isinstance(c, str):
                out.add(c.lower())
        return out
