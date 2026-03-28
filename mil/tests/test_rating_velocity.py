"""
test_rating_velocity.py — Unit tests for rating velocity monitor.
"""
import json
import unittest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.harvester.rating_velocity_monitor import run_velocity_check, _in_window, _avg_rating


def make_signal(competitor, source, rating, hours_ago):
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "source": source,
        "competitor": competitor,
        "trust_weight": 0.90,
        "timestamp": ts.isoformat(),
        "raw_data": {"rating": rating},
    }


def write_signals(tmp_dir: Path, signals: list):
    out = tmp_dir / "signals_2026-03-28_120000.json"
    with open(out, "w") as f:
        json.dump(signals, f)


class TestVelocityMonitor(unittest.TestCase):

    def test_no_signals_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            alerts = run_velocity_check(Path(tmp))
        self.assertEqual(alerts, [])

    def test_p0_alert_on_72h_drop(self):
        signals = []
        # Recent: 1-star reviews (last 24h)
        for _ in range(5):
            signals.append(make_signal("NatWest", "app_store", 1.0, hours_ago=2))
        # Baseline: 5-star reviews (80-100h ago)
        for _ in range(5):
            signals.append(make_signal("NatWest", "app_store", 5.0, hours_ago=90))

        with tempfile.TemporaryDirectory() as tmp:
            write_signals(Path(tmp), signals)
            alerts = run_velocity_check(Path(tmp))

        p0_alerts = [a for a in alerts if a["alert_type"] == "P0_IMMEDIATE"]
        self.assertTrue(len(p0_alerts) > 0, "Expected P0_IMMEDIATE alert")
        self.assertEqual(p0_alerts[0]["competitor"], "NatWest")
        self.assertEqual(p0_alerts[0]["severity"], "P0")

    def test_revenue_heist_alert_on_14d_drop(self):
        signals = []
        # Recent 3 days: 1-star
        for _ in range(10):
            signals.append(make_signal("Lloyds", "google_play", 1.0, hours_ago=24))
        # 11-14 days ago: 5-star
        for _ in range(10):
            signals.append(make_signal("Lloyds", "google_play", 5.0, hours_ago=300))

        with tempfile.TemporaryDirectory() as tmp:
            write_signals(Path(tmp), signals)
            alerts = run_velocity_check(Path(tmp))

        rh_alerts = [a for a in alerts if a["alert_type"] == "REVENUE_HEIST"]
        self.assertTrue(len(rh_alerts) > 0, "Expected REVENUE_HEIST alert")

    def test_in_window_true(self):
        now = datetime.now(timezone.utc)
        sig = {"timestamp": (now - timedelta(hours=1)).isoformat()}
        self.assertTrue(_in_window(sig, now - timedelta(hours=2), now))

    def test_in_window_false(self):
        now = datetime.now(timezone.utc)
        sig = {"timestamp": (now - timedelta(hours=5)).isoformat()}
        self.assertFalse(_in_window(sig, now - timedelta(hours=2), now))

    def test_avg_rating(self):
        sigs = [
            {"raw_data": {"rating": 1}},
            {"raw_data": {"rating": 3}},
            {"raw_data": {"rating": 5}},
        ]
        avg = _avg_rating(sigs)
        self.assertAlmostEqual(avg, 3.0)

    def test_avg_rating_empty(self):
        self.assertIsNone(_avg_rating([]))

    def test_alerts_written_to_file(self):
        signals = []
        for _ in range(5):
            signals.append(make_signal("HSBC", "app_store", 1.0, hours_ago=2))
        for _ in range(5):
            signals.append(make_signal("HSBC", "app_store", 5.0, hours_ago=90))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_signals(tmp_path, signals)
            run_velocity_check(tmp_path)
            alert_file = tmp_path / "velocity_alerts.json"
            self.assertTrue(alert_file.exists())
            with open(alert_file) as f:
                data = json.load(f)
            self.assertIn("alerts", data)


if __name__ == "__main__":
    unittest.main()
