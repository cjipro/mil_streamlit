"""
mil/chat/retrievers/bm25.py — MIL-41.

BM25 lexical retriever over the enriched review corpus.
Best for exact-phrase quote_search and keyword-dense issue_lookup.

Inline BM25Okapi implementation — no external dependency.
Corpus loaded once per process; rebuilt only if file mtimes change.
"""
from __future__ import annotations

import logging
import math
import re
from functools import lru_cache
from typing import Any, Optional

from mil.chat.retrievers._corpus import load_review_records
from mil.chat.retrievers.base import Evidence, EvidenceBundle, Retriever

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z][a-z']+")
_STOPWORDS = frozenset("""
a an and are as at be but by for from has have he her him his i in is it its
just my me of on or our she so than that the their them there these they this
to was we were what when where which who why will with would you your about
app bank very really
""".split())

_K1 = 1.5
_B  = 0.75
_MIN_TOKEN_LEN = 3


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower())
            if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS]


class _BM25Index:
    """In-memory BM25Okapi index over a fixed corpus."""
    def __init__(self, docs: list[list[str]]):
        self.docs = docs
        self.N = len(docs)
        self.doc_lens = [len(d) for d in docs]
        self.avgdl = sum(self.doc_lens) / self.N if self.N else 0.0

        # Document frequencies
        df: dict[str, int] = {}
        for doc in docs:
            for token in set(doc):
                df[token] = df.get(token, 0) + 1

        # Inverse document frequency
        self.idf: dict[str, float] = {
            t: math.log((self.N - df_t + 0.5) / (df_t + 0.5) + 1.0)
            for t, df_t in df.items()
        }

        # Precompute term frequencies per doc
        self.tf: list[dict[str, int]] = []
        for doc in docs:
            counts: dict[str, int] = {}
            for t in doc:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)

    def score(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * self.N
        for t in query_tokens:
            idf_t = self.idf.get(t)
            if idf_t is None:
                continue
            for i in range(self.N):
                tf = self.tf[i].get(t)
                if not tf:
                    continue
                dl = self.doc_lens[i]
                denom = tf + _K1 * (1 - _B + _B * dl / self.avgdl) if self.avgdl else 1.0
                scores[i] += idf_t * (tf * (_K1 + 1)) / denom
        return scores


@lru_cache(maxsize=1)
def _load_index() -> tuple[list[dict], _BM25Index]:
    """Load shared review records + build the BM25 index."""
    records = load_review_records()
    tokenized = [_tokenize(r["text"]) for r in records]
    logger.info("[bm25] indexed %d reviews", len(records))
    return records, _BM25Index(tokenized)


class BM25Retriever(Retriever):
    name = "bm25"

    def retrieve(
        self,
        query: str,
        entities: Optional[dict[str, Any]] = None,
        k: int = 10,
    ) -> EvidenceBundle:
        entities = entities or {}
        records, index = _load_index()
        bundle = EvidenceBundle(query=query, retriever_chain=[self.name])
        if not records:
            return bundle

        qtoks = _tokenize(query)
        if entities.get("issue_type"):
            qtoks += _tokenize(entities["issue_type"])
        if not qtoks:
            return bundle

        scores = index.score(qtoks)
        max_score = max(scores) if scores else 0.0
        if max_score <= 0:
            return bundle

        competitors = self._competitors(entities)
        severity_filter = entities.get("severity") or entities.get("severity_class")
        source_filter = entities.get("source")

        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        taken = 0
        for i in ranked:
            if scores[i] <= 0:
                break
            r = records[i]
            if competitors and r["competitor"] not in competitors:
                continue
            if severity_filter and r["severity"] != severity_filter:
                continue
            if source_filter and r["source"] != source_filter:
                continue

            normalised = scores[i] / max_score
            bundle.add(Evidence(
                source="reviews",
                id=r["id"],
                text=r["text"],
                score=round(normalised, 4),
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

        bundle.total_candidates = sum(1 for s in scores if s > 0)
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
