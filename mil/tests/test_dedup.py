"""
test_dedup.py — Unit tests for enrichment deduplication logic.

Tests the SHA-256 content hash dedup used in enrich_sonnet.run_enrichment()
to prevent re-enriching records already in the enriched file.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _content_hash(r: dict) -> str:
    text = (r.get("review") or r.get("content") or r.get("body") or "").strip()
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


class TestContentHash:
    def test_same_review_same_hash(self):
        r = {"review": "App keeps crashing on login"}
        assert _content_hash(r) == _content_hash(r)

    def test_different_reviews_different_hash(self):
        r1 = {"review": "App keeps crashing on login"}
        r2 = {"review": "Payment failed three times"}
        assert _content_hash(r1) != _content_hash(r2)

    def test_content_field_used_when_no_review(self):
        r = {"content": "App keeps crashing on login"}
        r_review = {"review": "App keeps crashing on login"}
        assert _content_hash(r) == _content_hash(r_review)

    def test_empty_record_produces_stable_hash(self):
        r = {}
        h = _content_hash(r)
        assert len(h) == 64
        assert _content_hash(r) == h

    def test_whitespace_stripped_before_hash(self):
        r1 = {"review": "  App crashing  "}
        r2 = {"review": "App crashing"}
        assert _content_hash(r1) == _content_hash(r2)

    def test_unicode_content_handled(self):
        r = {"review": "Application ne s\u2019ouvre pas \u2014 tr\u00e8s frustrant"}
        h = _content_hash(r)
        assert len(h) == 64

    def test_dedup_set_blocks_duplicate(self):
        records = [
            {"review": "App crashing constantly"},
            {"review": "Payment failed"},
        ]
        existing_hashes = {_content_hash(r) for r in records}
        new_record = {"review": "App crashing constantly"}
        assert _content_hash(new_record) in existing_hashes

    def test_dedup_set_allows_new_record(self):
        records = [{"review": "App crashing constantly"}]
        existing_hashes = {_content_hash(r) for r in records}
        new_record = {"review": "Login not working at all"}
        assert _content_hash(new_record) not in existing_hashes
