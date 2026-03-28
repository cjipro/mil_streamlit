"""
test_downdetector.py — Unit tests for DowndetectorSource.
All mocked — no live HTTP calls.
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys, os

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.harvester.sources.downdetector import DowndetectorSource
from mil.harvester.sources.base import SILENCE_FLAG, SCHEMA_DRIFT


MOCK_CONFIG = {
    "name": "NatWest",
    "downdetector_slug": "natwest",
    "active": True,
}


class TestDowndetectorSource(unittest.TestCase):

    def setUp(self):
        self.source = DowndetectorSource("NatWest", MOCK_CONFIG)

    def test_source_name(self):
        self.assertEqual(self.source.source_name, "downdetector")

    def test_trust_weight(self):
        self.assertAlmostEqual(self.source.trust_weight, 0.95)

    def test_status_active(self):
        self.assertEqual(self.source.status, "ACTIVE")

    def test_url_construction(self):
        self.assertIn("natwest", self.source.url)

    def test_parse_json_embed(self):
        html = '''
        <html><body>
        <script>window.DD.currentStatus = {"reports": 150, "status": "danger", "baseline": 30};</script>
        </body></html>
        '''
        result = self.source.parse(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["current_report_count"], 150)
        self.assertEqual(result[0]["baseline_report_count"], 30)
        self.assertEqual(result[0]["status"], "danger")

    def test_parse_regex_fallback(self):
        html = '<html><body>250 reports in the last 24 hours</body></html>'
        result = self.source.parse(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["current_report_count"], 250)
        self.assertEqual(result[0]["parse_method"], "regex_fallback")

    def test_to_signal_p0(self):
        item = {
            "current_report_count": 300,
            "baseline_report_count": 50,
            "status": "danger",
            "source_url": "https://downdetector.co.uk/status/natwest/",
            "parse_method": "json_embed",
        }
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "P0")
        self.assertTrue(sig.spike_detected)
        self.assertAlmostEqual(sig.raw_data["spike_multiplier"], 6.0)

    def test_to_signal_p1(self):
        item = {
            "current_report_count": 100,
            "baseline_report_count": 40,
            "status": "warning",
            "source_url": "...",
            "parse_method": "json_embed",
        }
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "P1")
        self.assertTrue(sig.spike_detected)

    def test_to_signal_info_no_baseline(self):
        item = {
            "current_report_count": 5,
            "baseline_report_count": 0,
            "status": "ok",
            "source_url": "...",
            "parse_method": "regex_fallback",
        }
        sig = self.source.to_signal(item)
        self.assertEqual(sig.severity_class, "INFO")
        self.assertFalse(sig.spike_detected)

    @patch("mil.harvester.sources.downdetector.requests.get")
    def test_run_silence_flag_on_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        signals = self.source.run()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].error_flag, SILENCE_FLAG)

    @patch("mil.harvester.sources.downdetector.requests.get")
    def test_run_schema_drift_on_bad_parse(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = ""  # empty → parse returns [] — but force a drift
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.object(self.source, "parse", side_effect=ValueError("schema changed")):
            signals = self.source.run()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].error_flag, SCHEMA_DRIFT)


if __name__ == "__main__":
    unittest.main()
