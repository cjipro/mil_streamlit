#!/usr/bin/env python3
"""
mil/data/benchmark_engine.py — MIL-27

Competitive benchmarking engine.

Computes issue-type rates per competitor (App Store + Google Play only),
tracks Barclays issue persistence streaks, calculates churn risk score.

Rates are complaint-normalised: denominator = total records minus
Positive Feedback and Other. This gives the rate among complaint
records — more meaningful for competitive benchmarking.

Two modes:
  --mode backfill   Process all unique run dates from daily_run_log.jsonl.
                    Builds full persistence history from existing enriched data.
                    Run once at MIL-27 launch.

  --mode daily      Update persistence log for today only.
                    Called as Step 4d in run_daily.py.

Usage:
  py mil/data/benchmark_engine.py --mode backfill
  py mil/data/benchmark_engine.py --mode daily
"""
import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import date as _date, datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("benchmark_engine")

# ── Paths ─────────────────────────────────────────────────────────────────────
MIL_ROOT       = Path(__file__).parent.parent
ENRICHED_DIR   = MIL_ROOT / "data" / "historical" / "enriched"
PERSISTENCE_LOG = MIL_ROOT / "data" / "issue_persistence_log.jsonl"
BENCHMARK_CACHE = MIL_ROOT / "data" / "benchmark_cache.json"
RUN_LOG        = MIL_ROOT / "data" / "daily_run_log.jsonl"

# ── Issue categories ──────────────────────────────────────────────────────────
TECHNICAL_ISSUES = {
    "App Not Opening",
    "App Crashing",
    "Login Failed",
    "Biometric / Face ID Issue",
    "Notification Issue",
    "Account Locked",
}

SERVICE_ISSUES = {
    "Payment Failed",
    "Transfer Failed",
    "Feature Broken",
    "Feature Not Working",
    "Customer Support Failure",
    "Incorrect Balance",
    "Missing Transaction",
    "Card Frozen or Blocked",
    "Slow Performance",
    "Security Concern",
}

ALL_TRACKED_ISSUES = TECHNICAL_ISSUES | SERVICE_ISSUES
EXCLUDE_FROM_RATES = {"Positive Feedback", "Other", ""}

# Competitor peer groups (excludes Barclays)
PEERS            = ["natwest", "lloyds", "hsbc", "monzo", "revolut"]
INCUMBENT_PEERS  = ["natwest", "lloyds", "hsbc"]   # Barclays' real competitive set
NEOBANK_PEERS    = ["monzo", "revolut"]
STORE_SOURCES    = {"app_store", "google_play"}

# Churn score weights
SEVERITY_WEIGHTS    = {"P0": 3.0, "P1": 2.0, "P2": 1.0}
PERSISTENCE_CAP     = 3.0   # max multiplier (reached at 10 days active)
PERSISTENCE_STEP    = 0.2   # +0.2 per day active

BENCHMARK_WINDOW_DAYS  = 90    # rolling window for daily benchmark rates
CHURN_SCORE_CAP        = 180.0 # 20pp × P0(3.0) × max_persistence(3.0) — normalises to 0-100
STREAK_GAP_TOLERANCE   = 2     # carry streak if pipeline gap ≤ this many days


# ── Data loading ──────────────────────────────────────────────────────────────

def _normalise_date(val) -> str:
    """Normalise App Store date or Google Play 'at' field to YYYY-MM-DD."""
    if not val:
        return ""
    s = str(val)[:10]   # take first 10 chars: covers YYYY-MM-DD
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return ""


def load_competitor_records(
    competitor: str,
    max_date: str | None = None,
    min_date: str | None = None,
) -> list[dict]:
    """
    Load App Store + Google Play enriched records for a competitor.
    Optionally filter to records within [min_date, max_date] (YYYY-MM-DD, inclusive).
    """
    records = []
    for source in STORE_SOURCES:
        f = ENRICHED_DIR / f"{source}_{competitor}_enriched.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for r in data.get("records", []):
                if max_date or min_date:
                    rv_date = _normalise_date(r.get("date") or r.get("at", ""))
                    if max_date and rv_date and rv_date > max_date:
                        continue
                    if min_date and rv_date and rv_date < min_date:
                        continue
                records.append(r)
        except Exception as exc:
            logger.warning("[benchmark] failed to load %s: %s", f.name, exc)
    return records


