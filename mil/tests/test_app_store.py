"""
test_app_store.py — Unit tests for AppStoreSource.
All mocked — no live HTTP calls.
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.harvester.sources.app_store import AppStoreSource
from mil.harvester.sources.base import SILENCE_FLAG


MOCK_CONFIG = {
    "name": "NatWest",
    "app_store_id": "466738371",
    "active": True,
}

MOCK_FEED_RESPONSE = {
    "feed": {
        "entry": [
            # First entry is app metadata — should be skipped
            {"im:name": {"label": "NatWest Mobile Banking"}},
            {
                "im:rating": {"label": "1"},
                "title": {"label": "App broken"},
                "content": {"label": "Cannot log in since the update. Terrible."},
                "im:version": {"label": "8.12.0"},
                "updated": {"label": "2026-03-28T10:00:00-07:00"},
                "author": {"name": {"label": "user123"}},
            },
            {
                "im:rating": {"label": "5"},
                "title": {"label": "Works great"},
                "content": {"label": "Very smooth experience."},
                "im:version": {"label": "8.12.0"},
                "updated": {"label": "2026-03-28T09:00:00-07:00"},
                "author": {"name": {"label": "happyuser"}},
            },
        ]
    }
}


class TestAppStoreSource(unittest.TestCase):

    def setUp(self):
        self.source = AppStoreSource("NatWest", MOCK_CONFIG)

    def test_source_name(self):
        self.assertEqual(self.source.source_name, "app_store")

    def test_trust_weight(self):
        self.assertAlmostEqual(self.source.trust_weight, 0.90)

    def test_url_contains_app_id(self):
        self.assertIn("466738371", self.source.url)

    def test_parse_skips_metadata_entry(self):
        results = self.source.parse(MOCK_FEED_RESPONSE)
        self.assertEqual(len(results), 2)

    def test_parse_fields(self):
        results = self.source.parse(MOCK_FEED_RESPONSE)
        self.assertEqual(results[0]["rating"], 1)
        self.assertEqual(results[0]["version"], "8.12.0")
        self.assertIn("Cannot log in", results[0]["review"])

    def test_to_signal_p1_for_one_star(self):
        item = {"rating": 1, "review": "broken", "title": "bad", "version": "8.12.0", "date": ""}
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "P1")

    def test_to_signal_p2_for_two_star(self):
        item = {"rating": 2, "review": "poor", "title": "meh", "version": "8.12.0", "date": ""}
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "P2")

    def test_to_signal_info_for_five_star(self):
        item = {"rating": 5, "review": "great", "title": "good", "version": "8.12.0", "date": ""}
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "INFO")

    @patch("mil.harvester.sources.app_store.requests.get")
    def test_run_returns_signals(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_FEED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        signals = self.source.run()
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0].competitor, "NatWest")

    @patch("mil.harvester.sources.app_store.requests.get")
    def test_run_silence_on_network_error(self, mock_get):
        mock_get.side_effect = Exception("Timeout")
        signals = self.source.run()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].error_flag, SILENCE_FLAG)


if __name__ == "__main__":
    unittest.main()
