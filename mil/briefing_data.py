"""
briefing_data.py -- MIL Briefing Data Layer (v2 -- fully dynamic journeys)

Primary data source: mil/data/historical/enriched/*.json
  - Records grouped by journey_category (raw Refuel output -- no hardcoded list)
  - Sentiment: avg star rating x 20 -> 0-100
  - Severity: P0/P1/P2 from enriched record severity_class field
  - Trend: 3-day vs 4-day split within 7-day rolling window

Secondary source: mil/outputs/mil_findings.json
  - CHRONICLE bonus lookup (CHR-001/002/003/004)
  - Top findings and executive alert

Journey grouping is fully dynamic: whatever journey_category values Refuel
produced are the labels. Nothing is hardcoded or remapped in the output.

Issue Score = Volume x Severity_Weight x Trend_Factor x CHRONICLE_Bonus
  Volume          = enriched records with that journey_category in window
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

WINDOW_DAYS = 7
MIN_RECORDS_FOR_TREND = 5  # minimum to compute a reliable 3d/4d trend

# Internal lookup only: maps journey_category -> journey_id for CHRONICLE bonus.
# Never used as an output label -- output always uses the raw journey_category string.
_CATEGORY_TO_JID = {
    "Login & Account Access":  "J_LOGIN_01",
    "Password Issues":         "J_LOGIN_01",
    "Failed Transaction":      "J_PAY_01",
    "Transaction Charges":     "J_PAY_01",
    "Account Registration":    "J_ONBOARD_01",
    "App Installation Issues": "J_ONBOARD_01",
    "App crashes or Slow":     "J_SERVICE_01",
    "App not Opening":         "J_SERVICE_01",
    "Network Failure":         "J_SERVICE_01",
    "Customer Support":        "J_SERVICE_01",
    "Customer Inquiry":        "J_SERVICE_01",
}

# CHRONICLE bonus multipliers (Issue Score formula)
_CHRONICLE_BONUS = {
    "CHR-001": 1.25,
    "CHR-002": 1.15,
    "CHR-003": 1.15,
    "CHR-004": 1.10,
}


# ============================================================
# DATE UTILITIES
# ============================================================

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_record_date(r: dict) -> Optional[date]:
    """App Store uses 'date', Google Play uses 'at'. Both are ISO strings."""
    raw = r.get("date") or r.get("at")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except Exception:
        return None


def _parse_finding_date(f: dict) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(f.get("generated_at", ""))).date()
    except Exception:
        return None


# ============================================================
# DATA LOADERS
# ============================================================

def _load_enriched_records(window_days: int = WINDOW_DAYS) -> list[dict]:
    """
    Load enriched records from all files where review date is within window.
    Attaches _competitor, _review_date to each record for downstream use.
    Drops ENRICHMENT_FAILED records (no reliable classification).
    """
    cutoff  = _today() - timedelta(days=window_days)
    records = []

    for f in sorted(ENRICHED_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[BriefingData] Cannot read %s: %s", f.name, exc)
            continue

        # Derive competitor name from payload fields
        source     = payload.get("source", "")
        competitor = payload.get("competitor", "")

        for r in payload.get("records", []):
            # Drop failed enrichments
            if r.get("severity_class") == "ENRICHMENT_FAILED":
                continue
            if r.get("journey_category") == "ENRICHMENT_FAILED":
                continue

            rdate = _parse_record_date(r)
            if rdate is None or rdate < cutoff:
                continue

            records.append({
                **r,
                "_competitor": competitor,
                "_source":     source,
                "_review_date": rdate,
            })

    logger.debug("[BriefingData] %d records in %d-day window", len(records), window_days)
    return records


def _load_findings(window_days: int = WINDOW_DAYS) -> list[dict]:
    """Load findings generated within the last window_days."""
    if not FINDINGS_FILE.exists():
        return []
    raw     = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
    cutoff  = _today() - timedelta(days=window_days)
    all_f   = raw.get("findings", []) + raw.get("unanchored_signals", [])
    return [f for f in all_f
            if (fdate := _parse_finding_date(f)) is None or fdate >= cutoff]


# ============================================================
# SENTIMENT
# ============================================================

def _star_sentiment(ratings: list) -> int:
    """avg star rating (1-5) x 20 -> 0-100. Returns -1 if no data."""
    valid = [r for r in ratings if r is not None and 1 <= r <= 5]
    if not valid:
        return -1
    return round(sum(valid) / len(valid) * 20)


def _trend(records: list[dict], today: date) -> str:
    """
    Compare current 3-day avg vs earlier 4-day avg on 0-100 scale.
    Split point: today - 3 days.
      earlier_4d  = records dated [today-6 .. today-3)
      current_3d  = records dated [today-2 .. today]
    Returns STABLE when insufficient data for either window.
    """
    split   = today - timedelta(days=3)
    earlier = [r["rating"] for r in records
               if r.get("rating") and r["_review_date"] < split]
    current = [r["rating"] for r in records
               if r.get("rating") and r["_review_date"] >= split]

    if len(earlier) < MIN_RECORDS_FOR_TREND or len(current) < MIN_RECORDS_FOR_TREND:
        return "STABLE"

    e_score = _star_sentiment(earlier)
    c_score = _star_sentiment(current)

    if c_score < e_score - 5:
        return "WORSENING"
    if c_score > e_score + 5:
        return "IMPROVING"
    return "STABLE"


# ============================================================
# ISSUE SCORE FORMULA
# ============================================================

def _severity_weight(p0: int, p1: int, p2: int) -> float:
    """
    Severity Weight = 8*(P0/total) + 3*(P1/total) + 1*(P2/total)
    Floor at 1.0 (pure P2 = 1.0). Zero records = 1.0.
    """
    total = p0 + p1 + p2
    if total == 0:
        return 1.0
    return 8 * (p0 / total) + 3 * (p1 / total) + 1 * (p2 / total)


def _chronicle_bonus(chronicle_ids: set) -> float:
    """Highest applicable CHRONICLE bonus -- not additive, single max."""
    return max((_CHRONICLE_BONUS.get(cid, 1.0) for cid in chronicle_ids), default=1.0)


def _issue_score(volume: int, p0: int, p1: int, p2: int,
                 trend: str, chronicle_ids: set) -> float:
    """
    Issue Score = Volume x Severity_Weight x Trend_Factor x CHRONICLE_Bonus
    """
    sev    = _severity_weight(p0, p1, p2)
    tf     = {"WORSENING": 1.5, "IMPROVING": 0.8}.get(trend, 1.0)
    bonus  = _chronicle_bonus(chronicle_ids)
    return round(volume * sev * tf * bonus, 4)


# ============================================================
# CHRONICLE LOOKUP (internal -- not exposed in output labels)
# ============================================================

def _build_journey_chronicle_map(findings: list[dict]) -> dict[str, set]:
    """
    Returns {journey_id: {chronicle_ids}} from anchored findings.
    Used only to assign CHRONICLE bonus -- not used for output labels.
    """
    jmap: dict[str, set] = defaultdict(set)
    for f in findings:
        if f.get("is_unanchored"):
            continue
        jid  = f.get("journey_id")
        cid  = f.get("provenance", {}).get("chronicle_id")
        if jid and cid:
            jmap[jid].add(cid)
    return jmap


# ============================================================
# VERDICT (deterministic)
# ============================================================

def _verdict(journey: str, trend: str, p0: int, p1: int, p2: int) -> str:
    total = p0 + p1 + p2
    if p0 > 0 and trend == "WORSENING":
        return f"{journey} -- {p0} complete-block signals, trend worsening."
    if p0 > 0:
        return f"{journey} -- {p0} complete-block signals, volume stable."
    if p1 > 0 and trend == "WORSENING":
        return f"{journey} -- {p1} friction reports, trend declining."
    if p1 > 0:
        return f"{journey} -- {p1} friction signals, monitoring required."
    if trend == "IMPROVING":
        return f"{journey} -- {total} signals, trend improving."
    return f"{journey} -- {total} signals, minor issues only."


# ============================================================
# MAIN
# ============================================================

def get_briefing_data(window_days: int = WINDOW_DAYS) -> dict:
    """
    Compute and return the full MIL briefing data dictionary.

    Journeys are fully dynamic: grouped by raw journey_category strings
    from Refuel enrichment. No remapping, no hardcoded list.
    """
    today    = _today()
    cutoff   = today - timedelta(days=window_days)
    records  = _load_enriched_records(window_days)
    findings = _load_findings(window_days)

    # CHRONICLE bonus lookup map (journey_id -> set of chronicle_ids from findings)
    jid_chronicles = _build_journey_chronicle_map(findings)

    # ----------------------------------------------------------
    # SECTION 1: OVERALL SENTIMENT
    # Equal-weight per competitor: prevents dense scrapes (e.g. 334 Revolut records)
    # from dominating competitors with sparser recent coverage (e.g. 25 Monzo records).
    # ----------------------------------------------------------
    comp_ratings: dict[str, list] = defaultdict(list)
    for r in records:
        comp = r.get("_competitor")
        if comp and r.get("rating"):
            comp_ratings[comp].append(r["rating"])

    comp_scores = [_star_sentiment(v) for v in comp_ratings.values() if v]
    overall_score = round(sum(s for s in comp_scores if s >= 0) / len([s for s in comp_scores if s >= 0])) if comp_scores else -1

    all_ratings   = [r["rating"] for r in records if r.get("rating")]  # kept for trend calc only
    overall_trend = _trend(records, today)

    # Baseline: full corpus avg (all dates, all files)
    baseline_ratings = []
    for f in sorted(ENRICHED_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            baseline_ratings.extend(
                r["rating"] for r in payload.get("records", [])
                if r.get("rating") and r.get("severity_class") != "ENRICHMENT_FAILED"
            )
        except Exception:
            pass
    baseline = _star_sentiment(baseline_ratings) if baseline_ratings else "Establishing"

    overall_sentiment = {
        "score":     overall_score if overall_score >= 0 else "N/A",
        "trend":     overall_trend,
        "baseline":  baseline,
        "n_records": len(all_ratings),
        "window":    f"{cutoff.isoformat()} to {today.isoformat()}",
    }

    # ----------------------------------------------------------
    # SECTION 2: JOURNEY PERFORMANCE
    # Group by raw journey_category. No remapping in output.
    # ----------------------------------------------------------

    # Build per-journey groups from enriched records
    jgroups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        cat = r.get("journey_category") or "Other"
        jgroups[cat].append(r)

    rows = []
    for cat, jrecs in jgroups.items():
        # Skip "Other" / "General Feedback" unless they have P0/P1 signals
        # (keeps the top-5 focused on actionable journeys)
        p0 = sum(1 for r in jrecs if r.get("severity_class") == "P0")
        p1 = sum(1 for r in jrecs if r.get("severity_class") == "P1")
        p2 = sum(1 for r in jrecs if r.get("severity_class") == "P2")

        if cat in ("Other", "General Feedback") and p0 == 0 and p1 == 0:
            continue    # pure noise -- no actionable signal

        vol         = len(jrecs)
        ratings     = [r["rating"] for r in jrecs if r.get("rating")]
        sentiment   = _star_sentiment(ratings) if ratings else overall_score
        j_trend     = _trend(jrecs, today)

        # CHRONICLE bonus: look up via internal journey_id mapping
        jid          = _CATEGORY_TO_JID.get(cat)
        chron_ids    = jid_chronicles.get(jid, set()) if jid else set()
        i_score      = _issue_score(vol, p0, p1, p2, j_trend, chron_ids)

        rows.append({
            "journey":         cat,
            "sentiment_score": sentiment if sentiment >= 0 else overall_score,
            "trend":           j_trend,
            "issue_score":     i_score,
            "p0":              p0,
            "p1":              p1,
            "p2":              p2,
            "volume":          vol,
            "chronicle_ids":   sorted(chron_ids),
        })

    rows.sort(key=lambda x: -x["issue_score"])

    journey_performance = []
    for rank, row in enumerate(rows[:5], 1):
        journey_performance.append({
            "rank":            rank,
            "journey":         row["journey"],
            "sentiment_score": row["sentiment_score"],
            "trend":           row["trend"],
            "issue_score":     row["issue_score"],
            "p0":              row["p0"],
            "p1":              row["p1"],
            "p2":              row["p2"],
            "verdict":         _verdict(row["journey"], row["trend"],
                                        row["p0"], row["p1"], row["p2"]),
        })

    # ----------------------------------------------------------
    # SECTION 3: ISSUES STATUS
    # needs_attention = Clark P1 or Designed Ceiling (anchored only)
    # watch           = Clark P2 (anchored, no ceiling)
    # performing_well = P3 + unanchored
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
    performing_well = max(len(findings) - needs_attention - watch, 0)

    issues_status = {
        "needs_attention": needs_attention,
        "watch":           watch,
        "performing_well": performing_well,
    }

    # ----------------------------------------------------------
    # SECTION 4: COMPETITOR TICKER
    # Per competitor: sentiment score + trend from their enriched records.
    # Top journey = journey_category with highest Issue Score for that competitor.
    # ----------------------------------------------------------
    comp_records: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        comp_records[r["_competitor"]].append(r)

    competitor_ticker = []
    for comp, crecs in sorted(comp_records.items()):
        ratings  = [r["rating"] for r in crecs if r.get("rating")]
        score    = _star_sentiment(ratings)
        c_trend  = _trend(crecs, today)

        # Top journey_category for this competitor by P0+P1 count
        cat_sev: dict[str, int] = defaultdict(int)
        for r in crecs:
            cat = r.get("journey_category") or "Other"
            sev = r.get("severity_class", "P2")
            cat_sev[cat] += (8 if sev == "P0" else 3 if sev == "P1" else 0)
        top_journey = max(cat_sev, key=cat_sev.get) if cat_sev else ""

        competitor_ticker.append({
            "competitor": comp,
            "score":      score if score >= 0 else "N/A",
            "trend":      c_trend,
            "top_journey": top_journey,
            "n_records":  len(crecs),
        })

    competitor_ticker.sort(key=lambda x: x["score"] if isinstance(x["score"], int) else 999)

    # ----------------------------------------------------------
    # SECTION 5: TOP FINDINGS
    # Top 5 anchored findings by confidence_score.
    # ----------------------------------------------------------
    anchored = [f for f in findings if not f.get("is_unanchored")]
    top_findings = []
    for f in sorted(anchored, key=lambda x: -x.get("confidence_score", 0))[:5]:
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
            "summary":          f.get("finding_summary", "")[:120],
        })

    # ----------------------------------------------------------
    # SECTION 6: EXECUTIVE ALERT
    # Always surfaces the top Barclays finding (P0/P1) first.
    # Falls back to highest-priority anchored finding across all competitors
    # only if no qualifying Barclays finding exists.
    # ----------------------------------------------------------
    all_cands = [f for f in anchored
                 if f["signal_counts"]["P0"] + f["signal_counts"]["P1"] > 0]
    barclays_cands = [f for f in all_cands
                      if f.get("competitor", "").lower() == "barclays"]
    exec_cands = barclays_cands if barclays_cands else all_cands

    if exec_cands:
        top = max(exec_cands, key=lambda f: (
            f["signal_counts"]["P0"] > 0,
            f.get("designed_ceiling_reached", False),
            f.get("confidence_score", 0),
        ))
        blind_spots = top.get("blind_spots", [])
        executive_alert = {
            "finding_id":        top["finding_id"],
            "competitor":        top["competitor"],
            "journey_id":        top.get("journey_id", ""),
            "confidence_score":  top.get("confidence_score"),
            "signal_severity":   top.get("signal_severity"),
            "finding_tier":      top.get("finding_tier"),
            "chronicle_id":      top["provenance"].get("chronicle_id"),
            "designed_ceiling":  top.get("designed_ceiling_reached", False),
            "p0":                top["signal_counts"]["P0"],
            "p1":                top["signal_counts"]["P1"],
            "summary":           top.get("finding_summary", "")[:160],
            "top_keywords":      top.get("top_3_keywords", []),
            "primary_blind_spot": blind_spots[0] if blind_spots else "",
            "action_required": (
                "To confirm this I require internal HDFS telemetry data. Request Phase 2."
                if top.get("designed_ceiling_reached")
                else "Monitor signal volume. Await human countersign before escalation."
            ),
        }
    else:
        executive_alert = {
            "finding_id":     None,
            "summary":        "No P0/P1 anchored findings in current window.",
            "action_required": "No immediate action required.",
        }

    return {
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "window_days":         window_days,
        "overall_sentiment":   overall_sentiment,
        "journey_performance": journey_performance,
        "issues_status":       issues_status,
        "competitor_ticker":   competitor_ticker,
        "top_findings":        top_findings,
        "executive_alert":     executive_alert,
    }


# ============================================================
# TEST BLOCK
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("MIL Briefing Data Layer -- test run")
    print()
    data = get_briefing_data()
    print(json.dumps(data, indent=2, default=str))