def compute_rates(records: list[dict]) -> dict[str, float]:
    """
    Compute complaint-normalised issue-type rates (%) from a set of records.
    Denominator = total records - Positive Feedback - Other.
    Returns {issue_type: rate_pct} for tracked issue types only.
    """
    counts: Counter = Counter()
    total = len(records)
    if total == 0:
        return {}

    for r in records:
        it = r.get("issue_type", "")
        counts[it] += 1

    # Complaint denominator
    excluded = sum(counts.get(e, 0) for e in EXCLUDE_FROM_RATES)
    complaint_total = total - excluded
    if complaint_total <= 0:
        return {}

    rates = {}
    for issue in ALL_TRACKED_ISSUES:
        cnt = counts.get(issue, 0)
        rates[issue] = round(cnt / complaint_total * 100, 2)
    return rates


def get_dominant_severity(records: list[dict], issue_type: str) -> str:
    """Return the dominant non-P2 severity class for an issue type, or P2."""
    sev_counts: Counter = Counter()
    for r in records:
        if r.get("issue_type") == issue_type:
            sev = r.get("severity_class", "P2")
            sev_counts[sev] += 1
    for sev in ("P0", "P1", "P2"):
        if sev_counts.get(sev, 0) > 0:
            return sev
    return "P2"


# ── Benchmark computation ─────────────────────────────────────────────────────

def compute_benchmark(
    max_date: str | None = None,
    min_date: str | None = None,
) -> dict:
    """
    Compute issue-type rates for all competitors + peer averages.

    peer_avg / incumbent_avg — NatWest, Lloyds, HSBC only (Barclays' real competitive set).
    Zero-record peers excluded from averages rather than contributing 0.0.
    neobank_avg — Monzo + Revolut separately.

    Returns full benchmark dict, also writes to BENCHMARK_CACHE.
    """
    all_rates: dict[str, dict] = {}
    all_records: dict[str, list] = {}

    competitors = ["barclays"] + PEERS
    for comp in competitors:
        recs = load_competitor_records(comp, max_date=max_date, min_date=min_date)
        all_records[comp] = recs
        all_rates[comp] = compute_rates(recs)
        logger.debug("[benchmark] %s: %d records, %d rates computed",
                     comp, len(recs), len(all_rates[comp]))

    def _peer_avg(group: list[str]) -> dict[str, float]:
        avg: dict[str, float] = {}
        for issue in ALL_TRACKED_ISSUES:
            vals = [
                all_rates[p].get(issue, 0.0)
                for p in group
                if p in all_rates and len(all_records[p]) > 0
            ]
            avg[issue] = round(sum(vals) / len(vals), 2) if vals else 0.0
        return avg

    incumbent_avg = _peer_avg(INCUMBENT_PEERS)
    neobank_avg   = _peer_avg(NEOBANK_PEERS)
    peer_avg      = incumbent_avg  # backward-compat alias

    def _split(rates: dict) -> dict:
        return {
            "technical": {k: v for k, v in rates.items() if k in TECHNICAL_ISSUES},
            "service":   {k: v for k, v in rates.items() if k in SERVICE_ISSUES},
        }

    result = {
        "computed_at":    (max_date or _date.today().isoformat()),
        "competitors":    {c: _split(all_rates[c]) for c in competitors},
        "peer_avg":       _split(peer_avg),        # incumbent avg — backward compat
        "incumbent_avg":  _split(incumbent_avg),
        "neobank_avg":    _split(neobank_avg),
        "record_counts":  {c: len(all_records[c]) for c in competitors},
        "window":         {"min_date": min_date, "max_date": max_date or _date.today().isoformat()},
    }

    BENCHMARK_CACHE.write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return result


# ── Persistence log ───────────────────────────────────────────────────────────

def load_persistence_log() -> list[dict]:
    if not PERSISTENCE_LOG.exists():
        return []
    entries = []
    for line in PERSISTENCE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _get_previous_entry(
    log: list[dict],
    issue_type: str,
    before_date: str,
) -> dict | None:
    """Return the most recent log entry for an issue_type before a given date."""
    candidates = [
        e for e in log
        if e["issue_type"] == issue_type and e["date"] < before_date
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda e: e["date"])


