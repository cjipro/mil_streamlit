"""
test_voice_agent.py — Unit tests for voice_intelligence_agent orchestrator.
All sources mocked — no live calls.
"""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.harvester.sources.base import RawSignal, SILENCE_FLAG


class TestVoiceAgentOrchestrator(unittest.TestCase):

    def _make_mock_signal(self, source="downdetector", competitor="NatWest", severity="P1"):
        sig = RawSignal(
            source=source,
            competitor=competitor,
            trust_weight=0.95,
            severity_class=severity,
            raw_data={"test": True},
        )
        return sig

    def test_raw_signal_to_dict(self):
        sig = self._make_mock_signal()
        d = sig.to_dict()
        self.assertEqual(d["source"], "downdetector")
        self.assertEqual(d["competitor"], "NatWest")
        self.assertEqual(d["severity_class"], "P1")
        self.assertIn("signal_id", d)
        self.assertIn("timestamp", d)

    def test_raw_signal_defaults(self):
        sig = RawSignal()
        self.assertEqual(sig.severity_class, "INFO")
        self.assertFalse(sig.spike_detected)
        self.assertTrue(sig.jax_clean)
        self.assertEqual(sig.jax_flags, [])
        self.assertIsNone(sig.error_flag)

    def test_silence_flag_signal(self):
        sig = RawSignal(
            source="app_store",
            competitor="Monzo",
            error_flag=SILENCE_FLAG,
        )
        d = sig.to_dict()
        self.assertEqual(d["error_flag"], SILENCE_FLAG)

    @patch("mil.harvester.voice_intelligence_agent._build_all_sources")
    @patch("mil.harvester.voice_intelligence_agent.DATA_DIR")
    def test_run_harvest_skips_stubs(self, mock_data_dir, mock_build):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            with patch("mil.harvester.voice_intelligence_agent.DATA_DIR", tmp_path):
                mock_source = MagicMock()
                mock_source.status = "STUB"
                mock_source.source_name = "twitter_x"
                mock_source.competitor = "NatWest"
                mock_build.return_value = [mock_source]

                from mil.harvester import voice_intelligence_agent
                signals = voice_intelligence_agent.run_harvest()

                mock_source.run.assert_not_called()
                self.assertEqual(signals, [])

    @patch("mil.harvester.voice_intelligence_agent._build_all_sources")
    def test_run_harvest_processes_active_source(self, mock_build):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            with patch("mil.harvester.voice_intelligence_agent.DATA_DIR", tmp_path):
                mock_source = MagicMock()
                mock_source.status = "ACTIVE"
                mock_source.source_name = "downdetector"
                mock_source.competitor = "NatWest"

                sig = self._make_mock_signal()
                mock_source.run.return_value = [sig]
                mock_build.return_value = [mock_source]

                from mil.harvester import voice_intelligence_agent
                import importlib
                importlib.reload(voice_intelligence_agent)

                with patch("mil.harvester.voice_intelligence_agent._build_all_sources", return_value=[mock_source]):
                    with patch("mil.harvester.voice_intelligence_agent.DATA_DIR", tmp_path):
                        signals = voice_intelligence_agent.run_harvest()

                self.assertEqual(len(signals), 1)
                self.assertEqual(signals[0]["source"], "downdetector")


if __name__ == "__main__":
    unittest.main()
