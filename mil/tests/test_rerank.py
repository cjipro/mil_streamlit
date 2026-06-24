"""
mil/tests/test_rerank.py — MIL-182.

Cross-encoder reranking stage. Uses a stub cross-encoder (no model download)
to assert ordering, comparable-score, fail-soft passthrough, and truncation.

Run: py -m pytest mil/tests/test_rerank.py -v
"""
from __future__ import annotations

import pytest

from mil.chat import rerank as rr
from mil.chat.retrievers.base import Evidence, EvidenceBundle


class _StubCE:
    """Scores a pair high iff the query term appears in the doc text."""
    def predict(self, pairs):
        return [5.0 if "crash" in doc.lower() else -5.0 for _q, doc in pairs]


def _bundle():
    b = EvidenceBundle(query="login crash", retriever_chain=["bm25", "embedding"])
    # Deliberately put the irrelevant item first so reranking has to move it.
    b.add(Evidence(source="reviews", id="A", text="Great savings rates and friendly staff", score=0.95, metadata={}))
    b.add(Evidence(source="reviews", id="B", text="The app keeps crashing on login", score=0.10, metadata={}))
    return b


def test_rerank_moves_relevant_to_top(monkeypatch):
    monkeypatch.setattr(rr, "_MODEL", _StubCE())
    out = rr.rerank(_bundle())
    assert [e.id for e in out.items] == ["B", "A"]      # relevant first now
    assert "rerank" in out.retriever_chain


def test_rerank_sets_comparable_sigmoid_score(monkeypatch):
    monkeypatch.setattr(rr, "_MODEL", _StubCE())
    out = rr.rerank(_bundle())
    # scores are sigmoid(logit) in (0,1); relevant > irrelevant
    assert 0.0 < out.items[1].score < out.items[0].score < 1.0


def test_rerank_failsoft_passthrough_when_unavailable(monkeypatch):
    monkeypatch.setattr(rr, "_MODEL", False)            # model could not load
    b = _bundle()
    out = rr.rerank(b)
    assert [e.id for e in out.items] == ["A", "B"]      # untouched order
    assert "rerank" not in out.retriever_chain


def test_rerank_truncates_to_top_n(monkeypatch):
    monkeypatch.setattr(rr, "_MODEL", _StubCE())
    out = rr.rerank(_bundle(), top_n=1)
    assert [e.id for e in out.items] == ["B"]


def test_rerank_noop_on_single_item(monkeypatch):
    # Must not even call the model for <2 items.
    monkeypatch.setattr(rr, "_MODEL", _StubCE())
    b = EvidenceBundle(query="q")
    b.add(Evidence(source="reviews", id="X", text="only one", score=0.5, metadata={}))
    out = rr.rerank(b)
    assert [e.id for e in out.items] == ["X"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