def update_persistence_log(
    run_date: str,
    barclays_rates: dict[str, float],
    peer_avg: dict[str, float],
    barclays_records: list[dict],
    existing_log: list[dict],
) -> tuple[list[dict], float]:
    """
    Append today's entries to the persistence log.
    Returns (new_entries, churn_risk_score).
    """
    new_entries: list[dict] = []
    churn_risk_score = 0.0

    for issue in ALL_TRACKED_ISSUES:
        b_rate   = barclays_rates.get(issue, 0.0)
        p_rate   = peer_avg.get(issue, 0.0)
        gap_pp   = round(b_rate - p_rate, 2)
        over     = gap_pp > 0
        category = "technical" if issue in TECHNICAL_ISSUES else "service"
        severity = get_dominant_severity(barclays_records, issue)

        # Compute days_active from previous entry
        prev = _get_previous_entry(existing_log + new_entries, issue, run_date)
        if prev and prev.get("over_indexed") and over:
            try:
                gap_days = (_date.fromisoformat(run_date) - _date.fromisoformat(prev["date"])).days
            except ValueError:
                gap_days = 1
            if gap_days <= STREAK_GAP_TOLERANCE:
                # Normal daily (gap=1) or one missed run (gap=2) — carry streak
                days_active = prev["days_active"] + gap_days
                first_seen  = prev["first_seen"]
            else:
                days_active = 1
                first_seen  = run_date
        else:
            days_active = 1 if over else 0
            first_seen  = run_date if over else ""

        entry = {
            "date":           run_date,
            "issue_type":     issue,
            "category":       category,
            "barclays_rate":  b_rate,
            "peer_avg_rate":  p_rate,
            "gap_pp":         gap_pp,
            "over_indexed":   over,
            "dominant_severity": severity,
            "days_active":    days_active,
            "first_seen":     first_seen,
        }
        new_entries.append(entry)

        # Accumulate churn risk for over-indexed issues
        if over and days_active > 0:
            sw   = SEVERITY_WEIGHTS.get(severity, 1.0)
            pm   = min(1.0 + PERSISTENCE_STEP * days_active, PERSISTENCE_CAP)
            churn_risk_score += gap_pp * sw * pm

    return new_entries, round(churn_risk_score, 2)


def compute_trend(run_date: str, current_score: float, log: list[dict]) -> str:
    """
    7-day vs 14-day churn score trend using linear regression slope.
    Returns WORSENING / STABLE / IMPROVING, or INSUFFICIENT_DATA.
    Requires at least 14 distinct prior dates.

    Linear slope over the full 21-day window (14 prior + today):
      positive slope > threshold → WORSENING
      negative slope < -threshold → IMPROVING
      otherwise → STABLE

    Falls back to simple mean comparison if scipy unavailable.
    """
    scores_by_date: dict[str, float] = {}
    for entry in log:
        d = entry["date"]
        if d < run_date and entry.get("over_indexed"):
            sw = SEVERITY_WEIGHTS.get(entry.get("dominant_severity", "P2"), 1.0)
            pm = min(1.0 + PERSISTENCE_STEP * entry.get("days_active", 1), PERSISTENCE_CAP)
            scores_by_date[d] = scores_by_date.get(d, 0.0) + (
                entry["gap_pp"] * sw * pm
            )

    past_dates = sorted(scores_by_date.keys(), reverse=True)
    if len(past_dates) < 14:
        return "INSUFFICIENT_DATA"

    # 21-day window: 14 prior dates + today
    window_dates = sorted(past_dates[:14])
    window_scores = [scores_by_date[d] for d in window_dates]

    try:
        from scipy.stats import linregress
        xs = list(range(len(window_scores)))
        slope, _, _, _, _ = linregress(xs, window_scores)
        # Threshold: >1 point/day = meaningful trend
        if slope > 1.0:
            return "WORSENING"
        elif slope < -1.0:
            return "IMPROVING"
        return "STABLE"
    except ImportError:
        # Fallback: 7d vs 14d mean comparison
        recent_7 = window_scores[-7:]
        prior_7  = window_scores[:7]
        avg_r = sum(recent_7) / len(recent_7)
        avg_p = sum(prior_7) / len(prior_7)
        if avg_p == 0:
            return "INSUFFICIENT_DATA"
        delta_pct = (avg_r - avg_p) / avg_p * 100
        if delta_pct > 10:
            return "WORSENING"
        elif delta_pct < -10:
            return "IMPROVING"
        return "STABLE"


# ── Run modes ─────────────────────────────────────────────────────────────────

