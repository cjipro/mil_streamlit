"""
mil/tests/test_verifier.py — MIL-184.

Covers the fail-flagged behaviour of the stage-2 LLM support check: a verifier
outage (LLM error / unparseable response) must NOT silently pass as verified.
It must surface llm_check_status="unavailable" + an explicit violation so the
answer is served flagged but not cached as verified.

Run: py -m pytest mil/tests/test_verifier.py -v
"""
from __future__ import annotations

import pytest

from mil.chat import verifier
from mil.chat.retrievers.base import Evidence, EvidenceBundle
from mil.chat.synthesis import Confidence, SynthesisResult


def _bundle() -> EvidenceBundle:
    b = EvidenceBundle(query="q")
    b.add(Evidence(source="app_store", id="E1",
                   text="The app keeps crashing on login every morning.",
                   score=0.9, metadata={"severity": "P0"}))
    return b


def _result(answer="App crashing is the top issue [E1].", citations=("E1",), quotes=()):
    return SynthesisResult(answer=answer, citations=list(citations), quotes=list(quotes),
                           confidence=Confidence.EVIDENCED, chart_hint=None, model_used="test")


def test_llm_unavailable_on_exception_is_fail_flagged(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("haiku down")
    monkeypatch.setattr(verifier, "call_anthropic", boom)

    res = verifier.verify(_result(), _bundle())

    assert res.passed is False                     # AC: no longer a passing result
    assert res.llm_check_status == "unavailable"
    assert any("verification incomplete" in v for v in res.violations)


def test_llm_unavailable_on_no_json(monkeypatch):
    monkeypatch.setattr(verifier, "call_anthropic", lambda *a, **k: "sorry, I can't help")
    res = verifier.verify(_result(), _bundle())
    assert res.passed is False
    assert res.llm_check_status == "unavailable"


def test_llm_unavailable_on_bad_json(monkeypatch):
    monkeypatch.setattr(verifier, "call_anthropic", lambda *a, **k: "{not: valid, json]")
    res = verifier.verify(_result(), _bundle())
    assert res.passed is False
    assert res.llm_check_status == "unavailable"


def test_supported_answer_passes(monkeypatch):
    monkeypatch.setattr(verifier, "call_anthropic",
                        lambda *a, **k: '{"supported": true, "violations": []}')
    res = verifier.verify(_result(), _bundle())
    assert res.passed is True
    assert res.llm_check_status == "ok"
    assert res.violations == []


def test_unsupported_answer_reports_violations(monkeypatch):
    monkeypatch.setattr(verifier, "call_anthropic",
                        lambda *a, **k: '{"supported": false, "violations": ["claim X unsupported"]}')
    res = verifier.verify(_result(), _bundle())
    assert res.passed is False
    assert res.llm_check_status == "ok"
    assert "claim X unsupported" in res.violations


def test_stage1_failure_skips_llm(monkeypatch):
    called = {"n": 0}
    def spy(*a, **k):
        called["n"] += 1
        return '{"supported": true, "violations": []}'
    monkeypatch.setattr(verifier, "call_anthropic", spy)

    # citation [E9] does not resolve → stage 1 fails
    res = verifier.verify(_result(answer="bad [E9]", citations=("E9",)), _bundle())

    assert res.passed is False
    assert res.llm_check_status == "skipped"
    assert called["n"] == 0                         # stage 2 must not run


def test_empty_answer_does_not_trip_unavailable(monkeypatch):
    # An empty answer has nothing to audit — must be treated as ran-clean, not unavailable.
    monkeypatch.setattr(verifier, "call_anthropic",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call")))
    res = verifier.verify(_result(answer="", citations=()), _bundle())
    assert res.passed is True
    assert res.llm_check_status == "ok"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
