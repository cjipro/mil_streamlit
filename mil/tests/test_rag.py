"""
test_rag.py — Unit tests for mil/inference/rag.py

Tests keyword overlap fallback (no sentence-transformers dependency needed).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.inference.rag import _keyword_overlap, find_best_chronicle_match

SAMPLE_ENTRIES = [
    {
        "chronicle_id": "CHR-001",
        "inference_approved": True,
        "journey_tags": ["J_LOGIN_01"],
        "pattern_keywords": ["login", "crash", "authentication", "biometric"],
        "pattern_description": "login failure and biometric crash pattern",
    },
    {
        "chronicle_id": "CHR-002",
        "inference_approved": True,
        "journey_tags": ["J_PAY_01"],
        "pattern_keywords": ["payment", "transfer", "failed", "declined"],
        "pattern_description": "payment failure pattern across channels",
    },
    {
        "chronicle_id": "CHR-003",
        "inference_approved": False,
        "journey_tags": ["J_LOGIN_01"],
        "pattern_keywords": ["login", "access"],
        "pattern_description": "not yet approved",
    },
]


class TestKeywordOverlap:
    def test_exact_match(self):
        score = _keyword_overlap(["login", "crash"], ["login", "crash", "auth"])
        assert score > 0.0

    def test_no_overlap(self):
        assert _keyword_overlap(["payment"], ["login", "biometric"]) == 0.0

    def test_empty_signal(self):
        assert _keyword_overlap([], ["login"]) == 0.0

    def test_empty_chronicle(self):
        assert _keyword_overlap(["login"], []) == 0.0

    def test_capped_at_one(self):
        score = _keyword_overlap(["login"] * 100, ["login"])
        assert score <= 1.0

    def test_partial_substring_match(self):
        score = _keyword_overlap(["crashing"], ["crash"])
        assert score > 0.0


class TestFindBestChronicleMatch:
    def test_returns_none_when_no_entries(self):
        entry, score = find_best_chronicle_match("J_LOGIN_01", ["login"], [])
        assert entry is None
        assert score == 0.0

    def test_skips_unapproved_entries(self):
        only_unapproved = [e for e in SAMPLE_ENTRIES if not e["inference_approved"]]
        entry, score = find_best_chronicle_match("J_LOGIN_01", ["login"], only_unapproved)
        assert entry is None

    def test_journey_filter_applied(self):
        # login keywords but payment journey — should not match CHR-001 (J_LOGIN_01)
        entry, score = find_best_chronicle_match("J_PAY_01", ["login", "crash"], SAMPLE_ENTRIES)
        if entry:
            assert "J_PAY_01" in entry["journey_tags"]

    def test_best_match_selected(self):
        # payment keywords → CHR-002 should win over CHR-001
        entry, score = find_best_chronicle_match(None, ["payment", "failed"], SAMPLE_ENTRIES)
        assert entry is not None
        assert entry["chronicle_id"] == "CHR-002"

    def test_score_between_zero_and_one(self):
        _, score = find_best_chronicle_match(None, ["login", "crash"], SAMPLE_ENTRIES)
        assert 0.0 <= score <= 1.0

    def test_none_journey_matches_all(self):
        # journey_id=None means no journey filter
        entry, _ = find_best_chronicle_match(None, ["login", "crash"], SAMPLE_ENTRIES)
        assert entry is not None