def run_daily() -> dict:
    """
    Daily mode — update persistence log for today.
    Returns {churn_risk_score, churn_risk_trend, over_indexed, under_indexed}.
    """
    today        = _date.today().isoformat()
    window_start = (_date.today() - timedelta(days=BENCHMARK_WINDOW_DAYS)).isoformat()
    logger.info("[benchmark] daily mode — date=%s window=%s to %s", today, window_start, today)

    # Compute benchmark over rolling 90-day window
    bm = compute_benchmark(min_date=window_start)
    barclays_records = load_competitor_records("barclays", min_date=window_start)
    barclays_rates: dict[str, float] = {}
    for cat in ("technical", "service"):
        barclays_rates.update(bm["competitors"]["barclays"][cat])

    peer_avg: dict[str, float] = {}
    for cat in ("technical", "service"):
        peer_avg.update(bm["peer_avg"][cat])

    existing_log = load_persistence_log()

    # Remove any existing entries for today (idempotent re-runs)
    existing_log = [e for e in existing_log if e["date"] != today]

    new_entries, raw_score = update_persistence_log(
        today, barclays_rates, peer_avg, barclays_records, existing_log
    )
    score = min(round(raw_score / CHURN_SCORE_CAP * 100, 1), 100.0)

    trend = compute_trend(today, raw_score, existing_log)

    # Write updated log
    all_entries = existing_log + new_entries
    PERSISTENCE_LOG.write_text(
        "\n".join(json.dumps(e) for e in all_entries) + "\n",
        encoding="utf-8",
    )

    over_indexed  = [e for e in new_entries if e["over_indexed"] and e["gap_pp"] > 0]
    under_indexed = [e for e in new_entries if not e["over_indexed"] and e["barclays_rate"] > 0]

    over_indexed.sort(key=lambda e: e["gap_pp"] * SEVERITY_WEIGHTS.get(e["dominant_severity"], 1.0), reverse=True)
    under_indexed.sort(key=lambda e: e["gap_pp"])  # most negative gap = biggest strength

    logger.info(
        "[benchmark] churn_risk_score=%.1f (raw=%.2f) trend=%s over=%d under=%d",
        score, raw_score, trend, len(over_indexed), len(under_indexed),
    )

    return {
        "churn_risk_score":     score,       # 0-100 normalised
        "churn_risk_score_raw": raw_score,   # raw sum for internal use
        "churn_risk_trend":     trend,
        "over_indexed":         over_indexed,
        "under_indexed":        under_indexed,
        "benchmark":            bm,
    }


def run_backfill() -> None:
    """
    Backfill mode — process all unique run dates from daily_run_log.jsonl.
    Builds full persistence history. Run once at MIL-27 launch.
    """
    if not RUN_LOG.exists():
        logger.error("[backfill] daily_run_log.jsonl not found")
        return

    # Get unique dates in chronological order
    run_dates: list[str] = []
    seen: set[str] = set()
    for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            d = entry.get("date", "")
            if d and d not in seen:
                run_dates.append(d)
                seen.add(d)
        except json.JSONDecodeError:
            pass

    run_dates.sort()
    logger.info("[backfill] processing %d unique run dates: %s to %s",
                len(run_dates), run_dates[0] if run_dates else "?",
                run_dates[-1] if run_dates else "?")

    # Clear existing persistence log (full rebuild)
    all_entries: list[dict] = []

    for run_date in run_dates:
        logger.info("[backfill] processing %s ...", run_date)

        # Compute benchmark with records up to this date
        bm = compute_benchmark(max_date=run_date)

        barclays_records = load_competitor_records("barclays", max_date=run_date)
        barclays_rates: dict[str, float] = {}
        for cat in ("technical", "service"):
            barclays_rates.update(bm["competitors"]["barclays"][cat])

        peer_avg: dict[str, float] = {}
        for cat in ("technical", "service"):
            peer_avg.update(bm["peer_avg"][cat])

        new_entries, score = update_persistence_log(
            run_date, barclays_rates, peer_avg, barclays_records, all_entries
        )
        all_entries.extend(new_entries)

        over_count = sum(1 for e in new_entries if e["over_indexed"])
        logger.info("[backfill] %s — churn_score=%.2f over_indexed=%d",
                    run_date, score, over_count)

    # Write full log
    PERSISTENCE_LOG.write_text(
        "\n".join(json.dumps(e) for e in all_entries) + "\n",
        encoding="utf-8",
    )
    logger.info("[backfill] complete — %d total log entries written", len(all_entries))

    # Recompute benchmark cache with all data (no date filter)
    compute_benchmark()
    logger.info("[backfill] benchmark_cache.json updated with full dataset")


# ── Entry point ───────────────────────────────────────────────────────────────

def run(mode: str = "daily") -> dict:
    """Called from run_daily.py Step 4d."""
    if mode == "backfill":
        run_backfill()
        return {}
    return run_daily()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MIL Benchmark Engine")
    parser.add_argument(
        "--mode",
        choices=["daily", "backfill"],
        default="daily",
        help="daily: update today's persistence log | backfill: rebuild full history",
    )
    args = parser.parse_args()
    run(args.mode)
