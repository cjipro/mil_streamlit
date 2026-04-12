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
from collections import Counter, defaultdict
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
    Anchors on latest review date in the dataset (not today) so the
    3-day window is never empty when run early in the day.
    Split point: latest_review_date - 3 days.
      earlier_4d  = records dated before split
      current_3d  = records dated on or after split
    Returns STABLE when insufficient data for either window.
    """
    dated = [r for r in records if r.get("rating") and r.get("_review_date")]
    if not dated:
        return "STABLE"
    anchor = max(r["_review_date"] for r in dated)
    split   = anchor - timedelta(days=3)
    earlier = [r["rating"] for r in dated if r["_review_date"] < split]
    current = [r["rating"] for r in dated if r["_review_date"] >= split]

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
# EXECUTIVE ALERT HELPERS
# ============================================================

# Chronicle sentences — all inference_approved entries
_CHRONICLE_SENTENCES = {
    "CHR-001": "TSB saw this same sequence in 2018 — 1.9 million customers locked out, services unavailable for weeks.",
    "CHR-002": "Lloyds hit this same pattern in 2025 — a software update exposed 447,000 customers' transaction data before engineering caught it.",
    "CHR-003": "HSBC triggered this same failure class in August 2025 — an 18-month app refresh stressed legacy authentication infrastructure, locking customers out for 5 hours.",
    "CHR-004": "This matches Barclays' own sustained friction pattern — Feature Broken and Payment Failed signals have been running at low-level for months.",
}

# Teacher lessons — competitor banks that already went through this (CHR-001/002/003 only).
# CHR-004 is Barclays' own baseline — not a teacher, not included here.
_CHRONICLE_TEACHERS = {
    "CHR-001": {
        "bank": "TSB",
        "year": "2018",
        "lesson": (
            "TSB went live with 4,424 open defects. Within days, 1.9 million customers "
            "were locked out. 33,000 complaints arrived in a single week — ten times normal "
            "volume. The fine was £48.65 million. The CEO resigned. They had the same signals "
            "Barclays is showing now and did not escalate in time."
        ),
    },
    "CHR-002": {
        "bank": "Lloyds",
        "year": "2025",
        "lesson": (
            "An overnight software update exposed 447,000 Lloyds customers' transaction data. "
            "Lloyds fixed the defect the same day — but FCA, ICO, and Parliament were still "
            "asking questions months later. Resolving the issue quickly did not close the risk."
        ),
    },
    "CHR-003": {
        "bank": "HSBC",
        "year": "2025",
        "lesson": (
            "After an 18-month app redesign, HSBC took 4,765 DownDetector complaints in the "
            "first hour of their outage. The build-up looked exactly like this — rising app "
            "instability complaints with no single catastrophic trigger. Until there was one."
        ),
    },
}


def _chronicle_match_from_findings(findings: list) -> tuple:
    """
    Returns (chronicle_id, sentence) driven by the top Barclays finding's
    actual chronicle_match from mil_findings.json — not a static keyword overlap.

    Priority for Barclays: CHR-004 (their own friction pattern) is preferred
    over higher-CAC matches to other banks' incidents. Only falls back to the
    highest-CAC match if CHR-004 has no representation in the findings.
    """
    barclays = [
        f for f in findings
        if f.get("competitor", "").lower() == "barclays"
        and f.get("chronicle_match", {}).get("chronicle_id")
    ]
    if not barclays:
        return "", ""

    # Prefer CHR-004 for Barclays — it is their own sustained friction pattern
    chr4 = [f for f in barclays if f["chronicle_match"]["chronicle_id"] == "CHR-004"]
    if chr4:
        cid = "CHR-004"
    else:
        top = max(barclays, key=lambda f: f.get("confidence_score", 0))
        cid = top["chronicle_match"]["chronicle_id"]

    sentence = _CHRONICLE_SENTENCES.get(cid, "")
    return cid, sentence


def _teacher_from_findings(findings: list) -> tuple:
    """
    Returns (chr_id, bank, year, lesson) for the most relevant teacher CHR.

    Selection: driven by the top over-indexed Barclays issue type from the
    persistence log. Issue type → CHR mapping is explicit — avoids keyword
    substring gaming that caused CHR-001 (TSB migration) to win for generic
    app crash/feature signals.

    Issue-to-CHR map:
      App Crashing, App Not Opening, Feature Broken → CHR-003 (HSBC 2025: app instability)
      Login Failed, Account Locked               → CHR-001 (TSB 2018: auth/lockout)
      Incorrect Balance, Missing Transaction, Payment Failed → CHR-002 (Lloyds 2025: data defect)

    Fallback: CHR frequency across Barclays findings (excluding CHR-004).
    """
    _ISSUE_CHR_MAP = {
        "App Crashing":         "CHR-003",
        "App Not Opening":      "CHR-003",
        "Feature Broken":       "CHR-003",
        "Biometric / Face ID Issue": "CHR-003",
        "Login Failed":         "CHR-001",
        "Account Locked":       "CHR-001",
        "Incorrect Balance":    "CHR-002",
        "Missing Transaction":  "CHR-002",
        "Payment Failed":       "CHR-002",
        "Transfer Failed":      "CHR-002",
    }

    # Step 1: get top over-indexed issue from persistence log
    persistence_log = Path(__file__).parent / "data" / "issue_persistence_log.jsonl"
    preferred_cid = None
    if persistence_log.exists():
        try:
            all_entries = []
            for line in persistence_log.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        all_entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            if all_entries:
                latest_date = max(e["date"] for e in all_entries)
                today_entries = [e for e in all_entries if e["date"] == latest_date]
                # Top over-indexed issue sorted by churn contribution (gap × severity × persistence)
                sev_w = {"P0": 3.0, "P1": 2.0, "P2": 1.0}
                risk = [e for e in today_entries if e.get("over_indexed")]
                if risk:
                    risk.sort(
                        key=lambda e: e["gap_pp"] * sev_w.get(e.get("dominant_severity","P2"), 1.0)
                                      * min(1.0 + 0.2 * e.get("days_active", 1), 3.0),
                        reverse=True,
                    )
                    top_issue = risk[0]["issue_type"]
                    preferred_cid = _ISSUE_CHR_MAP.get(top_issue)
        except Exception:
            pass

    # Step 2: if we have a preferred CHR, verify at least one Barclays finding anchors to it
    _TEACHER_IDS = {"CHR-001", "CHR-002", "CHR-003"}
    barclays = [
        f for f in findings
        if f.get("competitor", "").lower() == "barclays"
        and f.get("chronicle_match", {}).get("chronicle_id") in _TEACHER_IDS
    ]

    cid = None
    if preferred_cid and barclays:
        cid = preferred_cid  # use issue-map CHR even if 0 findings anchor to it — map is authoritative

    # Step 3: fallback — frequency count across anchored findings
    if not cid:
        if not barclays:
            return "", "", "", ""
        chr_counts = Counter(f["chronicle_match"]["chronicle_id"] for f in barclays)
        cid = chr_counts.most_common(1)[0][0]

    t = _CHRONICLE_TEACHERS.get(cid, {})
    return cid, t.get("bank", ""), t.get("year", ""), t.get("lesson", "")


def _next_steps(p0: int, trend: str, clark_tier: str) -> str:
    if clark_tier == "CLARK-3" or p0 >= 4:
        return "This belongs on the incident board today. If it is not already there, that is the first failure. Escalate now."
    elif clark_tier == "CLARK-2" or (p0 >= 2 and trend == "WORSENING"):
        return "Escalate to product and engineering leadership. Request a status update by end of day."
    elif p0 >= 2 or trend == "WORSENING":
        return "Flag to the product team. Confirm someone owns this and get an update within 48 hours."
    elif p0 >= 1:
        return "Watch this. If volume increases or the trend turns, escalate immediately."
    return "Signal within normal range. No action required."


def _signal_strength(p0: int, cac: float) -> str:
    if p0 >= 4 or cac >= 0.6:
        return "STRONG SIGNAL"
    elif p0 >= 2 or cac >= 0.4:
        return "MODERATE SIGNAL"
    return "EARLY SIGNAL"


def _your_call(p0: int, trend: str) -> str:
    if p0 >= 4 or (p0 >= 2 and trend == "WORSENING"):
        return "Escalate now. If this isn't already on the incident board, it should be."
    elif p0 >= 2 or trend == "WORSENING":
        return "Confirm this is in hand. If not, flag to product immediately."
    elif p0 >= 1:
        return "Monitor. Raise with product team at next touchpoint."
    return "Signal within normal range. No action required."


def _exec_alert_description(reviews: list, chronicle_sentence: str) -> str:
    """
    Synthesise top P0/P1 reviews into one plain-English sentence for Box 3.
    Routes to qwen3:14b via Ollama (ARCH-002 — zero API cost for exec alert).
    Returns empty string on any failure — caller uses template fallback.
    """
    try:
        from openai import OpenAI
        try:
            from mil.config.get_model import get_model
        except ModuleNotFoundError:
            from config.get_model import get_model
        cfg = get_model("exec_alert")

        lines = []
        for i, r in enumerate(reviews[:5], 1):
            text = (r.get("review") or r.get("content", ""))[:120].strip()
            if text:
                lines.append(f"{i}. [{r.get('rating', '?')}/5] {text}")

        if not lines:
            return ""

        context_line = (
            f"\nFor context, this mirrors a known pattern: {chronicle_sentence}"
            if chronicle_sentence else ""
        )
        prompt = (
            "You are summarising customer app reviews for a bank CEO.\n"
            "In one sentence (maximum 30 words), describe the core customer problem.\n"
            "Be specific. Start with what customers cannot do. No preamble."
            f"{context_line}\n\nReviews:\n" + "\n".join(lines)
        )

        client = OpenAI(base_url=cfg["api_compat_url"], api_key="ollama")
        response = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip().rstrip(".")
    except Exception as exc:
        logger.warning("[exec_alert] qwen3 synthesis failed: %s", exc)
        return ""


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
    # SECTION 2a: ISSUES — grouped by issue_type (what went wrong)
    # Barclays records only. Excludes Positive Feedback and Other unless P0/P1.
    # ----------------------------------------------------------
    barclays_records = [r for r in records if r.get("_competitor", "").lower() == "barclays"]
    issue_groups: dict[str, list[dict]] = defaultdict(list)
    for r in barclays_records:
        cat = r.get("issue_type") or "Other"
        issue_groups[cat].append(r)

    rows = []
    for cat, jrecs in issue_groups.items():
        p0 = sum(1 for r in jrecs if r.get("severity_class") == "P0")
        p1 = sum(1 for r in jrecs if r.get("severity_class") == "P1")
        p2 = sum(1 for r in jrecs if r.get("severity_class") == "P2")

        if cat in ("Positive Feedback", "Other") and p0 == 0 and p1 == 0:
            continue

        vol       = len(jrecs)
        ratings   = [r["rating"] for r in jrecs if r.get("rating")]
        sentiment = _star_sentiment(ratings) if ratings else overall_score
        j_trend   = _trend(jrecs, today)
        i_score   = _issue_score(vol, p0, p1, p2, j_trend, set())

        rows.append({
            "journey":         cat,
            "sentiment_score": sentiment if sentiment >= 0 else overall_score,
            "trend":           j_trend,
            "issue_score":     i_score,
            "p0":              p0,
            "p1":              p1,
            "p2":              p2,
            "volume":          vol,
            "chronicle_ids":   [],
        })

    rows.sort(key=lambda x: -x["issue_score"])

    # ----------------------------------------------------------
    # SECTION 2b: JOURNEY PERFORMANCE — grouped by customer_journey
    # Barclays records only. Excludes General App Use unless P0/P1.
    # ----------------------------------------------------------
    journey_groups: dict[str, list[dict]] = defaultdict(list)
    for r in barclays_records:
        cat = r.get("customer_journey") or "General App Use"
        journey_groups[cat].append(r)

    journey_rows = []
    for cat, jrecs in journey_groups.items():
        p0 = sum(1 for r in jrecs if r.get("severity_class") == "P0")
        p1 = sum(1 for r in jrecs if r.get("severity_class") == "P1")
        p2 = sum(1 for r in jrecs if r.get("severity_class") == "P2")

        if cat == "General App Use" and p0 == 0 and p1 == 0:
            continue

        vol       = len(jrecs)
        ratings   = [r["rating"] for r in jrecs if r.get("rating")]
        sentiment = _star_sentiment(ratings) if ratings else overall_score
        j_trend   = _trend(jrecs, today)
        jid       = _CATEGORY_TO_JID.get(cat)
        chron_ids = jid_chronicles.get(jid, set()) if jid else set()
        i_score   = _issue_score(vol, p0, p1, p2, j_trend, chron_ids)

        journey_rows.append({
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

    journey_rows.sort(key=lambda x: -x["issue_score"])

    # Top 5 issues (what went wrong)
    issues_performance = []
    for rank, row in enumerate(rows[:5], 1):
        issues_performance.append({
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

    # Top 5 journeys (what were they trying to do)
    journey_performance = []
    for rank, row in enumerate(journey_rows[:5], 1):
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

        # Baseline: all-time avg from enriched files for this competitor (no date filter)
        c_baseline = None
        if comp.lower() == "barclays":
            _all_ratings = []
            for _f in sorted(ENRICHED_DIR.glob("*.json")):
                try:
                    _p = json.loads(_f.read_text(encoding="utf-8"))
                    if _p.get("competitor", "").lower() == "barclays":
                        _all_ratings.extend(
                            r["rating"] for r in _p.get("records", [])
                            if r.get("rating") and r.get("severity_class") != "ENRICHMENT_FAILED"
                        )
                except Exception:
                    pass
            if _all_ratings:
                c_baseline = _star_sentiment(_all_ratings)

        competitor_ticker.append({
            "competitor": comp,
            "score":      score if score >= 0 else "N/A",
            "trend":      c_trend,
            "baseline":   c_baseline,
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
    # Self-intelligence: Barclays is the client (TAQ Bank).
    # Reads their own public app signals back to them before internal
    # teams escalate. Chronicle surfaces only on issue_type keyword match
    # against inference_approved entries (CHR-001, CHR-002).
    # ----------------------------------------------------------
    all_cands = [f for f in anchored
                 if f["signal_counts"]["P0"] + f["signal_counts"]["P1"] > 0]
    barclays_cands = [f for f in all_cands
                      if f.get("competitor", "").lower() == "barclays"]
    exec_cands = barclays_cands if barclays_cands else all_cands

    if exec_cands:
        top     = max(exec_cands, key=lambda f: (
            f["signal_counts"]["P0"] > 0,
            f.get("designed_ceiling_reached", False),
            f.get("confidence_score", 0),
        ))
        p0      = top["signal_counts"]["P0"]
        p1      = top["signal_counts"]["P1"]
        cac     = top.get("confidence_score") or 0.0

        # Barclays P0/P1 records for Sonnet synthesis — P0 first
        barclays_p01 = sorted(
            [r for r in records
             if r.get("_competitor", "").lower() == "barclays"
             and r.get("severity_class") in ("P0", "P1")],
            key=lambda r: 0 if r.get("severity_class") == "P0" else 1,
        )

        # Barclays trend from competitor_ticker (built above)
        _b_ticker = next(
            (c for c in competitor_ticker if c["competitor"].lower() == "barclays"), {}
        )
        barclays_trend = _b_ticker.get("trend", "STABLE")

        # Chronicle matching — driven by top Barclays finding's actual CHR anchor
        chronicle_id, chronicle_sentence = _chronicle_match_from_findings(anchored)

        # Top quote: most specific P0 review — prefer 60-150 chars, else shortest over 40
        top_quote = ""
        top_quote_rating = 0
        top_quote_source = ""
        _candidates = [
            r for r in barclays_p01
            if r.get("severity_class") == "P0"
            and len((r.get("review") or r.get("content", "")).strip()) >= 40
            and r.get("issue_type") != "Positive Feedback"
        ]
        if _candidates:
            _in_range = [r for r in _candidates
                         if 60 <= len((r.get("review") or r.get("content", "")).strip()) <= 200]
            _pick = _in_range[0] if _in_range else sorted(
                _candidates, key=lambda r: len((r.get("review") or r.get("content", "")))
            )[0]
            top_quote        = ((_pick.get("review") or _pick.get("content", ""))).strip()
            top_quote_rating = _pick.get("rating", 0) or 0
            top_quote_source = "App Store" if _pick.get("review") else "Google Play"

        def _pick_quote(candidates: list, text_field: str, date_field: str) -> tuple:
            """Return (text, rating, date_str) for worst available quote from a source.
            Tries P0 first, falls back to P1."""
            for sev in ("P0", "P1"):
                _c = [
                    r for r in candidates
                    if r.get(text_field) and r.get("severity_class") == sev
                    and len(r.get(text_field, "").strip()) >= 40
                    and r.get("issue_type") != "Positive Feedback"
                ]
                if _c:
                    break
            if not _c:
                return "", 0, ""
            _in_range = [r for r in _c if 60 <= len(r.get(text_field, "").strip()) <= 200]
            _p = _in_range[0] if _in_range else sorted(_c, key=lambda r: len(r.get(text_field, "")))[0]
            _text = _p.get(text_field, "").strip()
            _rating = int(_p.get("rating", 0) or 0)
            _raw_date = str(_p.get(date_field, "") or "")[:10]
            _date_str = ""
            if _raw_date and len(_raw_date) >= 10:
                try:
                    from datetime import datetime as _dtp
                    _dobj = _dtp.fromisoformat(_raw_date)
                    _date_str = f"{_dobj.day} {_dobj.strftime('%b')}"
                except Exception:
                    _date_str = _raw_date
            return _text, _rating, _date_str

        # App Store quote (Barclays P0, has 'review' field and 'date')
        as_quote, as_quote_rating, as_quote_date = _pick_quote(barclays_p01, "review", "date")
        # Google Play quote (Barclays P0, has 'content' field and 'at')
        gp_quote, gp_quote_rating, gp_quote_date = _pick_quote(barclays_p01, "content", "at")

        # Description: Sonnet synthesis with template fallback
        description = _exec_alert_description(barclays_p01, chronicle_sentence)
        if not description:
            top_issues = [
                i.lower() for i, _ in Counter(
                    r.get("issue_type", "app issues") for r in barclays_p01
                ).most_common(2)
                if i and i != "Positive Feedback"
            ]
            issue_label = " and ".join(top_issues) if top_issues else "app issues"
            description = f"Customers reporting {issue_label}"

        # Clark tier for top finding — dual import path (mil/ on sys.path or repo root)
        try:
            from mil.command.components.clark_protocol import get_clark_tier_for_finding
        except ImportError:
            from command.components.clark_protocol import get_clark_tier_for_finding
        try:
            clark_tier = get_clark_tier_for_finding(top["finding_id"])
        except Exception:
            clark_tier = "CLARK-0"

        # Teacher lesson — which competitor bank already walked this path
        teacher_chr, teacher_bank, teacher_year, teacher_lesson = _teacher_from_findings(anchored)

        # Top journey from the highest-ranked finding
        top_journey = top.get("journey_id", "")

        executive_alert = {
            "finding_id":         top["finding_id"],
            "competitor":         top["competitor"],
            "p0":                 p0,
            "p1":                 p1,
            "cac":                round(cac, 2),
            "signal_strength":    _signal_strength(p0, cac),
            "top_journey":        top_journey,
            "description":        description,
            "top_quote":          top_quote,
            "top_quote_rating":   int(top_quote_rating),
            "top_quote_source":   top_quote_source,
            "as_quote":           as_quote,
            "as_quote_rating":    as_quote_rating,
            "as_quote_date":      as_quote_date,
            "gp_quote":           gp_quote,
            "gp_quote_rating":    gp_quote_rating,
            "gp_quote_date":      gp_quote_date,
            "chronicle_id":       chronicle_id,
            "chronicle_sentence": chronicle_sentence,
            "teacher_chr":        teacher_chr,
            "teacher_bank":       teacher_bank,
            "teacher_year":       teacher_year,
            "teacher_lesson":     teacher_lesson,
            "next_steps":         _next_steps(p0, barclays_trend, clark_tier),
            "clark_tier":         clark_tier,
        }
    else:
        as_quote = gp_quote = ""
        executive_alert = {
            "finding_id":         None,
            "p0":                 0,
            "p1":                 0,
            "cac":                0.0,
            "signal_strength":    "CLEAR",
            "top_journey":        "",
            "description":        "No P0/P1 signals detected in current window.",
            "chronicle_id":       "",
            "chronicle_sentence": "",
            "teacher_chr":        "",
            "teacher_bank":       "",
            "teacher_year":       "",
            "teacher_lesson":     "",
            "next_steps":         "No action required.",
            "clark_tier":         "CLARK-0",
        }

    # Box 2 quote: worst P0/P1 from the top-ranked issue_type, de-duped vs Box 1 quotes
    box2_quote = ""
    box2_quote_rating = 0
    box2_quote_source = ""
    box2_quote_date = ""
    box2_issue_type = ""
    if issues_performance:
        _top_issue = issues_performance[0]["journey"]
        box2_issue_type = _top_issue
        _b2_pool = [
            r for r in barclays_records
            if r.get("issue_type") == _top_issue
            and r.get("severity_class") in ("P0", "P1")
            and len((r.get("review") or r.get("content", "")).strip()) >= 40
            and r.get("issue_type") != "Positive Feedback"
        ]
        _b2_pool.sort(key=lambda r: 0 if r.get("severity_class") == "P0" else 1)
        _b1_keys = {as_quote[:80], gp_quote[:80]} - {""}
        # First pass: prefer 60-200 chars, not duplicate
        for _b2r in _b2_pool:
            _t = ((_b2r.get("review") or _b2r.get("content", ""))).strip()
            if _t[:80] in _b1_keys:
                continue
            if 60 <= len(_t) <= 200:
                box2_quote = _t
                break
        # Second pass: any non-duplicate
        if not box2_quote:
            for _b2r in _b2_pool:
                _t = ((_b2r.get("review") or _b2r.get("content", ""))).strip()
                if _t[:80] not in _b1_keys:
                    box2_quote = _t
                    break
        if box2_quote:
            _b2r = next(r for r in _b2_pool
                        if (r.get("review") or r.get("content","")).strip() == box2_quote)
            box2_quote_rating = int(_b2r.get("rating", 0) or 0)
            box2_quote_source = "App Store" if _b2r.get("review") else "Google Play"
            _b2_raw = str(_b2r.get("date") or _b2r.get("at", "") or "")[:10]
            if len(_b2_raw) >= 10:
                try:
                    from datetime import datetime as _dtp3
                    _b2d = _dtp3.fromisoformat(_b2_raw)
                    box2_quote_date = f"{_b2d.day} {_b2d.strftime('%b')}"
                except Exception:
                    box2_quote_date = _b2_raw

    return {
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "window_days":         window_days,
        "overall_sentiment":   overall_sentiment,
        "issues_performance":  issues_performance,
        "journey_performance": journey_performance,
        "issues_status":       issues_status,
        "box2_quote":          box2_quote,
        "box2_quote_rating":   box2_quote_rating,
        "box2_quote_source":   box2_quote_source,
        "box2_quote_date":     box2_quote_date,
        "box2_issue_type":     box2_issue_type,
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
