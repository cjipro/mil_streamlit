"""
mil/chat/retrievers/base.py — MIL-41.

Retriever base class + Evidence / EvidenceBundle dataclasses.

Every retriever returns Evidence items carrying:
  source    — "reviews" | "findings" | "chronicle" | "benchmark" | "clark_log"
  id        — stable identifier (primary key, content hash)
  text      — verbatim content. Customer quotes MUST be unmodified.
  score     — relevance score in [0.0, 1.0]
  metadata  — source-specific fields (date, competitor, issue_type, ...)

The contract is stateless: each retrieve() call returns a fresh bundle.
Caching belongs at the query-hash layer (MIL-47), not here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Evidence:
    source: str
    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceBundle:
    query: str
    items: list[Evidence] = field(default_factory=list)
    retriever_chain: list[str] = field(default_factory=list)
    total_candidates: int = 0

    def add(self, evidence: Evidence) -> None:
        self.items.append(evidence)

    def extend(self, items: list[Evidence]) -> None:
        self.items.extend(items)

    def top_k(self, k: int) -> list[Evidence]:
        return sorted(self.items, key=lambda e: e.score, reverse=True)[:k]


class Retriever(ABC):
    """Base contract for every retriever in the pool."""

    name: str = "retriever"

    @abstractmethod
    def retrieve(
        self,
        query: str,
        entities: Optional[dict[str, Any]] = None,
        k: int = 10,
    ) -> EvidenceBundle:
        """Return an EvidenceBundle scoped to this retriever's source."""
        raise NotImplementedError
