"""
test_jax_filter.py — Unit tests for Jax synthetic filter.
"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.harvester.jax_synthetic_filter import apply_jax_filter, apply_jax_filter_batch


def make_signal(source="reddit", raw_data=None):
    return {
        "source": source,
        "competitor": "NatWest",
        "trust_weight": 0.85,
        "raw_data": raw_data or {},
    }


class TestJaxFilter(unittest.TestCase):

    def test_clean_signal_passes(self):
        sig = make_signal("app_store", {"rating": 1, "review": "App completely broken since update cannot log in at all very frustrated customer"})
        result = apply_jax_filter(sig)
        self.assertTrue(result["jax_clean"])
        self.assertEqual(result["jax_flags"], [])

    def test_short_content_flagged(self):
        sig = make_signal("app_store", {"rating": 1, "review": "bad"})
        result = apply_jax_filter(sig)
        self.assertIn("JAX_SHORT_CONTENT", result["jax_flags"])
        self.assertFalse(result["jax_clean"])

    def test_drive_by_one_star_flagged(self):
        sig = make_signal("app_store", {"rating": 1, "review": "bad app"})
        result = apply_jax_filter(sig)
        self.assertIn("JAX_DRIVE_BY_ONE_STAR", result["jax_flags"])

    def test_repeated_phrases_flagged(self):
        phrase = "app not working app not working app not working app not working app not working"
        sig = make_signal("reddit", {"body": phrase})
        result = apply_jax_filter(sig)
        self.assertIn("JAX_REPEATED_PHRASES", result["jax_flags"])

    def test_downvoted_reddit_flagged(self):
        sig = make_signal("reddit", {"body": "this bank is ruining my life completely", "score": -5})
        result = apply_jax_filter(sig)
        self.assertIn("JAX_DOWNVOTED_POST", result["jax_flags"])

    def test_youtube_like_farming_flagged(self):
        sig = make_signal("youtube", {
            "title": "NatWest app not working fix",
            "like_count": 5000,
            "comment_count": 10,
            "view_count": 100000,
        })
        result = apply_jax_filter(sig)
        self.assertIn("JAX_LIKE_FARMING", result["jax_flags"])

    def test_youtube_bot_view_inflation_flagged(self):
        sig = make_signal("youtube", {
            "title": "NatWest app review",
            "like_count": 100,
            "comment_count": 1,
            "view_count": 2000000,
        })
        result = apply_jax_filter(sig)
        self.assertIn("JAX_BOT_VIEW_INFLATION", result["jax_flags"])

    def test_batch_filter(self):
        sigs = [
            make_signal("app_store", {"rating": 1, "review": "bad"}),
            make_signal("reddit", {"body": "Cannot log in to Monzo app this is really frustrating", "score": 10}),
        ]
        results = apply_jax_filter_batch(sigs)
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0]["jax_clean"])  # short content
        self.assertTrue(results[1]["jax_clean"])

    def test_original_not_mutated(self):
        sig = make_signal("reddit", {"body": "test", "score": -1})
        original_id = id(sig)
        result = apply_jax_filter(sig)
        self.assertNotEqual(id(result), original_id)  # new dict returned

    def test_existing_flags_preserved(self):
        sig = make_signal("youtube", {
            "like_count": 5000,
            "comment_count": 10,
            "view_count": 100000,
        })
        sig["jax_flags"] = ["JAX_EXISTING_FLAG"]
        result = apply_jax_filter(sig)
        self.assertIn("JAX_EXISTING_FLAG", result["jax_flags"])


if __name__ == "__main__":
    unittest.main()
