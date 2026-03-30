"""
briefing_data.py -- MIL Briefing Data Layer

Computes all dynamic briefing metrics from:
  - mil/outputs/mil_findings.json  (inference findings, last 7 days)
  - mil/data/historical/enriched/  (enriched records with star ratings and dates)

No hardcoded journey lists. All journey detection is dynamic.
Sentiment score = avg star rating (1-5) x 20 -> 0-100 scale.
Trend uses 3-day vs 4-day window split within the 7-day rolling window.

Issue Score formula (per spec):
  Score = Volume x Severity_Weight x Trend_Factor x CHRONICLE_Bonus
  Volume          = number of findings for journey in window
  Severity_Weight = 8*(P0/total) + 3*(P1/total) + 1*(P2/total)
  Trend_Factor    = 1.5 WORSENING | 0.8 IMPROVING | 1.0 STABLE
  CHRONICLE_Bonus = 1.25 CHR-001 | 1.15 CHR-002/CHR-003 | 1.10 CHR-004 | 1.0 none

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
Article Zero: express ignorance before unverified certainty.
"""
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIL_ROOT      = Path(__file__).parent
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"
ENRICHED_DIR  = MIL_ROOT / "data" / "historical" / "enriched"

WINDOW_DAYS   = 7       # Rolling window for all calculations
MIN_RECORDS_FOR_TREND = 5   # Need at least this many records to compute a reliable trend

# Maps journey_category (enrichment schema v2) -> journey_id (MIL schema)
# Used to link enriched record star ratings back to journey_id clusters
JOURNEY_CATEGORY_TO_ID = {
    "Login & Account Access":   "J_LOGIN_01",
    "Password Issues":          "J_LOGIN_01",
    "Failed Transaction":       "J_PAY_01",
    "Transaction Charges":      "J_PAY_01",
    "Account Registration":     "J_ONBOARD_01",
    "App Installation Issues":  "J_ONBOARD_01",
    "App crashes or Slow":      "J_SERVICE_01",
    "App not Opening":          "J_SERVICE_01",
    "Network Failure":          "J_SERVICE_01",
    "Customer Support":         "J_SERVICE_01",
    "Customer Inquiry":         "J_SERVICE_01",
    # These have no journey_id -- excluded from journey performance table
    "UI/UX":          None,
    "Feature Requests": None,
    "General Feedback": None,
    "Other":           None,
    "ENRICHMENT_FAILED": None,
}

# CHRONICLE bonus multipliers for Issue Score formula
CHRONICLE_BONUS = {
    "CHR-001": 1.25,
    "CHR-002": 1.15,
    "CHR-003": 1.15,
    "CHR-004": 1.10,
}


# ============================================================
# DATE UTILITIES
# ============================================================

def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _parse_record_date(record: dict) -> Optional[date]:
    """
    Parse review date from enriched record.
    App Store uses 'date' field (ISO string).
    Google Play uses 'at' field (ISO string or datetime object).
    Returns None if field absent or unparseable.
    """
    raw = record.get("date") or record.get("at")
    if raw is None:
        return None
    try:
        if isinstance(raw, (date, datetime)):
            return raw.date() if isinstance(raw, datetime) else raw
        raw_str = str(raw)[:10]   # take YYYY-MM-DD prefix only
        return date.fromisoformat(raw_str)
    except Exception:
        return None


def _parse_finding_date(finding: dict) -> Optional[date]:
    """Parse generated_at timestamp from a finding dict."""
    raw = finding.get("generated_at", "")
    try:
        return datetime.fromisoformat(str(raw)).date()
    except Exception:
        return None


# ============================================================
# DATA LOADERS
# ============================================================

def _load_findings(window_days: int = WINDOW_DAYS) -> list[dict]:
    """
    Load findings from mil_findings.json generated within the last window_days.
    Returns both anchored and unanchored findings (caller filters as needed).
    """
    if not FINDINGS_FILE.exists():
        logger.warning("[BriefingData] mil_findings.json not found")
        return []

    raw = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
    cutoff = _today_utc() - timedelta(days=window_days)

    all_findings = raw.get("findings", []) + raw.get("unanchored_signals", [])
    in_window = []
    for f in all_findings:
        fdate = _parse_finding_date(f)
        if fdate is None or fdate >= cutoff:
            in_window.append(f)

    logger.debug("[BriefingData] Loaded %d findings within %d-day window", len(in_window), window_days)
    return in_window


