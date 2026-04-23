"""
mil/chat/retrievers/embedding.py — MIL-41.

Dense retriever over the enriched review corpus using all-MiniLM-L6-v2
(same model family as mil/inference/rag.py).

Embeddings are cached to disk as an .npz next to the corpus — rebuilt only
when corpus files change (compared via max mtime). First call of a cold
process pays the model-load latency; subsequent calls are O(N) cosine.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from mil.chat.retrievers._corpus import corpus_mtime, load_review_records
from mil.chat.retrievers.base import Evidence, EvidenceBundle, Retriever

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent.parent
_CACHE_PATH  = _MIL_ROOT / "data" / "ask_embedding_cache.npz"
_MODEL_NAME  = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer
    logger.info("[embedding] loading %s", _MODEL_NAME)
    return SentenceTransformer(_MODEL_NAME)


def _cache_valid() -> bool:
    if not _CACHE_PATH.exists():
        return False
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
    np.savez(_CACHE_PATH, ids=ids, vectors=vectors)
    logger.info("[embedding] cache written to %s", _CACHE_PATH)
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
