"""
test_reddit.py — Unit tests for RedditSource.
All mocked — no live API calls. PRAW is mocked entirely.
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.harvester.sources.reddit import RedditSource
from mil.harvester.sources.base import SILENCE_FLAG


MOCK_CONFIG = {
    "name": "Monzo",
    "reddit_mentions": ["Monzo", "Monzo bank", "Monzo app"],
    "active": True,
}

MOCK_POST = MagicMock()
MOCK_POST.title = "Monzo app not loading transactions"
MOCK_POST.selftext = "Since the update this morning the app won't load my transactions."
MOCK_POST.score = 45
MOCK_POST.num_comments = 23
MOCK_POST.created_utc = 1711620000.0
MOCK_POST.permalink = "/r/Monzo/comments/abc123/monzo_app_not_loading/"
MOCK_POST.id = "abc123"


class TestRedditSource(unittest.TestCase):

    def setUp(self):
        self.source = RedditSource("Monzo", MOCK_CONFIG)

    def test_source_name(self):
        self.assertEqual(self.source.source_name, "reddit")

    def test_trust_weight(self):
        self.assertAlmostEqual(self.source.trust_weight, 0.85)

    def test_keywords_from_config(self):
        self.assertIn("Monzo", self.source.keywords)

    def test_fetch_returns_list(self):
        mock_praw_module = MagicMock()
        mock_reddit = MagicMock()
        mock_praw_module.Reddit.return_value = mock_reddit
        mock_subreddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit
        mock_subreddit.search.return_value = [MOCK_POST]

        with patch.dict("sys.modules", {"praw": mock_praw_module}):
            self.source.client_id = "test_id"
            self.source.client_secret = "test_secret"
            results = self.source.fetch()
        # Should return a list of dicts (one per subreddit x post)
        self.assertIsInstance(results, list)

    def test_to_signal_p1_high_comments(self):
        item = {
            "title": "App down",
            "body": "Cannot log in",
            "score": 100,
            "num_comments": 75,
            "created_utc": "2026-03-28T10:00:00+00:00",
            "subreddit": "Monzo",
            "url": "https://reddit.com/r/Monzo/...",
            "post_id": "xyz",
        }
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "P1")
        self.assertEqual(sig.competitor, "Monzo")

    def test_to_signal_p2_medium_comments(self):
        item = {
            "title": "Minor issue",
            "body": "Slow loading",
            "score": 5,
            "num_comments": 25,
            "created_utc": "2026-03-28T10:00:00+00:00",
            "subreddit": "UKPersonalFinance",
            "url": "...",
            "post_id": "yyy",
        }
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "P2")

    def test_to_signal_info_low_comments(self):
        item = {
            "title": "Question",
            "body": "How do I...",
            "score": 2,
            "num_comments": 3,
            "created_utc": "2026-03-28T10:00:00+00:00",
            "subreddit": "UKPersonalFinance",
            "url": "...",
            "post_id": "zzz",
        }
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "INFO")

    def test_run_silence_on_import_error(self):
        # praw not installed — fetch() raises ImportError → SILENCE_FLAG after retries
        with patch.dict("sys.modules", {"praw": None}):
            signals = self.source.run()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].error_flag, SILENCE_FLAG)


if __name__ == "__main__":
    unittest.main()