def _load_enriched_records(window_days: int = WINDOW_DAYS) -> list[dict]:
    """
    Load enriched review records from all enriched JSON files
    where the review date falls within the last window_days.
    Attaches 'competitor_key' and 'review_date' to each record.
    """
    today    = _today_utc()
    cutoff   = today - timedelta(days=window_days)
    records  = []

    for f in sorted(ENRICHED_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[BriefingData] Failed to read %s: %s", f.name, exc)
            continue

        competitor_key = f"{payload.get('source', '?')}_{payload.get('competitor', '?')}"
        for r in payload.get("records", []):
            rdate = _parse_record_date(r)
            if rdate is None or rdate < cutoff:
                continue
            records.append({**r, "_competitor_key": competitor_key, "_review_date": rdate})

    logger.debug("[BriefingData] Loaded %d enriched records within %d-day window",
                 len(records), window_days)
    return records


# ============================================================
# SENTIMENT CALCULATIONS
# ============================================================

def _star_to_sentiment(ratings: list[float]) -> int:
    """
    Convert list of 1-5 star ratings to 0-100 sentiment score.
    Formula: avg_rating x 20, rounded to nearest int.
    Returns -1 if no ratings available (caller should render as 'N/A').
    """
    valid = [r for r in ratings if r is not None and 1 <= r <= 5]
    if not valid:
        return -1
    return round(sum(valid) / len(valid) * 20)


def _compute_trend(records_7d: list[dict], today: date) -> str:
    """
    Compare current 3-day average star rating vs earlier 4-day average.

    Window split:
      earlier_4d : [today-6, today-3]  (days 7,6,5,4 ago)
      current_3d : [today-2, today]    (days 3,2,1 ago including today)

    WORSENING if current_3d_avg < earlier_4d_avg - 5 points (on 0-100 scale)
    IMPROVING if current_3d_avg > earlier_4d_avg + 5 points
    STABLE    otherwise

    Returns 'STABLE' with a note if insufficient data for either window.
    """
    split = today - timedelta(days=3)   # records on/after this date = current 3-day

    earlier = [r["rating"] for r in records_7d
               if r.get("rating") and r["_review_date"] < split]
    current = [r["rating"] for r in records_7d
               if r.get("rating") and r["_review_date"] >= split]

    if len(earlier) < MIN_RECORDS_FOR_TREND or len(current) < MIN_RECORDS_FOR_TREND:
        return "STABLE"     # Article Zero: insufficient data -> do not assert direction

    earlier_score = _star_to_sentiment(earlier)
    current_score = _star_to_sentiment(current)

    if current_score < earlier_score - 5:
        return "WORSENING"
    if current_score > earlier_score + 5:
        return "IMPROVING"
    return "STABLE"


# ============================================================
# ISSUE SCORE FORMULA
# ============================================================

def _severity_weight(p0: int, p1: int, p2: int) -> float:
    """
    Severity Weight = 8*(P0/total) + 3*(P1/total) + 1*(P2/total)
    Returns 1.0 (P2 floor) if no signals.
    """
    total = p0 + p1 + p2
    if total == 0:
        return 1.0
    return 8 * (p0 / total) + 3 * (p1 / total) + 1 * (p2 / total)


def _chronicle_bonus(chronicle_ids: set) -> float:
    """
    Return highest applicable CHRONICLE bonus from the set of matched CHR IDs.
    Only uses the single highest multiplier (not additive).
    """
    best = 1.0
    for cid in chronicle_ids:
        best = max(best, CHRONICLE_BONUS.get(cid, 1.0))
    return best


def _issue_score(
    volume: int,
    p0: int,
    p1: int,
    p2: int,
    trend: str,
    chronicle_ids: set,
) -> float:
    """
    Issue Score = Volume x Severity_Weight x Trend_Factor x CHRONICLE_Bonus

    All four components documented inline.
    """
    # 1. Volume: raw count of findings in window for this journey
    vol = volume

    # 2. Severity Weight: P0 signals weighted 8x, P1 3x, P2 1x
    sev_weight = _severity_weight(p0, p1, p2)

    # 3. Trend Factor: amplifies score when signal is worsening
    trend_factor = {"WORSENING": 1.5, "IMPROVING": 0.8}.get(trend, 1.0)

    # 4. CHRONICLE Bonus: historical precedent elevates risk signal
    chron_bonus = _chronicle_bonus(chronicle_ids)

    score = vol * sev_weight * trend_factor * chron_bonus
    return round(score, 4)


# ============================================================
# VERDICT GENERATOR (deterministic -- no model call)
# ============================================================

_VERDICT_TEMPLATES = {
    ("WORSENING", "P0"): "{journey} signals worsening -- {n_p0} complete-block reports across {competitors}.",
    ("WORSENING", "P1"): "{journey} friction increasing -- {n_p1} friction reports, trend declining.",
    ("WORSENING", "P2"): "{journey} minor degradation -- trend worsening but severity low.",
    ("STABLE",    "P0"): "{journey} has {n_p0} complete-block reports -- stable volume, requires monitoring.",
    ("STABLE",    "P1"): "{journey} showing {n_p1} friction signals -- volume stable.",
    ("STABLE",    "P2"): "{journey} stable with minor issues only.",
    ("IMPROVING", "P0"): "{journey} improving -- {n_p0} P0 reports but trend positive.",
    ("IMPROVING", "P1"): "{journey} friction easing -- {n_p1} friction reports, trend positive.",
    ("IMPROVING", "P2"): "{journey} performing well and improving.",
}

def _verdict(journey_id: str, trend: str, p0: int, p1: int, p2: int, competitors: list) -> str:
    """Build a short one-sentence verdict from structured data. No model calls."""
    dominant = "P0" if p0 > 0 else ("P1" if p1 > 0 else "P2")
    template = _VERDICT_TEMPLATES.get((trend, dominant),
               "{journey} -- {n_findings} signals in window, trend {trend}.")
    return template.format(
        journey=journey_id,
        trend=trend.lower(),
        n_p0=p0,
        n_p1=p1,
        n_findings=p0 + p1 + p2,
        competitors=", ".join(sorted(set(competitors))[:3]),
    )


# ============================================================
# MAIN BRIEFING DATA FUNCTION
# ============================================================

def get_briefing_data(window_days: int = WINDOW_DAYS) -> dict:
    """
    Compute and return the full briefing data dictionary.

    All sections are dynamic -- no hardcoded journey lists or competitors.
    Returns the structure required by publish.py and the dashboard.
    """
    today      = _today_utc()
    window_end = today
    window_start = today - timedelta(days=window_days)

    findings      = _load_findings(window_days)
    enr_records   = _load_enriched_records(window_days)

    generated_at = datetime.now(timezone.utc).isoformat()

    # ----------------------------------------------------------
    # SECTION 1: OVERALL SENTIMENT
    # Sentiment Score = avg star rating across all records in window x 20
    # Trend = compare current 3-day vs earlier 4-day split
    # ----------------------------------------------------------
    all_ratings   = [r["rating"] for r in enr_records if r.get("rating")]
    overall_score = _star_to_sentiment(all_ratings)
    overall_trend = _compute_trend(enr_records, today)

    # Baseline: the avg rating over the full enriched corpus (all dates) for comparison
    # Load all records regardless of date for baseline
    baseline_ratings = []
    for f in sorted(ENRICHED_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            baseline_ratings.extend(
                r["rating"] for r in payload.get("records", []) if r.get("rating")
            )
        except Exception:
            pass
    baseline_score = _star_to_sentiment(baseline_ratings) if baseline_ratings else "Establishing"

    overall_sentiment = {
        "score":    overall_score if overall_score >= 0 else "N/A",
        "trend":    overall_trend,
        "baseline": baseline_score,
        "n_records": len(all_ratings),
        "window":   f"{window_start.isoformat()} to {window_end.isoformat()}",
    }

    # ----------------------------------------------------------
    # SECTION 2: JOURNEY PERFORMANCE
    # Dynamically detect all unique journey_ids from findings in window.
    # Compute per-journey: sentiment (star ratings), trend, issue score.
    # Return top 5 by issue score descending.
    # ----------------------------------------------------------

    # Group findings by journey_id (fully dynamic -- no hardcoded list)
    journey_findings: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        jid = f.get("journey_id")
        if jid and jid != "UNMAPPED":
            journey_findings[jid].append(f)

    # Group enriched records by journey_id for per-journey star ratings
    journey_records: dict[str, list[dict]] = defaultdict(list)
    for r in enr_records:
        jid = JOURNEY_CATEGORY_TO_ID.get(r.get("journey_category", ""), None)
        if jid:
            journey_records[jid].append(r)

    journey_rows = []
    for journey_id, jfindings in journey_findings.items():
        # Aggregate signal counts across all findings for this journey
        total_p0 = sum(f["signal_counts"]["P0"] for f in jfindings)
        total_p1 = sum(f["signal_counts"]["P1"] for f in jfindings)
        total_p2 = sum(f["signal_counts"]["P2"] for f in jfindings)

        # CHRONICLE IDs matched for this journey (for bonus calc)
        chronicle_ids = {
            f["provenance"]["chronicle_id"]
            for f in jfindings
            if f["provenance"].get("chronicle_id")
        }

        # Sentiment from star ratings for this specific journey
        j_ratings    = [r["rating"] for r in journey_records.get(journey_id, [])
                        if r.get("rating")]
        j_sentiment  = _star_to_sentiment(j_ratings) if j_ratings else overall_score
        j_trend      = _compute_trend(journey_records.get(journey_id, []), today)

        # Issue Score (full formula)
        i_score = _issue_score(
            volume=len(jfindings),
            p0=total_p0, p1=total_p1, p2=total_p2,
            trend=j_trend,
            chronicle_ids=chronicle_ids,
        )

        competitors = list({f["competitor"] for f in jfindings})

        journey_rows.append({
            "journey":         journey_id,
            "sentiment_score": j_sentiment if j_sentiment >= 0 else overall_score,
            "trend":           j_trend,
            "issue_score":     i_score,
            "p0":              total_p0,
            "p1":              total_p1,
            "p2":              total_p2,
            "n_findings":      len(jfindings),
            "chronicle_ids":   sorted(chronicle_ids),
            "competitors":     sorted(competitors),
            "_verdict_raw":    (j_trend, total_p0, total_p1, total_p2, competitors),
        })

    # Sort by issue score descending, take top 5
    journey_rows.sort(key=lambda x: -x["issue_score"])
    journey_performance = []
    for rank, row in enumerate(journey_rows[:5], start=1):
        trend, p0, p1, p2, competitors = row.pop("_verdict_raw")
        journey_performance.append({
            "rank":            rank,
            "journey":         row["journey"],
            "sentiment_score": row["sentiment_score"],
            "trend":           row["trend"],
            "issue_score":     row["issue_score"],
            "p0":              row["p0"],
            "p1":              row["p1"],
            "p2":              row["p2"],
            "chronicle_ids":   row["chronicle_ids"],
            "verdict":         _verdict(row["journey"], row["trend"], p0, p1, p2, competitors),
        })

    # ----------------------------------------------------------
    # SECTION 3: ISSUES STATUS
    # needs_attention = anchored findings, Clark P1 OR Designed Ceiling
    # watch           = anchored findings, Clark P2
    # performing_well = everything else (P3, unanchored)
    # ----------------------------------------------------------
    needs_attention = sum(
        1 for f in findings
        if not f.get("is_unanchored")
        and (f.get("finding_tier") == "P1" or f.get("designed_ceiling_reached"))
    )
    watch = sum(
        1 for f in findings
        if not f.get("is_unanchored")
        and f.get("finding_tier") == "P2"
        and not f.get("designed_ceiling_reached")
    )
    performing_well = len(findings) - needs_attention - watch

    issues_status = {
        "needs_attention": needs_attention,
        "watch":           watch,
        "performing_well": max(performing_well, 0),
    }

    # ----------------------------------------------------------
    # SECTION 4: COMPETITOR TICKER
    # Per competitor: sentiment score, trend, top journey (highest issue score)
    # Dynamically detected from enriched records and findings.
    # ----------------------------------------------------------
    competitor_records: dict[str, list[dict]] = defaultdict(list)
    for r in enr_records:
        # competitor_key = 'app_store_lloyds' -> extract competitor suffix
        ck = r.get("_competitor_key", "")
        competitor = ck   # keep full key for dedup; strip source prefix below
        for src in ("app_store_", "google_play_", "trustpilot_", "reddit_", "youtube_"):
            if ck.startswith(src):
                competitor = ck[len(src):]
                break
        competitor_records[competitor].append(r)

    # Per-competitor top journey from findings
    competitor_top_journey: dict[str, str] = {}
    competitor_findings: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        if not f.get("is_unanchored"):
            competitor_findings[f["competitor"]].append(f)
    for comp, cfindings in competitor_findings.items():
        if cfindings:
            top = max(cfindings, key=lambda x: x.get("confidence_score", 0))
            competitor_top_journey[comp] = top.get("journey_id", "")

    competitor_ticker = []
    for comp, crecs in sorted(competitor_records.items()):
        ratings = [r["rating"] for r in crecs if r.get("rating")]
        score   = _star_to_sentiment(ratings) if ratings else -1
        trend   = _compute_trend(crecs, today)
        competitor_ticker.append({
            "competitor":   comp,
            "score":        score if score >= 0 else "N/A",
            "trend":        trend,
            "top_journey":  competitor_top_journey.get(comp, ""),
            "n_records":    len(crecs),
        })
    # Sort by score ascending (most troubled first)
    competitor_ticker.sort(key=lambda x: x["score"] if isinstance(x["score"], int) else 999)

    # ----------------------------------------------------------
    # SECTION 5: TOP FINDINGS
    # Top 5 anchored findings by confidence_score.
    # ----------------------------------------------------------
    anchored = [f for f in findings if not f.get("is_unanchored")]
    top_findings = []
    for f in sorted(anchored, key=lambda x: -x.get("confidence_score", 0))[:5]:
        summary = f.get("finding_summary", "")
        top_findings.append({
            "finding_id":       f["finding_id"],
            "competitor":       f["competitor"],
            "journey_id":       f.get("journey_id", ""),
            "confidence_score": f.get("confidence_score"),
            "signal_severity":  f.get("signal_severity"),
            "finding_tier":     f.get("finding_tier"),
            "chronicle_id":     f["provenance"].get("chronicle_id"),
            "designed_ceiling": f.get("designed_ceiling_reached", False),
            "p0":               f["signal_counts"]["P0"],
            "p1":               f["signal_counts"]["P1"],
            "p2":               f["signal_counts"]["P2"],
            "summary":          summary[:120],
        })

    # ----------------------------------------------------------
    # SECTION 6: EXECUTIVE ALERT
    # Highest-severity anchored finding overall.
    # Designed Ceiling findings surface first if they have P0/P1 signals.
    # ----------------------------------------------------------
    def _alert_priority(f: dict) -> tuple:
        # Sort key: (has_p0, designed_ceiling, confidence_score)
        return (
            f["signal_counts"]["P0"] > 0,
            f.get("designed_ceiling_reached", False),
            f.get("confidence_score", 0),
        )

    exec_candidates = [f for f in anchored
                       if f["signal_counts"]["P0"] + f["signal_counts"]["P1"] > 0]
    executive_alert = {}
    if exec_candidates:
        top = max(exec_candidates, key=_alert_priority)
        blind_spots = top.get("blind_spots", [])
        executive_alert = {
            "finding_id":         top["finding_id"],
            "competitor":         top["competitor"],
            "journey_id":         top.get("journey_id", ""),
            "confidence_score":   top.get("confidence_score"),
            "signal_severity":    top.get("signal_severity"),
            "finding_tier":       top.get("finding_tier"),
            "chronicle_id":       top["provenance"].get("chronicle_id"),
            "designed_ceiling":   top.get("designed_ceiling_reached", False),
            "p0":                 top["signal_counts"]["P0"],
            "p1":                 top["signal_counts"]["P1"],
            "summary":            top.get("finding_summary", "")[:160],
            "primary_blind_spot": blind_spots[0] if blind_spots else "",
            "action_required":    (
                "To confirm this I require internal HDFS telemetry data. Request Phase 2."
                if top.get("designed_ceiling_reached")
                else "Monitor signal volume. Await human countersign before escalation."
            ),
        }
    else:
        executive_alert = {
            "finding_id":       None,
            "summary":          "No P0/P1 anchored findings in current window.",
            "action_required":  "No immediate action required.",
        }

    # ----------------------------------------------------------
    # ASSEMBLE FINAL OUTPUT
    # ----------------------------------------------------------
    return {
        "generated_at":       generated_at,
        "window_days":        window_days,
        "overall_sentiment":  overall_sentiment,
        "journey_performance": journey_performance,
        "issues_status":      issues_status,
        "competitor_ticker":  competitor_ticker,
        "top_findings":       top_findings,
        "executive_alert":    executive_alert,
    }


# ============================================================
# TEST BLOCK
# ============================================================

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("Running MIL Briefing Data Layer...")
    print()
    data = get_briefing_data()
    print(json.dumps(data, indent=2, default=str))
