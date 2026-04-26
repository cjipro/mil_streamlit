"""
Tests for Reckoner-scoped behaviour in mil.chat.

The pipeline talks to Haiku for intent classification; tests stub `classify`
so we can exercise the scope-aware code paths without burning API tokens.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from mil.chat import refusals
from mil.chat.intent import Intent, IntentResult


# ── refusals.is_firm_specific_for_reckoner ────────────────────────────────

class TestFirmSpecificGuard:
    def test_single_firm_no_peer_framing_is_firm_specific(self):
        assert refusals.is_firm_specific_for_reckoner(
            "how is barclays doing on logins", {"competitor": "barclays"}
        ) is True

    def test_no_firm_named_is_not_firm_specific(self):
        assert refusals.is_firm_specific_for_reckoner(
            "what are the top login issues this week", {}
        ) is False

    def test_multiple_firms_named_is_not_firm_specific(self):
        assert refusals.is_firm_specific_for_reckoner(
            "compare barclays and natwest on payments", {}
        ) is False

    def test_peer_framing_term_lifts_the_refusal(self):
        # Single firm but peer-framed ⇒ valid Reckoner question
        assert refusals.is_firm_specific_for_reckoner(
            "where does barclays rank on login failures", {}
        ) is False

    def test_cohort_framing_term_lifts_the_refusal(self):
        assert refusals.is_firm_specific_for_reckoner(
            "show barclays login issues across the uk banking cohort", {}
        ) is False

    def test_chronicle_query_naming_one_bank_is_not_firm_specific(self):
        assert refusals.is_firm_specific_for_reckoner(
            "what does the chronicle say about tsb's 2018 outage", {}
        ) is False
        assert refusals.is_firm_specific_for_reckoner(
            "tell me about chr-001", {}
        ) is False


# ── intent.classify scope behaviour ───────────────────────────────────────

def _stub_haiku_response(intent_value: str, entities: dict | None = None) -> str:
    import json
    return json.dumps({
        "intent": intent_value,
        "confidence": 0.9,
        "entities": entities or {},
    })


class TestIntentScope:
    def test_sonar_scope_keeps_barclays_default(self):
        from mil.chat.intent import classify
        with patch("mil.chat.intent.call_anthropic",
                   return_value=_stub_haiku_response("issue_lookup")):
            result = classify("any active P0 signals?", scope="sonar")
        assert result.entities.get("competitor") == "barclays"
        assert result.entities.get("competitor_default") == "implicit"

    def test_all_scope_keeps_barclays_default(self):
        from mil.chat.intent import classify
        with patch("mil.chat.intent.call_anthropic",
                   return_value=_stub_haiku_response("issue_lookup")):
            result = classify("any active P0 signals?", scope="all")
        assert result.entities.get("competitor") == "barclays"

    def test_reckoner_scope_skips_barclays_default(self):
        from mil.chat.intent import classify
        with patch("mil.chat.intent.call_anthropic",
                   return_value=_stub_haiku_response("issue_lookup")):
            result = classify("any active P0 signals?", scope="reckoner")
        assert "competitor" not in result.entities
        assert "competitor_default" not in result.entities

    def test_explicit_competitor_preserved_under_reckoner(self):
        from mil.chat.intent import classify
        with patch("mil.chat.intent.call_anthropic",
                   return_value=_stub_haiku_response("issue_lookup",
                                                    {"competitor": "natwest"})):
            result = classify("how is natwest on payments", scope="reckoner")
        # Reckoner doesn't strip an explicitly-named competitor — that's the
        # job of the firm-specific guard in pipeline.ask().
        assert result.entities.get("competitor") == "natwest"

    def test_reckoner_skips_keyword_override(self):
        # Classifier returned UNKNOWN — under sonar/all, the override would
        # rescue the query by defaulting to Barclays + a journey. Under
        # reckoner, that fallback is wrong cohort framing — let it through
        # as UNKNOWN so the user gets a refusal pointing at Sonar.
        from mil.chat.intent import classify
        with patch("mil.chat.intent.call_anthropic",
                   return_value=_stub_haiku_response("unknown")):
            result = classify("login regressing", scope="reckoner")
        assert result.intent == Intent.UNKNOWN

    def test_sonar_scope_keeps_keyword_override(self):
        from mil.chat.intent import classify
        with patch("mil.chat.intent.call_anthropic",
                   return_value=_stub_haiku_response("unknown")):
            result = classify("login regressing", scope="sonar")
        # Override should fire and route to ISSUE_LOOKUP with Barclays default.
        assert result.intent == Intent.ISSUE_LOOKUP
        assert result.entities.get("competitor") == "barclays"


# ── intent._system_prompt scope branching ────────────────────────────────

class TestSystemPromptScope:
    def test_sonar_prompt_carries_barclays_default_block(self):
        from mil.chat.intent import _system_prompt
        prompt = _system_prompt("sonar")
        assert "BARCLAYS IS THE DEFAULT SUBJECT" in prompt
        assert "RECKONER IS COHORT-WIDE" not in prompt

    def test_all_scope_carries_sonar_block_too(self):
        # Backwards compat: scope="all" defaults to Sonar-flavoured prompt.
        from mil.chat.intent import _system_prompt
        prompt = _system_prompt("all")
        assert "BARCLAYS IS THE DEFAULT SUBJECT" in prompt

    def test_reckoner_prompt_uses_cohort_block(self):
        from mil.chat.intent import _system_prompt
        prompt = _system_prompt("reckoner")
        assert "RECKONER IS COHORT-WIDE INDUSTRY INTELLIGENCE" in prompt
        assert "BARCLAYS IS THE DEFAULT SUBJECT" not in prompt

    def test_reckoner_prompt_explicitly_handles_cohort_two_word_phrases(self):
        # The bug we just fixed: bare "industry sentiment" was returning
        # insufficient. Prompt now tells the classifier to route it.
        from mil.chat.intent import _system_prompt
        prompt = _system_prompt("reckoner")
        assert "industry sentiment" in prompt.lower()

    def test_reckoner_prompt_tells_classifier_to_route_single_firm_queries_too(self):
        # Single-firm queries are upstream-refused by the pipeline scope
        # guard, not by the classifier — so the classifier should still
        # route them rather than refusing.
        from mil.chat.intent import _system_prompt
        prompt = _system_prompt("reckoner")
        # The prompt mentions the upstream scope guard so the model knows
        # not to double-refuse.
        assert "scope guard" in prompt.lower() or "redirect" in prompt.lower()


# ── pipeline.ask scope guard ──────────────────────────────────────────────

class TestPipelineScope:
    def test_reckoner_refuses_firm_specific_query(self):
        from mil.chat.pipeline import ask
        ir = IntentResult(
            intent=Intent.ISSUE_LOOKUP,
            confidence=0.9,
            entities={"competitor": "barclays"},
        )
        with patch("mil.chat.pipeline.classify", return_value=ir):
            response = ask("how is barclays doing on logins", scope="reckoner")
        assert response.refusal == "scope_mismatch"
        assert "Sonar" in response.answer or "sonar" in response.answer.lower()

    def test_reckoner_allows_cohort_query(self):
        # Cohort query with peer-rank intent — should NOT trip the guard.
        from mil.chat.pipeline import ask
        ir = IntentResult(
            intent=Intent.PEER_RANK,
            confidence=0.9,
            entities={},
        )
        # Mock retrieval to return empty so we get an INSUFFICIENT_EVIDENCE
        # refusal rather than firing real retrievers — but crucially not
        # SCOPE_MISMATCH.
        with patch("mil.chat.pipeline.classify", return_value=ir), \
             patch("mil.chat.pipeline._retrieve_all") as mock_retrieve:
            from mil.chat.retrievers.base import EvidenceBundle
            mock_retrieve.return_value = EvidenceBundle(query="x", retriever_chain=["sql"])
            response = ask("rank the uk banks on login failures", scope="reckoner")
        assert response.refusal != "scope_mismatch"

    def test_sonar_scope_allows_firm_specific_query(self):
        # Same firm-specific query under sonar scope must NOT refuse.
        from mil.chat.pipeline import ask
        ir = IntentResult(
            intent=Intent.ISSUE_LOOKUP,
            confidence=0.9,
            entities={"competitor": "barclays"},
        )
        with patch("mil.chat.pipeline.classify", return_value=ir), \
             patch("mil.chat.pipeline._retrieve_all") as mock_retrieve:
            from mil.chat.retrievers.base import EvidenceBundle
            mock_retrieve.return_value = EvidenceBundle(query="x", retriever_chain=["bm25"])
            response = ask("how is barclays doing on logins", scope="sonar")
        assert response.refusal != "scope_mismatch"


# ── api_server scope header ───────────────────────────────────────────────

class TestApiServerScope:
    def _stub_handler(self, header_value: str | None):
        """Build a minimal _Handler that exposes _scope() with stubbed headers."""
        from mil.chat.api_server import _Handler

        class _StubHeaders:
            def __init__(self, value: str | None):
                self._value = value
            def get(self, key: str, default=None):
                if key == "X-CJI-Scope":
                    return self._value
                return default

        # Bypass __init__ — we only need _scope() and self.headers.
        handler = _Handler.__new__(_Handler)
        handler.headers = _StubHeaders(header_value)
        return handler

    def test_no_header_defaults_to_all(self):
        h = self._stub_handler(None)
        assert h._scope() == "all"

    def test_reckoner_header_recognised(self):
        h = self._stub_handler("reckoner")
        assert h._scope() == "reckoner"

    def test_sonar_header_recognised(self):
        h = self._stub_handler("sonar")
        assert h._scope() == "sonar"

    def test_unknown_header_falls_back_to_all(self):
        h = self._stub_handler("malicious"); assert h._scope() == "all"

    def test_case_insensitive(self):
        h = self._stub_handler("Reckoner")
        assert h._scope() == "reckoner"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
