"""
rating_velocity_monitor.py — App rating velocity monitor.

Runs every 6 hours. Tracks rolling average rating per competitor
across App Store and Google Play. Detects:

  Revenue Heist:  drop > 0.3 points in 14 days  → P1
  P0 Immediate:   drop > 0.5 points in 72 hours  → P0
  Volume Spike:   review volume > 200% of 7-day baseline → P1

Output: mil/data/signals/velocity_alerts.json

Zero Entanglement: no imports from internal modules.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Trigger thresholds
REVENUE_HEIST_DROP = 0.3
REVENUE_HEIST_WINDOW_DAYS = 14
P0_DROP = 0.5
P0_WINDOW_HOURS = 72
VOLUME_SPIKE_MULTIPLIER = 2.0   # 200% above baseline
VOLUME_BASELINE_DAYS = 7

TRACKED_SOURCES = {"app_store", "google_play"}

DATA_DIR = Path(__file__).parent.parent / "data" / "signals"


def _load_signal_history(data_dir: Path) -> list[dict]:
    """Load all signal JSON files from data_dir. Returns flat list of signals."""
    all_signals = []
    for f in sorted(data_dir.glob("signals_*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                batch = json.load(fh)
                if isinstance(batch, list):
                    all_signals.extend(batch)
        except Exception as exc:
            logger.warning("[velocity] Failed to load %s: %s", f.name, exc)
    return all_signals


def _filter_source_signals(signals: list[dict], competitor: str, source: str) -> list[dict]:
    return [
        s for s in signals
        if s.get("competitor") == competitor and s.get("source") == source
    ]


def _average_rating_in_window(signals: list[dict], since: datetime) -> Optional[float]:
    """Average rating from signals after `since` timestamp."""
    ratings = []
    for s in signals:
        ts_str = s.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= since:
                rating = s.get("raw_data", {}).get("rating")
                if rating is not None:
                    ratings.append(float(rating))
        except (ValueError, TypeError):
            continue
    return sum(ratings) / len(ratings) if ratings else None


def _volume_in_window(signals: list[dict], since: datetime) -> int:
    count = 0
    for s in signals:
        ts_str = s.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= since:
                count += 1
        except (ValueError, TypeError):
            continue
    return count


def run_velocity_check(data_dir: Path = DATA_DIR) -> list[dict]:
    """
    Run all velocity checks. Returns list of alert dicts.
    Writes velocity_alerts.json to data_dir.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    signals = _load_signal_history(data_dir)

    if not signals:
        logger.info("[velocity] No signal history found. Nothing to check.")
        return []

    now = datetime.now(timezone.utc)
    alerts = []

    # Collect unique competitors from signal history
    competitors = list({s.get("competitor") for s in signals if s.get("competitor")})

    for competitor in competitors:
        for source in TRACKED_SOURCES:
            comp_signals = _filter_source_signals(signals, competitor, source)
            if not comp_signals:
                continue

            # ── Revenue Heist check (14-day drop) ────────────
            # Compare last 3 days vs 11-14 days ago
            recent_start = now - timedelta(days=3)
            baseline_start = now - timedelta(days=REVENUE_HEIST_WINDOW_DAYS)
            baseline_end = now - timedelta(days=3)

            recent_sigs = [s for s in comp_signals if _in_window(s, recent_start, now)]
            baseline_sigs = [s for s in comp_signals if _in_window(s, baseline_start, baseline_end)]

            recent_avg = _avg_rating(recent_sigs)
            baseline_avg = _avg_rating(baseline_sigs)

            if recent_avg is not None and baseline_avg is not None:
                drop = baseline_avg - recent_avg
                if drop >= REVENUE_HEIST_DROP:
                    alerts.append({
                        "alert_type": "REVENUE_HEIST",
                        "severity": "P1",
                        "competitor": competitor,
                        "source": source,
                        "rating_drop": round(drop, 3),
                        "baseline_avg": round(baseline_avg, 3),
                        "recent_avg": round(recent_avg, 3),
                        "window_days": REVENUE_HEIST_WINDOW_DAYS,
                        "timestamp": now.isoformat(),
                        "message": f"Revenue Heist — {competitor} rating dropped {drop:.2f} points over 14 days on {source}.",
                    })
                    logger.warning("[velocity] REVENUE_HEIST: %s on %s — drop %.2f", competitor, source, drop)

            # ── P0 Immediate check (72-hour drop) ────────────
            window_72h = now - timedelta(hours=P0_WINDOW_HOURS)
            prior_window = now - timedelta(hours=P0_WINDOW_HOURS * 2)

            recent_72h = [s for s in comp_signals if _in_window(s, window_72h, now)]
            prior_72h = [s for s in comp_signals if _in_window(s, prior_window, window_72h)]

            r72_avg = _avg_rating(recent_72h)
            p72_avg = _avg_rating(prior_72h)

            if r72_avg is not None and p72_avg is not None:
                drop_72 = p72_avg - r72_avg
                if drop_72 >= P0_DROP:
                    alerts.append({
                        "alert_type": "P0_IMMEDIATE",
                        "severity": "P0",
                        "competitor": competitor,
                        "source": source,
                        "rating_drop": round(drop_72, 3),
                        "baseline_avg": round(p72_avg, 3),
                        "recent_avg": round(r72_avg, 3),
                        "window_hours": P0_WINDOW_HOURS,
                        "timestamp": now.isoformat(),
                        "message": f"P0 — {competitor} rating dropped {drop_72:.2f} points in 72 hours on {source}.",
                    })
                    logger.error("[velocity] P0_IMMEDIATE: %s on %s — drop %.2f in 72h", competitor, source, drop_72)

            # ── Volume Spike check (200% above 7-day baseline) ─
            baseline_7d_start = now - timedelta(days=VOLUME_BASELINE_DAYS)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            today_sigs = [s for s in comp_signals if _in_window(s, today_start, now)]
            baseline_7d_sigs = [s for s in comp_signals if _in_window(s, baseline_7d_start, today_start)]

            today_vol = len(today_sigs)
            daily_baseline = len(baseline_7d_sigs) / max(VOLUME_BASELINE_DAYS, 1)

            if daily_baseline > 0 and today_vol > daily_baseline * VOLUME_SPIKE_MULTIPLIER:
                alerts.append({
                    "alert_type": "VOLUME_SPIKE",
                    "severity": "P1",
                    "competitor": competitor,
                    "source": source,
                    "today_volume": today_vol,
                    "daily_baseline": round(daily_baseline, 1),
                    "spike_ratio": round(today_vol / daily_baseline, 2),
                    "timestamp": now.isoformat(),
                    "message": f"Volume spike — {competitor} on {source}: {today_vol} reviews today vs {daily_baseline:.1f} daily baseline.",
                })
                logger.warning("[velocity] VOLUME_SPIKE: %s on %s — %d vs baseline %.1f", competitor, source, today_vol, daily_baseline)

    # Write alerts
    alert_file = data_dir / "velocity_alerts.json"
    with open(alert_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": now.isoformat(),
            "alert_count": len(alerts),
            "alerts": alerts,
        }, f, indent=2)

    logger.info("[velocity] Velocity check complete. %d alert(s). Written to %s", len(alerts), alert_file)
    return alerts


def _in_window(signal: dict, start: datetime, end: datetime) -> bool:
    ts_str = signal.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return start <= ts <= end
    except (ValueError, TypeError):
        return False


def _avg_rating(signals: list[dict]) -> Optional[float]:
    ratings = []
    for s in signals:
        r = s.get("raw_data", {}).get("rating")
        if r is not None:
            try:
                ratings.append(float(r))
            except (ValueError, TypeError):
                pass
    return sum(ratings) / len(ratings) if ratings else None
