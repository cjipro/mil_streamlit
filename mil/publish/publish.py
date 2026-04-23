#!/usr/bin/env python3
"""
Sonar Briefing Publisher — MIL Sovereign System
mil/publish/publish.py

Reads mil/outputs/mil_findings.json and mil/data/signals/latest.
Generates a self-contained HTML briefing page.
Pushes to GitHub Pages at /briefing/index.html.

MIL Zero Entanglement Rule:
  No imports from pulse/, poc/, app/, dags/, or any internal module.
  This file is sovereign — stdlib + third-party only.
"""

import json
import os
import sys
import glob
import shutil
import subprocess
import tempfile
import html as html_escape_module
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

# ── MIL-sibling import: briefing_data.py is sovereign MIL code, not a pulse/ module ──
_MIL_DIR_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(_MIL_DIR_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_MIL_DIR_FOR_IMPORT))
try:
    from briefing_data import get_briefing_data as _get_briefing_data
    _BRIEFING_DATA_AVAILABLE = True
except Exception as _bd_import_err:
    _get_briefing_data = None
    _BRIEFING_DATA_AVAILABLE = False

# -----------------------------------------------------------------------------
# PATH CONSTANTS
# -----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
MIL_DIR = SCRIPT_DIR.parent
REPO_ROOT = MIL_DIR.parent

FINDINGS_PATH = MIL_DIR / "outputs" / "mil_findings.json"
SIGNALS_DIR = MIL_DIR / "data" / "signals"
OUTPUT_DIR = SCRIPT_DIR / "output"
ENV_PATH = REPO_ROOT / ".env"

COMPETITORS_ORDERED = ["NatWest", "Lloyds", "HSBC", "Monzo", "Revolut", "Barclays"]

JOURNEY_IDS = ["J_LOGIN_01", "J_PAY_01", "J_ONBOARD_01", "J_LOANS_03", "J_SERVICE_01"]

JOURNEY_NAMES = {
    "J_LOGIN_01":   "Login & Auth",
    "J_PAY_01":     "Payments",
    "J_ONBOARD_01": "Onboarding",
    "J_LOANS_03":   "Loans — Step 3",
    "J_SERVICE_01": "Servicing",
}

JOURNEY_KEYWORDS = {
    "J_LOGIN_01": [
        "login", "log in", "sign in", "signin", "locked out", "locked",
        "authentication", "biometric", "face id", "fingerprint", "password",
        "two factor", "2fa", "otp", "access denied", "cant access", "can't access",
        "cant log", "can't log", "verify identity", "verification code",
    ],
    "J_PAY_01": [
        "payment", "transfer", "pay ", "transaction", "send money", "pending",
        "declined", "faster payment", "bacs", "standing order", "direct debit",
        "paying", "credit card", "debit card", "payee",
    ],
    "J_ONBOARD_01": [
        "open account", "sign up", "signup", "registration", "kyc",
        "new account", "join", "apply", "applying", "onboard",
    ],
    "J_LOANS_03": [
        "loan", "overdraft", "credit", "borrow", "mortgage",
        "income", "affordability", "limit", "lending",
    ],
    "J_SERVICE_01": [
        "balance", "statement", "card", "freeze", "dashboard",
        "features", "update", "notification", "app", "screen",
        "account", "interest", "savings",
    ],
}

# Negative keywords for pill extraction
NEGATIVE_KEYWORDS = [
    "error", "crash", "broken", "fix", "fail", "issue", "problem", "bug",
    "doesn't work", "not working", "not loading", "freezes", "stuck",
    "slow", "terrible", "awful", "useless", "frustrated", "annoying",
    "locked", "declined", "pending", "missing", "lost", "incorrect",
    "wrong", "outdated", "backwards", "removed", "deprecated",
]

POSITIVE_KEYWORDS = [
    "easy", "great", "love", "excellent", "perfect", "helpful",
    "reliable", "fast", "smooth", "brilliant", "best", "amazing",
    "improved", "simple", "intuitive",
]

# Internal map: raw journey_category -> journey_id (for legacy HTML functions only)
_CATEGORY_TO_JID_PUB = {
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


def _severity_state(p0: int, p1: int, trend: str, persistence_days: int,
                    persistent_threshold: int = 7) -> str:
    """
    4-way severity state (replaces the 3-way REGRESSION/WATCH/PERFORMING WELL
    taxonomy for the Journey Row). Each label answers one question:

      ACUTE      — severe signal present, and the situation isn't "stable bad"
                   (either the trend is worsening or persistence is short)
      PERSISTENT — severe signal has been present for ≥7d AND trend isn't
                   worsening (still bad, but not getting worse — chronic)
      DRIFT      — no severe signal yet, but rating trend is worsening
                   (early-warning band: harm not yet flagged, but forming)
      STABLE     — no severe signal, trend flat or improving

    Mutually exclusive. Decouples "is it severe" from "is it moving" from
    "how long has it been there" — the three signals that REGRESSION used
    to conflate.
    """
    severe = p0 > 0 or p1 > 0
    if severe:
        if persistence_days >= persistent_threshold and trend != "WORSENING":
            return "PERSISTENT"
        return "ACUTE"
    if trend == "WORSENING":
        return "DRIFT"
    return "STABLE"


def _bd_to_journey_analysis(journey_performance: list) -> list:
    """
    Translate briefing_data journey_performance (or issues_performance) list
    into the journey_analysis format used by the HTML builders.
    Fully dynamic — no hardcoded journey IDs or name mappings.
    """
    result = []
    for row in journey_performance:
        p0    = row.get("p0", 0)
        p1    = row.get("p1", 0)
        p2    = row.get("p2", 0)
        trend = row.get("trend", "STABLE")
        # issues_performance carries days_active; journey_performance carries
        # streak_days. Normalise to one persistence field for severity-state.
        persistence_days = row.get("days_active") or row.get("streak_days") or 0

        # Legacy 3-way status — kept for Box 2 / metrics strip / other surfaces
        # that haven't been migrated to severity_state yet.
        if p0 > 0 or (p1 >= 2 and trend == "WORSENING"):
            status = "REGRESSION"
        elif p1 > 0 or trend == "WORSENING":
            status = "WATCH"
        else:
            status = "PERFORMING WELL"

        severity_state = _severity_state(p0, p1, trend, persistence_days)

        name = row.get("journey", "")
        result.append({
            "rank":            row["rank"],
            "journey_id":      name,   # use name as ID — no static mapping
            "journey_name":    name,
            "status":          status,
            "severity_state":  severity_state,
            "trend":           trend,
            "score":           row.get("sentiment_score"),
            "avg_rating":      round(row.get("sentiment_score", 0) / 20, 2) if row.get("sentiment_score") else None,
            "p1":              p0 + p1,
            "p2":              p2,
            "volume":          row.get("volume", 0),
            "days_active":     row.get("days_active", 0),
            "streak_days":     row.get("streak_days", 0),
            "negative_weight": p0 * 8 + p1 * 3 + p2,
            "neg_pills":       [],
            "pos_pills":       [],
            "verdict_text":    row.get("verdict", ""),
            "version_current": None,
            "is_derived":      True,
        })
    return result


def build_bd_exec_alert_html(ea: dict, last_run_str: str) -> str:
    """Build Barclays Alert panel HTML from briefing_data executive_alert dict.

    Structure: THE SITUATION / THE LESSON (teacher bank) / SEVERITY / NEXT STEPS.
    Other banks are the teachers. Barclays is the student.
    """
    if not ea or not ea.get("finding_id"):
        return (
            '  <!-- Right: Barclays Alert panel -->\n'
            '  <div class="topbar-box exec-alert-panel exec-alert-nominal">\n'
            '    <div class="exec-alert-header exec-alert-header-nominal">\n'
            '      <span class="exec-alert-pulse exec-alert-pulse-green"></span>\n'
            '      <span class="exec-alert-title exec-alert-title-nominal">Barclays Alert</span>\n'
            f'      <span class="exec-alert-ts">{e(last_run_str)}</span>\n'
            '    </div>\n'
            '    <div class="exec-alert-body">\n'
            '      <div class="exec-nominal-badge">SYSTEMS NOMINAL</div>\n'
            '      <div class="exec-nominal-text">No active P0 or P1 signals in current window.</div>\n'
            '    </div>\n'
            '  </div>'
        )

    p0              = ea.get("p0", 0)
    p1              = ea.get("p1", 0)
    cac             = ea.get("cac", 0.0)
    clark_tier      = ea.get("clark_tier", "CLARK-0")
    signal_strength = ea.get("signal_strength", "EARLY SIGNAL")
    description     = ea.get("description", "")
    teacher_bank    = ea.get("teacher_bank", "")
    teacher_year    = ea.get("teacher_year", "")
    teacher_lesson  = ea.get("teacher_lesson", "")
    next_steps      = ea.get("next_steps", "")

    # Clark tier pill + button colour
    _clark_colours = {
        "CLARK-3": ("rgba(204,0,0,0.18)",    "#FF4444", "rgba(204,0,0,0.4)"),
        "CLARK-2": ("rgba(245,100,0,0.15)",   "#F56400", "rgba(245,100,0,0.4)"),
        "CLARK-1": ("rgba(245,166,35,0.12)",  "#F5A623", "rgba(245,166,35,0.3)"),
        "CLARK-0": ("rgba(120,120,120,0.10)", "#888",    "rgba(120,120,120,0.3)"),
    }
    _clark_labels = {
        "CLARK-3": "ACT NOW", "CLARK-2": "ESCALATE",
        "CLARK-1": "WATCH",   "CLARK-0": "NOMINAL",
    }
    _cbg, _cfg, _cbr = _clark_colours.get(clark_tier, _clark_colours["CLARK-0"])
    clark_style  = f"background:{_cbg};color:{_cfg};border:1px solid {_cbr};font-weight:700;"
    btn_style    = (
        f"background:{_cbg};color:{_cfg};border:1px solid {_cbr};"
        "border-radius:6px;font-size:13px;font-weight:700;letter-spacing:0.08em;"
        "padding:6px 14px;cursor:pointer;width:100%;font-family:var(--sans);"
        "text-transform:uppercase;margin-top:10px;"
    )
    btn_label    = _clark_labels.get(clark_tier, "ESCALATE")

    p0_style  = "background:rgba(204,0,0,0.18);color:#FF4444;border:1px solid rgba(204,0,0,0.4);"
    p1_style  = "background:rgba(245,166,35,0.12);color:#F5A623;border:1px solid rgba(245,166,35,0.3);"
    cac_style = "background:rgba(0,174,239,0.10);color:#00AEEF;border:1px solid rgba(0,174,239,0.3);"

    # Teacher lesson block — only when a teacher match exists
    teacher_html = ""
    if teacher_bank and teacher_lesson:
        label = f"THE LESSON — {e(teacher_bank)}, {e(teacher_year)}"
        teacher_html = (
            f'      <div class="exec-alert-section-label">{label}</div>\n'
            f'      <div class="exec-alert-section-text">{e(teacher_lesson)}</div>\n'
        )

    return (
        '  <!-- Right: Barclays Alert panel (bd-wired) -->\n'
        '  <div class="topbar-box exec-alert-panel">\n'
        '    <div class="exec-alert-header">\n'
        '      <span class="exec-alert-pulse"></span>\n'
        '      <span class="exec-alert-title">Barclays Alert</span>\n'
        f'      <span class="exec-alert-ts">{e(last_run_str)}</span>\n'
        '    </div>\n'
        '    <div class="exec-alert-body">\n'
        '      <div class="exec-alert-pills" style="margin-bottom:10px;">\n'
        f'        <span class="exec-pill" style="{clark_style}">{e(clark_tier)}</span>\n'
        f'        <span class="exec-pill" style="{cac_style}">{e(signal_strength)}</span>\n'
        '      </div>\n'
        '      <div class="exec-alert-section-label">THE SITUATION</div>\n'
        f'      <div class="exec-alert-section-text">{e(description)}</div>\n'
        f'{teacher_html}'
        '      <div class="exec-alert-section-label">SEVERITY</div>\n'
        '      <div class="exec-alert-pills">\n'
        f'        <span class="exec-pill" style="{p0_style}">P0 &nbsp;{p0}</span>\n'
        f'        <span class="exec-pill" style="{p1_style}">P1 &nbsp;{p1}</span>\n'
        f'        <span class="exec-pill" style="{cac_style}">CAC &nbsp;{cac:.2f}</span>\n'
        '      </div>\n'
        '      <div class="exec-alert-section-label">NEXT STEPS</div>\n'
        f'      <div class="exec-alert-section-text">{e(next_steps)}</div>\n'
        f'      <button class="exec-escalate-btn" style="{btn_style}">{btn_label}</button>\n'
        '    </div>\n'
        '    <div class="exec-alert-footnote">\n'
        '      <span>P0 — customer blocked</span>'
        '      <span class="exec-fn-sep">·</span>'
        '      <span>P1 — significant friction</span>'
        '      <span class="exec-fn-sep">·</span>'
        '      <span>CAC — signal confidence (0–1)</span>'
        '      <span class="exec-fn-sep">·</span>'
        f'      <span>CLARK-3 — act now &nbsp;CLARK-2 — escalate &nbsp;CLARK-1 — watch</span>\n'
        '    </div>\n'
        '  </div>'
    )


# -----------------------------------------------------------------------------
# ENV LOADING
# -----------------------------------------------------------------------------

def load_env():
    """Parse .env file without python-dotenv dependency."""
    env = {}
    if not ENV_PATH.exists():
        return env
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            env[key] = val
    return env


# -----------------------------------------------------------------------------
# DATA LOADING
# -----------------------------------------------------------------------------

def load_findings():
    """Load mil_findings.json with safe defaults."""
    defaults = {
        "findings": [],
        "generated_at": None,
        "sentiment_scores": {},
        "chronicle_matches": [],
        "blind_spots": [],
        "signal_sources": {},
        "version_current": None,
        "version_previous": None,
        "_status": "BOOTSTRAP",
    }
    try:
        with open(FINDINGS_PATH) as f:
            data = json.load(f)
        # Merge with defaults for any missing keys
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        return data, []
    except Exception as e:
        return defaults, [f"mil_findings.json: {e}"]


def load_latest_signals():
    """Load most recent signals_*.json file."""
    pattern = str(SIGNALS_DIR / "signals_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return [], None, ["No signals files found in mil/data/signals/"]
    latest = files[-1]
    try:
        with open(latest) as f:
            signals = json.load(f)
        return signals, Path(latest).name, []
    except Exception as e:
        return [], None, [f"{Path(latest).name}: {e}"]


# -----------------------------------------------------------------------------
# SIGNAL ANALYSIS
# -----------------------------------------------------------------------------

def classify_journey(text: str) -> str:
    """Return the most specific journey ID for a review text."""
    if not text:
        return "J_SERVICE_01"
    t = text.lower()
    scores = {}
    for jid, keywords in JOURNEY_KEYWORDS.items():
        scores[jid] = sum(1 for kw in keywords if kw in t)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "J_SERVICE_01"


def extract_text(signal: dict) -> str:
    """Extract review/content text from any source's raw_data."""
    rd = signal.get("raw_data", {})
    return (
        rd.get("review") or
        rd.get("content") or
        rd.get("title", "") + " " + (rd.get("description") or rd.get("summary") or "")
    ).strip()


def get_rating(signal: dict):
    """Extract numeric rating (1-5) from any source. Returns None if unavailable."""
    rd = signal.get("raw_data", {})
    return rd.get("rating")  # app_store and google_play both use 'rating'


def compute_competitor_sentiment(signals: list) -> dict:
    """
    Compute per-competitor sentiment from raw signals.
    Returns: {competitor: {score, avg_rating, count, p0, p1, p2, version, reviews}}
    """
    data = defaultdict(lambda: {
        "ratings": [], "p0": 0, "p1": 0, "p2": 0,
        "reviews": [], "versions": [],
    })

    for sig in signals:
        comp = sig.get("competitor")
        if not comp:
            continue
        rating = get_rating(sig)
        if rating is not None:
            data[comp]["ratings"].append(int(rating))
        sev = sig.get("severity_class", "")
        if sev == "P0":
            data[comp]["p0"] += 1
        elif sev == "P1":
            data[comp]["p1"] += 1
        elif sev == "P2":
            data[comp]["p2"] += 1

        text = extract_text(sig)
        rd = sig.get("raw_data", {})
        version = rd.get("version") or rd.get("reviewCreatedVersion")
        if version:
            data[comp]["versions"].append(version)
        if text and rating is not None:
            data[comp]["reviews"].append({
                "rating": int(rating),
                "text": text,
                "version": version,
                "severity": sev,
            })

    result = {}
    for comp in COMPETITORS_ORDERED:
        d = data.get(comp, {"ratings": [], "p0": 0, "p1": 0, "p2": 0, "reviews": [], "versions": []})
        ratings = d["ratings"]
        if ratings:
            avg = sum(ratings) / len(ratings)
            # Normalize 1–5 → 0–100
            score = round((avg - 1) / 4 * 100, 1)
        else:
            avg = None
            score = None
        versions = d["versions"]
        version = versions[-1] if versions else None
        result[comp] = {
            "score": score,
            "avg_rating": round(avg, 2) if avg else None,
            "count": len(ratings),
            "p0": d["p0"],
            "p1": d["p1"],
            "p2": d["p2"],
            "version": version,
            "reviews": d["reviews"],
        }
    return result


def compute_journey_analysis(signals: list, competitor_sentiment: dict) -> list:
    """
    Derive journey-level analysis from signals when findings are empty.
    Returns list of journey dicts ranked by signal weight (most impacted first).
    """
    journey_data = defaultdict(lambda: {
        "ratings": [], "p1": 0, "p2": 0,
        "reviews": [], "versions": [],
    })

    for sig in signals:
        text = extract_text(sig)
        jid = classify_journey(text)
        rating = get_rating(sig)
        if rating is not None:
            journey_data[jid]["ratings"].append(int(rating))
        sev = sig.get("severity_class", "")
        if sev in ("P1", "P0"):
            journey_data[jid]["p1"] += 1
        elif sev == "P2":
            journey_data[jid]["p2"] += 1
        rd = sig.get("raw_data", {})
        version = rd.get("version") or rd.get("reviewCreatedVersion")
        if version:
            journey_data[jid]["versions"].append(version)
        if text and sev in ("P1", "P2", "P0"):
            journey_data[jid]["reviews"].append({
                "rating": rating,
                "text": text,
                "version": version,
                "severity": sev,
            })

    journeys = []
    for rank, jid in enumerate(JOURNEY_IDS, 1):
        d = journey_data.get(jid, {"ratings": [], "p1": 0, "p2": 0, "reviews": [], "versions": []})
        ratings = d["ratings"]
        if ratings:
            avg = sum(ratings) / len(ratings)
            score = round((avg - 1) / 4 * 100, 1)
        else:
            avg = None
            score = None

        # Status
        negative_weight = d["p1"] * 1.5 + d["p2"]
        if d["p1"] >= 3 or (avg and avg < 2.5):
            status = "REGRESSION"
        elif d["p1"] >= 1 or d["p2"] >= 3 or (avg and avg < 3.5):
            status = "WATCH"
        else:
            status = "PERFORMING WELL"

        # Customer voice pills
        all_text = " ".join(r["text"].lower() for r in d["reviews"])
        neg_pills = [kw for kw in NEGATIVE_KEYWORDS if kw in all_text][:5]
        pos_pills = [kw for kw in POSITIVE_KEYWORDS if kw in all_text][:3]

        # Top negative review excerpt
        verdict_reviews = [r for r in d["reviews"] if r.get("rating") and r["rating"] <= 2]
        if verdict_reviews:
            top_review = sorted(verdict_reviews, key=lambda r: r.get("rating", 5))[0]
            text_excerpt = top_review["text"][:120].rstrip() + ("…" if len(top_review["text"]) > 120 else "")
        else:
            text_excerpt = None

        versions = d["versions"]
        version_current = versions[-1] if versions else None

        journeys.append({
            "rank": rank,
            "journey_id": jid,
            "journey_name": JOURNEY_NAMES[jid],
            "status": status,
            "score": score,
            "avg_rating": round(avg, 2) if avg else None,
            "p1": d["p1"],
            "p2": d["p2"],
            "negative_weight": negative_weight,
            "neg_pills": neg_pills,
            "pos_pills": pos_pills,
            "verdict_text": text_excerpt,
            "version_current": version_current,
            "version_previous": None,
            "version_delta": None,
            "is_derived": True,  # derived from signals, not inference
        })

    # Rank by negative weight descending
    journeys.sort(key=lambda j: j["negative_weight"], reverse=True)
    for i, j in enumerate(journeys, 1):
        j["rank"] = i

    return journeys


def detect_source_coverage(signals: list) -> dict:
    """Return dict of source → status (active/amber/inactive)."""
    sources_in_data = set(s.get("source") for s in signals)
    all_sources = [
        "downdetector", "app_store", "google_play", "financial_times",
        "city_am", "reddit", "trustpilot", "facebook", "youtube", "twitter_x",
    ]
    # Map ft_cityam → financial_times + city_am
    if "ft_cityam" in sources_in_data:
        sources_in_data.add("financial_times")
        sources_in_data.add("city_am")

    result = {}
    for src in all_sources:
        if src in sources_in_data:
            result[src] = "active"
        elif src == "facebook":
            result[src] = "stub"  # known stub
        else:
            result[src] = "inactive"
    return result


def get_version_info(signals: list) -> tuple:
    """Return (version_current, version_previous) from signals."""
    versions = []
    for s in signals:
        rd = s.get("raw_data", {})
        v = rd.get("version") or rd.get("reviewCreatedVersion")
        if v:
            versions.append(v)
    if not versions:
        return None, None
    version_counter = Counter(versions)
    top_versions = [v for v, _ in version_counter.most_common(2)]
    current = top_versions[0] if top_versions else None
    previous = top_versions[1] if len(top_versions) > 1 else None
    return current, previous


# -----------------------------------------------------------------------------
# HTML GENERATION
# -----------------------------------------------------------------------------

def e(s):
    """HTML-escape a value for safe embedding."""
    if s is None:
        return ""
    return html_escape_module.escape(str(s))


def score_color(score):
    """Return RAG CSS color for a 0–100 score. Used for arrows and status text."""
    if score is None:
        return "#6b7088"
    if score < 45:
        return "#cc3333"
    if score < 65:
        return "#e8a030"
    return "#2a9a5a"


def score_num_color(score):
    """Two-color rule for score numbers: red below 50, white above."""
    if score is not None and score < 50:
        return "#cc3333"
    return "#E8F4FA"


def score_bar_html(score, width=60):
    """Inline mini bar as HTML."""
    if score is None:
        pct = 0
        color = "#6b7088"
    else:
        pct = min(100, max(0, score))
        color = score_color(score)
    filled = round(pct / 100 * width)
    return (
        f'<span class="mini-bar">'
        f'<span class="mini-bar-fill" style="width:{filled}px;background:{color};"></span>'
        f'</span>'
    )


def status_badge_html(status):
    """Return HTML badge for a journey status."""
    colors = {
        "REGRESSION":     ("var(--red)",   "#2a0a0a"),
        "WATCH":          ("var(--amber)", "#1e1500"),
        "PERFORMING WELL":("var(--green)", "#0a1e10"),
    }
    fg, bg = colors.get(status, ("#6b7088", "#1a1a2a"))
    return f'<span class="badge" style="color:{fg};background:{bg};">{e(status)}</span>'


def delta_html(delta, prefix=""):
    """Render a numeric delta with colour and glow."""
    if delta is None:
        return '<span class="delta-na">—</span>'
    if delta < 0:
        glow = "rgba(255,68,68,0.4)"
        color = "#ff4444"
        sym = "▼"
    elif delta > 0:
        glow = "rgba(42,255,122,0.3)"
        color = "#2aff7a"
        sym = "▲"
    else:
        return '<span class="delta-na">—</span>'
    style = f'color:{color};text-shadow:0 0 8px {glow};'
    return f'<span class="delta" style="{style}">{prefix}{sym}{abs(delta):.1f}</span>'


def build_ticker_html(competitor_sentiment: dict) -> str:
    """Build the auto-scrolling sentiment ticker."""
    items = []
    for comp in COMPETITORS_ORDERED:
        d = competitor_sentiment.get(comp, {})
        score = d.get("score")
        is_barclays = comp == "Barclays"
        no_data = score is None
        color = "#e8a030" if is_barclays else score_color(score)
        score_str = f"{score:.1f}" if not no_data else "no store data"
        num_color = score_num_color(score) if not no_data else "#555566"
        bar = score_bar_html(score, width=40)
        title_attr = ' title="No App Store or Google Play data available for this competitor"' if no_data else ""
        items.append(
            f'<span class="ticker-item{" ticker-barclays" if is_barclays else ""}{" ticker-nodata" if no_data else ""}"{title_attr}>'
            f'<span class="ticker-name" style="color:{color};">{e(comp)}</span>'
            f'<span class="ticker-score" style="color:{num_color};{"font-style:italic;font-size:10px;" if no_data else ""}">{score_str}</span>'
            f'{bar}'
            f'<span class="ticker-delta">{delta_html(None)}</span>'
            f'</span>'
            f'<span class="ticker-sep">-</span>'
        )
    inner = "".join(items)
    # Duplicate for seamless loop
    return (
        '<div class="ticker-track">'
        f'<div class="ticker-inner">{inner}{inner}</div>'
        '</div>'
    )


def build_journey_row_html(journey_analysis: list, competitor_sentiment: dict,
                           journey_meta: dict | None = None) -> str:
    """Build the journey sentiment summary row — fully dynamic, no hardcoded IDs.

    Header reads "TOP 5 AFFECTED JOURNEYS · last Nd · M of K with signal".
    Each cell carries volume + "Nd in priority" (distinct severe days in
    the 30d window), mirroring Box 2's meta shape.

    Three visual signals, decoupled:
      - top-border colour + badge = severity_state (ACUTE / PERSISTENT /
        DRIFT / STABLE) — answers "how bad is this"
      - arrow icon + arrow colour = trend (WORSENING / STABLE / IMPROVING)
        — answers "is it moving"
      - score number colour = sentiment (red <50, white >=50) — answers
        "what do customers think of this journey"

    Cells with <5 reviews carry a muted "low-volume" badge.
    """
    # severity_state → (border colour, badge label)
    sev_colours = {
        "ACUTE":      ("var(--red)",    "ACUTE"),       # severe + moving/new
        "PERSISTENT": ("#B85450",       "PERSISTENT"),  # severe + chronic (muted red)
        "DRIFT":      ("var(--amber)",  "DRIFT"),       # no severe, worsening trend
        "STABLE":     ("var(--green)",  "STABLE"),      # healthy
    }
    # trend → (arrow, colour)
    trend_visual = {
        "WORSENING": ("↘", "var(--red)"),
        "IMPROVING": ("↗", "var(--green)"),
        "STABLE":    ("→", "#7AACBF"),
    }

    cells = []
    for j in journey_analysis:
        sev_state = j.get("severity_state", "STABLE")
        trend     = j.get("trend", "STABLE")
        score     = j.get("score")
        name      = j.get("journey_name") or j.get("journey", "")
        vol       = j.get("volume") or 0
        streak    = j.get("streak_days") or 0

        border_colour, badge_label = sev_colours.get(sev_state, sev_colours["STABLE"])
        arrow, arrow_colour        = trend_visual.get(trend, trend_visual["STABLE"])
        score_str = f"{score:.0f}" if score is not None else "—"
        num_color = score_num_color(score)

        meta_parts = []
        if vol:
            meta_parts.append(f"{vol} review" if vol == 1 else f"{vol} reviews")
        if streak:
            meta_parts.append(
                f"{streak} severe day" if streak == 1 else f"{streak} severe days"
            )
        meta_line = (
            f'<div class="journey-cell-submeta">{" &middot; ".join(meta_parts)}</div>'
            if meta_parts else ""
        )
        lowvol_badge = (
            '<span class="journey-cell-lowvol">low-volume</span>'
            if 0 < vol < 5 else ""
        )

        cells.append(
            f'<div class="journey-cell" style="border-top:3px solid {border_colour};">'
            f'<div class="journey-cell-name">{e(name)}</div>'
            f'<div class="journey-cell-score" style="color:{num_color};">{score_str}</div>'
            f'<div class="journey-cell-meta">'
            f'<span class="traj-icon" style="color:{arrow_colour};">{arrow}</span>'
            f'<span class="journey-status-label" style="color:{border_colour};">{badge_label}</span>'
            f'{lowvol_badge}'
            f'</div>'
            f'{meta_line}'
            f'</div>'
        )

    meta = journey_meta or {}
    window_days    = meta.get("window_days", 7)
    signal_count   = meta.get("signal_count", 0)
    eligible_count = meta.get("eligible_journey_count") or len(journey_analysis) or 1

    # Header row packs three groups on one flex line (title, window sub, label
    # legend). flex-wrap lets narrow viewports drop groups to new lines
    # individually rather than always forcing two rows.
    legend_items = [
        ("ACUTE",      "var(--red)",    "severe + new/worsening"),
        ("PERSISTENT", "#B85450",       "severe &ge; 7d, stable"),
        ("DRIFT",      "var(--amber)",  "no severe, trend worsening"),
        ("STABLE",     "var(--green)",  "quiet"),
    ]
    legend_spans = "".join(
        f'<span class="journey-legend-item">'
        f'<span class="journey-legend-label" style="color:{colour};">{label}</span> '
        f'<span class="journey-legend-def">{definition}</span>'
        f'</span>'
        for label, colour, definition in legend_items
    )
    # Definition of the "severe days" metric used in each tile's meta line —
    # anchored next to the severity-state legend so the count and the states
    # share one learnable glossary.
    legend_spans += (
        '<span class="journey-legend-item journey-legend-metric">'
        '<span class="journey-legend-def">severe day = &ge;1 P0/P1 review, last 30d</span>'
        '</span>'
    )

    header = (
        '<div class="journey-row-header">'
        '<span class="journey-row-title">TOP 5 AFFECTED JOURNEYS</span>'
        f'<span class="journey-row-sub">last {window_days} days &middot; '
        f'{signal_count} of {eligible_count} with signal</span>'
        f'<span class="journey-row-legend">{legend_spans}</span>'
        '</div>'
    )

    return header + '<div class="journey-row">' + "".join(cells) + "</div>"


def build_metrics_strip_html(journey_analysis: list, competitor_sentiment: dict) -> str:
    """Build the 4 top-level metric cards."""
    regression_count = sum(1 for j in journey_analysis if j.get("status") == "REGRESSION")
    watch_count = sum(1 for j in journey_analysis if j.get("status") == "WATCH")
    performing_count = sum(1 for j in journey_analysis if j.get("status") == "PERFORMING WELL")
    barclays_score = competitor_sentiment.get("Barclays", {}).get("score")
    barclays_str = f"{barclays_score:.1f}" if barclays_score is not None else "—"

    def metric_card(label, value, color, sublabel=""):
        sub_html = '<div class="metric-sub">' + e(sublabel) + "</div>" if sublabel else ""
        return (
            f'<div class="metric-card">'
            f'<div class="metric-value" style="color:{color};">{e(str(value))}</div>'
            f'<div class="metric-label">{e(label)}</div>'
            f'{sub_html}'
            f'</div>'
        )

    cards = [
        metric_card("Needs Attention", regression_count, "var(--red)", "REGRESSION journeys"),
        metric_card("Watch", watch_count, "var(--amber)", "WATCH journeys"),
        metric_card("Performing Well", performing_count, "var(--green)", "across all sources"),
    ]
    return '<div class="metrics-strip">' + "".join(cards) + "</div>"


def build_journey_card_html(j: dict) -> str:
    """Build a single journey card for the left column."""
    status = j.get("status", "WATCH")
    status_colors = {
        "REGRESSION": "var(--red)",
        "WATCH": "var(--amber)",
        "PERFORMING WELL": "var(--green)",
    }
    border_color = status_colors.get(status, "var(--amber)")
    score = j.get("score")
    score_str = f"{score:.1f}" if score is not None else "—"
    version = j.get("version_current") or "—"
    verdict = j.get("verdict_text")
    p1 = j.get("p1", 0)
    p2 = j.get("p2", 0)

    # Version delta
    delta = j.get("version_delta")
    if delta is not None:
        if delta < 0:
            delta_style = "color:#ff4444;text-shadow:0 0 8px rgba(255,68,68,0.4);"
            delta_sym = f"▼ {abs(delta):.1f}"
        elif delta > 0:
            delta_style = "color:#2aff7a;text-shadow:0 0 8px rgba(42,255,122,0.3);"
            delta_sym = f"▲ {delta:.1f}"
        else:
            delta_style = "color:#6b7088;"
            delta_sym = "0.0"
    else:
        delta_style = "color:#6b7088;"
        delta_sym = "— no baseline"

    # Customer voice pills
    neg_pills = j.get("neg_pills", [])
    pos_pills = j.get("pos_pills", [])
    pills_html = ""
    for pill in neg_pills:
        pills_html += f'<span class="pill pill-neg">{e(pill)}</span>'
    for pill in pos_pills:
        pills_html += f'<span class="pill pill-pos">{e(pill)}</span>'

    # Derived flag note
    derived_note = ""
    if j.get("is_derived"):
        derived_note = '<div class="derived-note">SIGNAL ANALYSIS — INFERENCE PENDING</div>'

    verdict_html = ""
    if verdict:
        verdict_html = f'<div class="verdict-text">{e(verdict)}</div>'
    else:
        verdict_html = '<div class="verdict-text verdict-baseline">Baseline establishing — check back tomorrow</div>'

    return f"""
<div class="journey-card" style="border-left:3px solid {border_color};">
  <div class="card-header">
    <span class="rank-num">#{j['rank']}</span>
    <span class="journey-name">{e(j['journey_name'])}</span>
    {status_badge_html(status)}
  </div>
  {derived_note}
  <div class="verdict-label">VERDICT</div>
  {verdict_html}
  <div class="version-delta-row">
    <span class="version-label">v{e(version)}</span>
    <code class="version-delta" style="{delta_style}">{e(delta_sym)}</code>
  </div>
  <div class="signal-counts">
    <span class="sig-count sig-p1">P1: {p1}</span>
    <span class="sig-count sig-p2">P2: {p2}</span>
  </div>
  {"<div class='voice-label'>CUSTOMER VOICE</div><div class='pills'>" + pills_html + "</div>" if pills_html else ""}
  <div class="market-note">Market signal analysis — public app store data - {j.get('avg_rating', 0) or 0:.2f} avg rating</div>
</div>
"""


def build_chronicle_html() -> str:
    """Build the CHRONICLE failure library panel."""
    entries = [
        {
            "id": "CHR-001",
            "bank": "TSB Bank",
            "date": "April 2018",
            "type": "Core Banking Migration Failure",
            "impact": "£48.65M fine - 225,492 complaints - 1.9M locked out - 8 months disruption",
            "approved": True,
            "active_match": False,
        },
        {
            "id": "CHR-002",
            "bank": "Lloyds Banking Group",
            "date": "March 2025",
            "type": "API Defect — Data Exposure",
            "impact": "447,936 exposed - 114,182 viewed wrong data - £139K compensation",
            "approved": True,
            "confidence_cap": "0.6 — PARTIAL",
            "active_match": False,
        },
        {
            "id": "CHR-003",
            "bank": "HSBC UK",
            "date": "August 2025",
            "type": "App & Online Banking Outage",
            "impact": "4,000+ DownDetector reports - ~5hr outage - ERR03 pattern",
            "approved": False,
            "inference_hold": True,
            "active_match": False,
        },
        {
            "id": "CHR-004",
            "bank": "Barclays",
            "date": "March 2026",
            "type": "App Friction — Cards Section Crash Cluster",
            "impact": "5 reviews 2026-03-23/25 — probable v8.20.1 regression — enrichment re-run pending",
            "approved": False,
            "inference_hold": True,
            "active_match": False,
        },
    ]

    cards = []
    for entry in entries:
        hold_badge = ""
        if entry.get("inference_hold"):
            hold_badge = '<span class="chronicle-hold">INFERENCE HOLD</span>'
        elif entry.get("confidence_cap"):
            hold_badge = f'<span class="chronicle-cap">CAP {entry["confidence_cap"]}</span>'

        active_badge = '<span class="chronicle-active">ACTIVE MATCH</span>' if entry.get("active_match") else ""

        cards.append(f"""
<div class="chronicle-card">
  <div class="chronicle-header">
    <span class="chronicle-id">{e(entry['id'])}</span>
    <span class="chronicle-bank">{e(entry['bank'])}</span>
    <span class="chronicle-date">{e(entry['date'])}</span>
    {active_badge}{hold_badge}
  </div>
  <div class="chronicle-type">{e(entry['type'])}</div>
  <div class="chronicle-impact">{e(entry['impact'])}</div>
</div>
""")

    return f"""
<div class="panel-section">
  <div class="panel-title">CHRONICLE — Failure Library</div>
  {"".join(cards)}
</div>
"""


def build_inference_card_html(findings: dict) -> str:
    """Build active inference card — only shown if P0/P1 findings exist."""
    active_findings = [
        f for f in findings.get("findings", [])
        if f.get("severity") in ("P0", "P1")
    ]
    if not active_findings:
        return ""

    top = active_findings[0]
    blind_spots = findings.get("blind_spots", [])
    chronicle_ref = top.get("chronicle_ref", "—")

    blind_html = ""
    for bs in blind_spots[:3]:
        blind_html += f'<li class="blind-spot-item">{e(str(bs))}</li>'

    return f"""
<div class="inference-card">
  <div class="inference-header">
    <span class="inference-label">ACTIVE INFERENCE</span>
    <span class="severity-badge severity-{e(top.get('severity','P1')).lower()}">{e(top.get('severity','P1'))}</span>
  </div>
  <div class="inference-finding">{e(top.get('finding','—'))}</div>
  {"<ul class='blind-spots'>" + blind_html + "</ul>" if blind_html else ""}
  <div class="chronicle-anchor">CHRONICLE: {e(chronicle_ref)}</div>
  <div class="inference-actions">
    <button class="action-btn">Escalate</button>
    <button class="action-btn">Add to Watch</button>
    <button class="action-btn">Dismiss</button>
  </div>
</div>
"""


def build_active_inferences_section_html() -> str:
    """Build the ACTIVE INFERENCES panel section for the right column.
    Hardcoded CHR-004 pending — rendered once Refuel enrichment re-run is complete
    and inference_approved is set to true in CHRONICLE.
    """
    return """
<div class="panel-section">
  <div class="panel-title">ACTIVE INFERENCES</div>
<div class="inference-card">
  <div class="inference-header">
    <span class="inference-label">ACTIVE INFERENCE</span>
    <span class="severity-badge severity-p1">P1</span>
  </div>
  <div class="inference-finding">Barclays Cards section crash cluster &#8212; probable v8.20.1 regression. OTP failure on account setup and payment auth loop detected.</div>
  <ul class="blind-spots">
    <li class="blind-spot-item">Root cause unconfirmed &#8212; enrichment re-run pending</li>
    <li class="blind-spot-item">No CHRONICLE similarity score yet &#8212; awaiting Refuel classification</li>
  </ul>
  <div class="chronicle-anchor">CHRONICLE: CHR-004</div>
  <div class="inference-actions">
    <button class="action-btn">View Signals</button>
    <button class="action-btn">CHRONICLE Check</button>
  </div>
</div>
</div>
"""


def build_sources_grid_html(source_coverage: dict) -> str:
    """Build signal sources status grid."""
    source_labels = {
        "downdetector":   "DownDetector",
        "app_store":      "App Store",
        "google_play":    "Google Play",
        "financial_times":"Financial Times",
        "city_am":        "City A.M.",
        "reddit":         "Reddit",
        "trustpilot":     "Trustpilot",
        "facebook":       "Facebook",
        "youtube":        "YouTube",
        "twitter_x":      "Twitter/X",
    }
    trust_weights = {
        "downdetector": 0.95, "app_store": 0.90, "google_play": 0.90,
        "financial_times": 0.90, "city_am": 0.90, "reddit": 0.85,
        "trustpilot": 0.80, "facebook": 0.75, "youtube": 0.75,
        "twitter_x": 0.60,
    }
    status_dots = {
        "active":   ('<span class="dot dot-green"></span>', "var(--green)"),
        "inactive": ('<span class="dot dot-grey"></span>', "#3a3d52"),
        "stub":     ('<span class="dot dot-amber"></span>', "var(--amber)"),
    }

    items = []
    for src_id, label in source_labels.items():
        status = source_coverage.get(src_id, "inactive")
        dot_html, _ = status_dots.get(status, status_dots["inactive"])
        weight = trust_weights.get(src_id, 0.0)
        items.append(
            f'<div class="source-item">'
            f'{dot_html}'
            f'<span class="source-name">{e(label)}</span>'
            f'<span class="source-weight">{weight:.2f}</span>'
            f'</div>'
        )

    return f"""
<div class="panel-section">
  <div class="panel-title">Signal Sources</div>
  <div class="sources-grid">{"".join(items)}</div>
</div>
"""


def generate_html(
    findings: dict,
    signals: list,
    signals_filename: str,
    competitor_sentiment: dict,
    journey_analysis: list,
    source_coverage: dict,
    version_current: str,
    version_previous: str,
    defaults_used: list,
    exec_alert_override: str = "",
    issues_analysis: list | None = None,
    top_quote: str = "",
    top_quote_rating: int = 0,
    top_quote_source: str = "",
    as_quote: str = "",
    as_quote_rating: int = 0,
    as_quote_date: str = "",
    gp_quote: str = "",
    gp_quote_rating: int = 0,
    gp_quote_date: str = "",
    box2_quote: str = "",
    box2_quote_rating: int = 0,
    box2_quote_source: str = "",
    box2_quote_date: str = "",
    box2_issue_type: str = "",
    journey_meta: dict | None = None,
) -> str:
    """Generate the full self-contained HTML briefing page."""

    now_utc = datetime.now(timezone.utc)
    last_run_raw = findings.get("generated_at") or (signals[0].get("timestamp") if signals else None)
    if last_run_raw:
        try:
            if isinstance(last_run_raw, str):
                last_run_dt = datetime.fromisoformat(last_run_raw.replace("Z", "+00:00"))
                last_run_str = last_run_dt.strftime("%Y-%m-%d %H:%M UTC")
            else:
                last_run_str = str(last_run_raw)
        except Exception:
            last_run_str = str(last_run_raw)
    else:
        last_run_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    version_display = version_current or "—"
    is_bootstrap = not bool(findings.get("findings"))

    # issues_analysis drives the Issues section; journey_analysis drives the Journey row
    _issues = issues_analysis if issues_analysis else journey_analysis

    ticker_html = build_ticker_html(competitor_sentiment)
    journey_row_html = build_journey_row_html(journey_analysis, competitor_sentiment,
                                              journey_meta=journey_meta)
    metrics_strip_html = build_metrics_strip_html(_issues, competitor_sentiment)
    inference_card_html = build_inference_card_html(findings)
    chronicle_html = build_chronicle_html()
    active_inferences_html = build_active_inferences_section_html()
    sources_grid_html = build_sources_grid_html(source_coverage)

    journey_cards_html = ""
    for j in _issues:
        journey_cards_html += build_journey_card_html(j)

    # ── Dual quote boxes for Box 1 (App Store + Google Play, Barclays only) ────
    def _build_single_quote_box(text: str, rating: int, source_label: str, date_str: str, label: str = "") -> str:
        if not text:
            return ""
        _qt   = e(text[:280])
        _stars = "★" * rating + "☆" * (5 - rating) if rating else "☆☆☆☆☆"
        _date_part = f" &middot; {e(date_str)}" if date_str else ""
        _footer = (
            f'<div style="font-size:11px;color:#4A7A8F;margin-top:6px;'
            f'letter-spacing:0.03em;white-space:nowrap;">'
            f'{_stars} &middot; {e(source_label)}{_date_part}</div>'
        )
        _is_short = len(text) < 100
        _col_align = "justify-content:center;align-items:center;text-align:center;" if _is_short else "justify-content:flex-start;align-items:flex-start;text-align:left;"
        _label_html = (
            f'<div style="font-size:10px;color:#3A6A7F;letter-spacing:0.1em;'
            f'text-transform:uppercase;margin-bottom:4px;">{e(label)}</div>'
        ) if label else ""
        return (
            f'<div style="height:104px;border:1px solid #003A5C;'
            f'border-radius:8px;padding:10px 12px;display:flex;flex-direction:column;'
            f'{_col_align}background:#001E2E;overflow:hidden;">'
            f'{_label_html}'
            f'<div style="font-size:12px;color:#B8D4E0;font-style:italic;'
            f'line-height:1.5;overflow:hidden;">&ldquo;{_qt}&rdquo;</div>'
            f'{_footer}'
            f'</div>'
        )

    _as_box = _build_single_quote_box(as_quote, as_quote_rating, "App Store", as_quote_date)
    _gp_box = _build_single_quote_box(gp_quote, gp_quote_rating, "Google Play", gp_quote_date)

    if _as_box or _gp_box:
        quote_box_html = (
            f'<div style="display:flex;flex-direction:column;gap:8px;">'
            f'{_as_box}'
            f'{_gp_box}'
            f'</div>'
        )
    else:
        quote_box_html = ""

    published_at = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    # ── Barclays topbar sentiment card data ───────────────────────────────────
    barcl = competitor_sentiment.get("Barclays", {})
    barcl_score = barcl.get("score")
    barcl_score_str = f"{barcl_score:.0f}" if barcl_score is not None else "—"
    barcl_pct = min(100, max(0, barcl_score or 0))
    barcl_p1 = barcl.get("p1", 0)
    # Baseline: Barclays all-time avg from enriched data; delta vs current score
    _barcl_baseline_val = barcl.get("bd_baseline")
    if _barcl_baseline_val is not None:
        barcl_baseline_str = str(_barcl_baseline_val)
        if barcl_score is not None:
            _delta = round(barcl_score - _barcl_baseline_val)
            _sign = "+" if _delta >= 0 else ""
            barcl_delta_str = f"{_sign}{_delta} vs baseline"
        else:
            barcl_delta_str = "— vs baseline"
    else:
        barcl_baseline_str = "Establishing"
        barcl_delta_str = "— vs baseline"
    # Trend: use real 3d/4d split from enriched data if available
    _barcl_trend_raw = barcl.get("bd_trend")
    if _barcl_trend_raw in ("WORSENING", "IMPROVING", "STABLE"):
        barcl_trajectory = _barcl_trend_raw
    else:
        barcl_trajectory = "WORSENING" if barcl_p1 > 0 else ("STABLE" if barcl_score and barcl_score > 65 else "WATCH")
    barcl_traj_color = "#ff4444" if barcl_trajectory == "WORSENING" else ("#e8a030" if barcl_trajectory == "WATCH" else "#2a9a5a")
    barcl_traj_arrow = "&#8600;" if barcl_trajectory == "WORSENING" else ("&#8594;" if barcl_trajectory == "WATCH" else "&#8599;")

    # ── Executive Alert panel data ────────────────────────────────────────────
    total_p0 = sum(d.get("p0", 0) for d in competitor_sentiment.values())
    total_p1 = sum(d.get("p1", 0) for d in competitor_sentiment.values())
    watch_count_tb = sum(1 for j in _issues if j.get("status") == "WATCH")
    alert_p0_str = str(total_p0) if total_p0 > 0 else "NONE"
    alert_p0_class = "status-alert" if total_p0 > 0 else "status-clear"
    alert_p1_count = str(total_p1)
    alert_p1_color = "#ff6666" if total_p1 > 5 else ("#e8a030" if total_p1 > 0 else "#4ad88a")
    top_concern_entry = max(competitor_sentiment.items(), key=lambda x: x[1].get("p1", 0))
    alert_top_concern = top_concern_entry[0] if top_concern_entry[1].get("p1", 0) > 0 else "None"

    # ── Executive Alert panel HTML (pre-computed — f-string cannot do conditionals) ─
    _has_alert = total_p0 > 0 or total_p1 > 3

    # Worst journey from market signals — used as Barclays journey context
    _worst_j = max(journey_analysis, key=lambda j: j.get("p1", 0) * 1.5 + j.get("p2", 0)) if journey_analysis else {}
    _worst_j_name = _worst_j.get("journey_name") or _worst_j.get("journey_id", "App") if _worst_j else "App"

    # Does Barclays have specific signals?
    _barcl_has_signal = barcl_p1 > 0 or (barcl_score is not None and barcl_score < 55)

    if _has_alert:
        if _barcl_has_signal:
            _status_phrase = "elevated risk signals" if barcl_p1 > 0 else "WATCH — declining sentiment"
            _finding_title = f"Barclays {_worst_j_name} journey \u2014 {_status_phrase}"
            _risk_text = (
                f"Customers are reporting problems on the {_worst_j_name} journey — "
                f"{barcl_p1} serious complaint{'s' if barcl_p1 != 1 else ''} flagged in the last 24 hours. "
                f"This matches a pattern seen in previous banking failures."
            )
        else:
            _finding_title = (
                f"Competitor warning — {total_p1} serious issues logged across monitored banks. "
                f"No Barclays-specific problem confirmed yet."
            )
            _risk_text = (
                f"Other banks are seeing problems on their {_worst_j_name} journey. "
                f"Worth checking whether Barclays is exposed to the same risk."
            )
        _action_text = (
            f"Check whether the {_worst_j_name} journey is working as expected. "
            "If customer complaints are rising, escalate to the product team now — don't wait for the next review."
        )
        _p0_pill_style = "background:rgba(204,0,0,0.18);color:#FF4444;border:1px solid rgba(204,0,0,0.4);"
        exec_alert_panel_html = (
            '  <!-- Right: Executive Alert panel -->\n'
            '  <div class="topbar-box exec-alert-panel">\n'
            '    <div class="exec-alert-header">\n'
            '      <span class="exec-alert-pulse"></span>\n'
            '      <span class="exec-alert-title">Executive Alert</span>\n'
            f'      <span class="exec-alert-ts">{e(last_run_str)}</span>\n'
            '    </div>\n'
            '    <div class="exec-alert-body">\n'
            f'      <div class="exec-alert-finding">{e(_finding_title)}</div>\n'
            '      <div class="exec-alert-pills">\n'
            f'        <span class="exec-pill" style="{_p0_pill_style}">P0 &nbsp;{e(alert_p0_str)}</span>\n'
            f'        <span class="exec-pill" style="background:rgba(245,166,35,0.12);color:#F5A623;border:1px solid rgba(245,166,35,0.3);">P1 &nbsp;{e(alert_p1_count)}</span>\n'
            f'        <span class="exec-pill" style="background:rgba(245,166,35,0.08);color:#c0922a;border:1px solid rgba(245,166,35,0.2);">Watch &nbsp;{watch_count_tb}</span>\n'
            '      </div>\n'
            '      <div class="exec-alert-section-label">WHAT THIS MEANS</div>\n'
            f'      <div class="exec-alert-section-text">{e(_risk_text)}</div>\n'
            '      <div class="exec-alert-section-label">WHAT TO DO</div>\n'
            f'      <div class="exec-alert-section-text">{e(_action_text)}</div>\n'
            '    </div>\n'
            '    <div class="exec-alert-footer">\n'
            '      <button class="exec-escalate-btn">Escalate</button>\n'
            '    </div>\n'
            '  </div>'
        )
    else:
        exec_alert_panel_html = (
            '  <!-- Right: Executive Alert panel -->\n'
            '  <div class="topbar-box exec-alert-panel exec-alert-nominal">\n'
            '    <div class="exec-alert-header exec-alert-header-nominal">\n'
            '      <span class="exec-alert-pulse exec-alert-pulse-green"></span>\n'
            '      <span class="exec-alert-title exec-alert-title-nominal">Executive Alert</span>\n'
            f'      <span class="exec-alert-ts">{e(last_run_str)}</span>\n'
            '    </div>\n'
            '    <div class="exec-alert-body">\n'
            '      <div class="exec-nominal-badge">SYSTEMS NOMINAL</div>\n'
            '      <div class="exec-nominal-text">No active P0 or P1 signals detected. All monitored competitors within normal operating parameters.</div>\n'
            '    </div>\n'
            '  </div>'
        )

    # Apply exec_alert_override from briefing_data layer if provided
    if exec_alert_override:
        exec_alert_panel_html = exec_alert_override

    # ── Box 2: Issues Status (pre-computed — metric rows + issue list) ──────
    _reg_count = sum(1 for j in _issues if j.get("status") == "REGRESSION")
    _wat_count = sum(1 for j in _issues if j.get("status") == "WATCH")
    _perf_count = sum(1 for j in _issues if j.get("status") == "PERFORMING WELL")

    _status_colors = {"REGRESSION": "#CC0000", "WATCH": "#F5A623", "PERFORMING WELL": "#00AFA0"}
    _status_arrows = {"REGRESSION": "&#8600;", "WATCH": "&#8594;", "PERFORMING WELL": "&#8599;"}
    _journey_rows = ""
    for _j in _issues:
        _jname = _j.get("journey_name") or _j.get("journey_id", "")
        _jscore = f'{_j["score"]:.0f}' if _j.get("score") is not None else "\u2014"
        _jstatus = _j.get("status", "WATCH")
        _jcolor = _status_colors.get(_jstatus, "#F5A623")
        _jarrow = _status_arrows.get(_jstatus, "&#8594;")
        _jscore_num_color = score_num_color(_j.get("score"))
        _jvol = _j.get("volume")
        _jdays = _j.get("days_active")
        _meta_parts = []
        if _jvol:
            _meta_parts.append(f"{_jvol} review" if _jvol == 1 else f"{_jvol} reviews")
        if _jdays:
            _meta_parts.append(f"{_jdays}d sustained")
        _jmeta = (
            f'            <span class="journey-list-meta">{" &middot; ".join(_meta_parts)}</span>\n'
            if _meta_parts else ""
        )
        _journey_rows += (
            f'        <div class="journey-list-item">\n'
            f'          <span class="journey-list-name">{e(_jname)}</span>\n'
            f'          <span class="journey-list-right">\n'
            f'            <span class="journey-list-score" style="color:{_jscore_num_color};">{_jscore}</span>\n'
            f'{_jmeta}'
            f'            <span class="journey-list-status" style="color:{_jcolor};">{_jarrow} {e(_jstatus)}</span>\n'
            f'          </span>\n'
            f'        </div>\n'
        )

    box2_legend_html = (
        '      <div class="box2-legend">\n'
        '        <span class="box2-legend-item">'
        '<span class="box2-legend-label" style="color:var(--red);">REGRESSION</span> '
        '<span class="box2-legend-def">P0 present or worsening P1s</span>'
        '</span>\n'
        '        <span class="box2-legend-item">'
        '<span class="box2-legend-label" style="color:var(--amber);">WATCH</span> '
        '<span class="box2-legend-def">P1 present or trend worsening</span>'
        '</span>\n'
        '        <span class="box2-legend-item">'
        '<span class="box2-legend-label" style="color:var(--teal);">PERFORMING WELL</span> '
        '<span class="box2-legend-def">no severe signal</span>'
        '</span>\n'
        '      </div>\n'
    )

    box2_html = (
        '  <!-- Middle: Issues Status box -->\n'
        '  <div class="topbar-box">\n'
        '    <div class="topbar-box-header" style="background:#001E30;">\n'
        '      <span class="topbar-box-title" style="color:#7AACBF;">ISSUES STATUS</span>\n'
        '      <span style="font-size:10px;color:#3A6A7F;">today\'s signal summary</span>\n'
        '    </div>\n'
        '    <div class="topbar-box-body">\n'
        '      <div class="issues-stat-row">\n'
        f'        <span class="issues-stat-num" style="color:var(--red);">{_reg_count}</span>\n'
        '        <div><div class="issues-stat-label">Needs Attention</div><div class="issues-stat-sub">REGRESSION journeys</div></div>\n'
        '      </div>\n'
        '      <div class="issues-stat-row">\n'
        f'        <span class="issues-stat-num" style="color:var(--amber);">{_wat_count}</span>\n'
        '        <div><div class="issues-stat-label">Watch</div><div class="issues-stat-sub">WATCH journeys</div></div>\n'
        '      </div>\n'
        '      <div class="issues-stat-row">\n'
        f'        <span class="issues-stat-num" style="color:var(--teal);">{_perf_count}</span>\n'
        '        <div><div class="issues-stat-label">Performing Well</div><div class="issues-stat-sub">across all sources</div></div>\n'
        '      </div>\n'
        '      <div class="issues-divider"></div>\n'
        f'{_journey_rows}'
        f'{_build_single_quote_box(box2_quote, box2_quote_rating, box2_quote_source, box2_quote_date, label=box2_issue_type)}'
        f'{box2_legend_html}'
        '    </div>\n'
        '  </div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sonar — App Intelligence Briefing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* -- Reset & Base ----------------------------------------------------------- */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:          #00273D;
  --topbar-bg:   #001E30;
  --ticker-bg:   #001828;
  --journey-bg:  #001E30;
  --summary-bg:  #002030;
  --feed-bg:     #00273D;
  --panel-bg:    #001828;
  --card:        #002A3F;
  --border:      #003A5C;
  --blue:        #00AEEF;
  --teal:        #00AFA0;
  --amber:       #F5A623;
  --red:         #CC0000;
  --text:        #E8F4FA;
  --text-2:      #7AACBF;
  --text-3:      #4A7A8F;
  --muted:       #3A6A7F;
  --mono:        'DM Mono', monospace;
  --sans:        'Plus Jakarta Sans', sans-serif;
}}

html, body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
}}

a {{ color: var(--blue); text-decoration: none; }}

/* -- Topbar ----------------------------------------------------------------- */
.topbar {{
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  padding: 16px 24px;
  background: var(--topbar-bg);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  align-items: stretch;
}}
/* Topbar shared box style */
.topbar-box {{ background: #002A3F; border: 1px solid #003A5C; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }}
.topbar-box-header {{ padding: 10px 16px; border-bottom: 1px solid #003A5C; display: flex; align-items: center; justify-content: space-between; }}
.topbar-box-title {{ font-size: 13px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; }}
.topbar-box-body {{ padding: 14px 16px; flex: 1; display: flex; flex-direction: column; gap: 10px; }}
/* Box 1 brand */
.topbar-left {{ display: flex; flex-direction: column; }}
/* Box 2 issues status */
.issues-stat-row {{ display: flex; align-items: center; gap: 12px; }}
.issues-stat-num {{ font-family: var(--mono); font-size: 40px; font-weight: 800; line-height: 1; min-width: 52px; }}
.issues-stat-label {{ font-size: 12px; font-weight: 700; letter-spacing: 1.5px; color: var(--text-3); text-transform: uppercase; }}
.issues-stat-sub {{ font-size: 13px; color: var(--text-2); margin-top: 2px; }}
.issues-divider {{ height: 1px; background: #003A5C; margin: 4px 0; }}
/* Box 2 legend — compact footnote explaining REGRESSION/WATCH/PERFORMING WELL.
   Single row via flex-wrap so items flow left-to-right and only wrap when
   the box is narrower than their combined width. Matches the Journey Row
   legend pattern. */
.box2-legend {{ margin-top: 14px; padding-top: 10px; border-top: 1px solid #003A5C;
                display: flex; flex-wrap: wrap; gap: 4px 14px;
                font-size: 10px; line-height: 1.4; }}
.box2-legend-item {{ white-space: nowrap; }}
.box2-legend-label {{ font-weight: 800; letter-spacing: 1px; text-transform: uppercase; }}
.box2-legend-def {{ color: #4A7A8F; }}
/* Journey list in box 2 */
.journey-list-item {{ display: flex; align-items: center; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #001E30; font-size: 14px; }}
.journey-list-item:last-child {{ border-bottom: none; }}
.journey-list-name {{ color: #7AACBF; font-weight: 600; }}
.journey-list-right {{ display: flex; align-items: center; gap: 6px; }}
.journey-list-score {{ font-family: var(--mono); font-size: 16px; font-weight: 700; }}
.journey-list-meta {{ color: #4A7A8F; font-size: 11px; font-weight: 500; }}
.journey-list-status {{ font-size: 10px; font-weight: 700; }}
.topbar-logo {{
  font-weight: 800;
  font-size: 17px;
  letter-spacing: 1.5px;
  color: var(--blue);
  margin-bottom: 2px;
}}
.brand-line {{
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 15px;
  font-weight: 400;
  color: var(--text-2);
  line-height: 1.4;
}}
.brand-dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 3px; }}
.brand-dot-blue {{ background: #00AEEF; box-shadow: 0 0 4px rgba(0,174,239,0.5); }}
.brand-dot-teal {{ background: #00AFA0; box-shadow: 0 0 4px rgba(0,175,160,0.5); }}

/* Barclays sentiment card — compact 2-line */
.topbar-sent-card {{ background: #002A3F; border: 1px solid #00AEEF; border-radius: 8px; overflow: hidden; margin-top: 0; margin-bottom: 0; max-width: 100%; width: 100%; }}
.sent-card-bar {{ height: 2px; background: linear-gradient(90deg, #00AEEF, #0080C0); }}
.sent-card-inner {{ padding: 8px 14px; display: flex; flex-direction: column; gap: 3px; }}
.sent-row-1 {{ display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }}
.sent-row-2 {{ display: flex; align-items: center; justify-content: space-between; }}
.sent-card-label {{ font-size: 15px; font-weight: 700; letter-spacing: 2px; color: #00AEEF; text-transform: uppercase; flex-shrink: 0; }}
.sent-card-score {{ font-family: var(--mono); font-size: 36px; font-weight: 800; color: #E8F4FA; line-height: 1; }}
.sent-card-delta {{ font-family: var(--mono); font-size: 16px; font-weight: 600; }}
.sent-card-traj {{ font-size: 10px; font-weight: 700; margin-left: auto; white-space: normal; }}
.sent-card-baseline {{ font-family: var(--mono); font-size: 10px; color: #4A7A8F; }}
.sent-card-progress {{ height: 2px; background: #003A5C; border-radius: 1px; overflow: hidden; margin-top: 3px; }}
.sent-progress-fill {{ height: 2px; background: linear-gradient(90deg, #00AEEF, #0080C0); border-radius: 1px; }}
.sent-card-ts {{ font-family: var(--mono); font-size: 10px; color: #3A6A7F; }}

/* Pills row */
.topbar-pills {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 3px; }}
.version-pill {{ font-family: var(--mono); font-size: 12px; color: var(--text-3); background: var(--card); border: 1px solid var(--border); padding: 2px 8px; border-radius: 4px; }}
.live-dot {{ display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--teal); font-weight: 600; letter-spacing: 0.05em; }}
.live-dot::before {{ content: ''; width: 7px; height: 7px; background: var(--teal); border-radius: 50%; animation: pulse 2s ease-in-out infinite; }}
@keyframes pulse {{
  0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(0,175,160,0.4); }}
  50% {{ opacity: 0.7; box-shadow: 0 0 0 5px rgba(0,175,160,0); }}
}}
.bootstrap-badge {{ font-size: 11px; padding: 2px 8px; border-radius: 12px; background: rgba(245,166,35,0.10); color: var(--amber); border: 1px solid rgba(245,166,35,0.3); font-family: var(--mono); letter-spacing: 0.05em; }}

/* Executive Alert panel */
.exec-alert-panel {{ background: #001828; border: 1px solid #CC0000; border-radius: 12px; overflow: hidden; }}
.exec-alert-header {{ background: #1A0000; border-bottom: 1px solid #CC0000; padding: 8px 14px; display: flex; align-items: center; gap: 8px; }}
.exec-alert-pulse {{ width: 7px; height: 7px; border-radius: 50%; background: #CC0000; animation: pulse-red 1.5s ease-in-out infinite; flex-shrink: 0; }}
@keyframes pulse-red {{
  0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(204,0,0,0.5); }}
  50% {{ opacity: 0.8; box-shadow: 0 0 0 4px rgba(204,0,0,0); }}
}}
.exec-alert-title {{ font-size: 11px; font-weight: 800; letter-spacing: 2px; color: #CC0000; text-transform: uppercase; flex: 1; }}
.exec-alert-ts {{ font-family: var(--mono); font-size: 10px; color: #4A2A2A; }}
.exec-alert-body {{ padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }}
.exec-alert-row {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; padding-bottom: 6px; border-bottom: 1px solid #2A1010; }}
.exec-alert-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
.exec-alert-key {{ font-size: 11px; color: #9A8080; }}
.exec-alert-val {{ font-size: 12px; font-weight: 600; font-family: var(--mono); }}
.exec-alert-status {{ font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 12px; letter-spacing: 1px; }}
.status-clear {{ background: rgba(0,175,160,0.12); color: #00AFA0; }}
.status-watch {{ background: rgba(245,166,35,0.12); color: #F5A623; }}
.status-alert {{ background: rgba(204,0,0,0.15); color: #FF4444; }}
/* Nominal state overrides */
.exec-alert-nominal {{ border-color: #00AFA0; }}
.exec-alert-header-nominal {{ background: #001A18; border-bottom-color: #00AFA0; }}
.exec-alert-pulse-green {{ background: #00AFA0; animation: none; }}
.exec-alert-title-nominal {{ color: #00AFA0; }}
/* Finding + pills */
.exec-alert-finding {{ font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 6px; }}
.exec-alert-pills {{ display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px; }}
.exec-pill {{ font-family: var(--mono); font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 10px; letter-spacing: 0.04em; }}
.exec-alert-section-label {{ font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: var(--text-3); text-transform: uppercase; margin-top: 8px; margin-bottom: 3px; padding-bottom: 4px; }}
.exec-alert-section-text {{ font-size: 13px; color: var(--text-2); line-height: 1.5; padding-bottom: 4px; }}
.exec-alert-footer {{ padding: 8px 14px; border-top: 1px solid #2A1010; }}
.exec-escalate-btn {{ background: rgba(204,0,0,0.15); color: #FF4444; border: 1px solid rgba(204,0,0,0.4); border-radius: 6px; font-size: 13px; font-weight: 700; letter-spacing: 0.08em; padding: 5px 14px; cursor: pointer; width: 100%; font-family: var(--sans); text-transform: uppercase; }}
.exec-escalate-btn:hover {{ opacity: 0.8; }}
.exec-alert-footnote {{ padding: 8px 14px 10px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }}
.exec-alert-footnote span {{ font-size: 10px; color: var(--text-3); font-family: var(--mono); line-height: 1.4; }}
.exec-fn-sep {{ color: var(--text-3); opacity: 0.4; padding: 0 2px; }}
/* Nominal body text */
.exec-nominal-badge {{ font-size: 12px; font-weight: 800; letter-spacing: 1.5px; color: #00AFA0; margin-bottom: 8px; }}
.exec-nominal-text {{ font-size: 11px; color: var(--text-2); line-height: 1.5; }}

/* -- Ticker ----------------------------------------------------------------- */
.ticker-wrapper {{ overflow: hidden; background: var(--ticker-bg); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 11px 0; }}
.ticker-track {{ overflow: hidden; white-space: nowrap; }}
.ticker-inner {{ display: inline-flex; align-items: center; animation: ticker-scroll 30s linear infinite; }}
.ticker-inner:hover {{ animation-play-state: paused; }}
@keyframes ticker-scroll {{
  0%   {{ transform: translateX(0); }}
  100% {{ transform: translateX(-50%); }}
}}
.ticker-item {{ display: inline-flex; align-items: center; gap: 6px; padding: 0 20px; }}
.ticker-barclays {{ background: rgba(0,174,239,0.06); border-radius: 4px; }}
.ticker-name {{ font-size: 13px; font-weight: 600; color: var(--text-2); }}
.ticker-barclays .ticker-name {{ font-size: 13px; font-weight: 800; color: #00AEEF; }}
.ticker-score {{ font-family: var(--mono); font-size: 15px; font-weight: 700; }}
.ticker-delta {{ font-family: var(--mono); font-size: 10px; }}
.ticker-sep {{ color: var(--border); padding: 0 4px; font-size: 18px; }}

/* -- Mini Bar --------------------------------------------------------------- */
.mini-bar {{ display: inline-flex; align-items: center; width: 60px; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }}
.mini-bar-fill {{ height: 4px; border-radius: 2px; transition: width 0.3s ease; }}

/* -- Journey Row ------------------------------------------------------------ */
.journey-row-header {{ display: flex; align-items: baseline; flex-wrap: wrap;
                       padding: 10px 20px; border-top: 1px solid var(--border);
                       background: var(--journey-bg); gap: 6px 18px; }}
.journey-row-title {{ font-size: 12px; font-weight: 800; color: var(--text-2); letter-spacing: 1.8px; text-transform: uppercase; }}
.journey-row-sub {{ font-size: 10px; color: #4A7A8F; font-family: var(--mono); letter-spacing: 0.5px; }}
.journey-row-legend {{ display: inline-flex; flex-wrap: wrap; gap: 2px 14px;
                       margin-left: auto; font-size: 9px; line-height: 1.4; }}
.journey-legend-item {{ white-space: nowrap; }}
.journey-legend-label {{ font-weight: 800; letter-spacing: 1px; text-transform: uppercase; }}
.journey-legend-def {{ color: #4A7A8F; }}
.journey-row {{ display: flex; gap: 1px; background: var(--border); border-bottom: 2px solid var(--border); }}
.journey-cell {{ flex: 1; padding: 10px 32px; background: var(--journey-bg); cursor: default; transition: background 0.15s; }}
.journey-cell:hover {{ background: #002440; }}
.journey-cell-name {{ font-size: 13px; font-weight: 700; color: var(--text-2); letter-spacing: 1px; margin-bottom: 4px; text-transform: uppercase; }}
.journey-cell-score {{ font-size: 30px; font-weight: 800; font-family: var(--mono); margin-bottom: 4px; }}
.journey-cell-meta {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
.journey-cell-submeta {{ font-size: 10px; color: #4A7A8F; font-family: var(--mono); margin-top: 4px; letter-spacing: 0.3px; }}
.journey-cell-lowvol {{ font-size: 8px; color: #7AACBF; background: #003A5C; border-radius: 3px;
                        padding: 1px 6px; letter-spacing: 1px; text-transform: uppercase; margin-left: 4px; font-weight: 600; }}
.traj-icon {{ font-size: 14px; }}
.journey-status-label {{ font-size: 10px; font-weight: 700; letter-spacing: 0.06em; font-family: var(--mono); color: var(--text-3); }}

/* -- Metrics Strip ---------------------------------------------------------- */
.metrics-strip {{ display: flex; gap: 1px; background: var(--border); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
.metric-card {{ flex: 1; padding: 12px 32px; background: var(--summary-bg); }}
.metric-value {{ font-size: 28px; font-weight: 800; font-family: var(--mono); line-height: 1; margin-bottom: 4px; }}
.metric-label {{ font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: var(--text-3); text-transform: uppercase; }}
.metric-sub {{ font-size: 12px; color: var(--text-2); margin-top: 2px; }}

/* -- Body Layout ------------------------------------------------------------ */
.body-wrapper {{ display: grid; grid-template-columns: 1fr 360px; gap: 1px; background: var(--border); min-height: calc(100vh - 200px); }}
.left-col {{ background: var(--feed-bg); padding: 18px 32px 24px; display: flex; flex-direction: column; gap: 16px; }}
.right-col {{ background: var(--panel-bg); padding: 16px 18px; display: flex; flex-direction: column; gap: 16px; }}

/* -- Journey Cards ---------------------------------------------------------- */
.journey-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }}
.card-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.rank-num {{ font-family: var(--mono); font-size: 12px; font-weight: 800; color: var(--text-3); background: var(--border); width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
.journey-name {{ font-size: 16px; font-weight: 700; color: var(--text); flex: 1; }}
.badge {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 2px 10px; border-radius: 12px; }}
.derived-note {{ font-size: 11px; font-family: var(--mono); color: var(--amber); background: rgba(245,166,35,0.08); padding: 3px 8px; border-radius: 12px; }}
.verdict-label {{ font-size: 10px; font-weight: 700; letter-spacing: 2px; color: var(--blue); text-transform: uppercase; }}
.verdict-text {{ font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.65; }}
.verdict-baseline {{ color: var(--text-3); font-weight: 400; font-style: italic; }}
.version-delta-row {{ display: flex; align-items: center; gap: 12px; }}
.version-label {{ font-family: var(--mono); font-size: 10px; font-weight: 700; color: var(--blue); background: var(--border); padding: 2px 6px; border-radius: 4px; }}
.version-delta {{ font-family: var(--mono); font-size: 12px; font-weight: 500; background: var(--border); padding: 2px 8px; border-radius: 4px; }}
.signal-counts {{ display: flex; gap: 8px; }}
.sig-count {{ font-family: var(--mono); font-size: 11px; padding: 1px 6px; border-radius: 12px; }}
.sig-p1 {{ background: rgba(204,0,0,0.15); color: #FF4444; border: 1px solid rgba(204,0,0,0.2); }}
.sig-p2 {{ background: rgba(245,166,35,0.10); color: var(--amber); border: 1px solid rgba(245,166,35,0.2); }}
.voice-label {{ font-size: 10px; font-weight: 700; letter-spacing: 2px; color: var(--blue); text-transform: uppercase; }}
.pills {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.pill {{ font-size: 11px; font-weight: 500; padding: 2px 10px; border-radius: 20px; }}
.pill-neg {{ background: #2A0010; color: #E08080; border: 1px solid #4A0020; }}
.pill-pos {{ background: #003A30; color: #7ADAC8; border: 1px solid #005A48; }}
.detected-pill {{ font-family: var(--mono); font-size: 11px; color: var(--text-2); background: var(--border); border-radius: 20px; padding: 1px 8px; }}
.market-note {{ font-size: 11px; color: var(--muted); font-style: italic; }}

/* -- Right Panel ------------------------------------------------------------ */
.panel-section {{ display: flex; flex-direction: column; gap: 10px; }}
.panel-title {{ font-size: 11px; font-weight: 700; letter-spacing: 2px; color: var(--blue); text-transform: uppercase; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}

/* -- Inference Card --------------------------------------------------------- */
.inference-card {{ background: var(--card); border: 1px solid var(--red); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }}
.inference-header {{ display: flex; align-items: center; gap: 8px; }}
.inference-label {{ font-size: 11px; font-weight: 800; letter-spacing: 2px; color: var(--red); text-transform: uppercase; }}
.severity-badge {{ font-size: 10px; font-weight: 700; padding: 1px 8px; border-radius: 12px; }}
.severity-p0 {{ background: rgba(204,0,0,0.3); color: #FF4444; }}
.severity-p1 {{ background: rgba(204,0,0,0.15); color: #FF6666; }}
.inference-finding {{ font-size: 13px; font-weight: 700; color: var(--text); line-height: 1.5; }}
.blind-spots {{ list-style: none; padding-left: 0; display: flex; flex-direction: column; gap: 4px; }}
.blind-spot-item {{ font-size: 11px; color: #9A8080; line-height: 1.5; padding-left: 12px; position: relative; }}
.blind-spot-item::before {{ content: '\26A0'; position: absolute; left: 0; font-size: 9px; color: var(--amber); }}
.chronicle-anchor {{ font-family: var(--mono); font-size: 11px; color: var(--blue); }}
.inference-actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.action-btn {{ background: #1A0000; color: var(--red); border: 1px solid #4A1010; border-radius: 12px; padding: 3px 10px; font-size: 10px; font-weight: 500; cursor: pointer; transition: background 0.15s; }}
.action-btn:hover {{ background: rgba(204,0,0,0.1); }}

/* -- Chronicle -------------------------------------------------------------- */
.chronicle-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; display: flex; flex-direction: column; gap: 5px; }}
.chronicle-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.chronicle-id {{ font-family: var(--mono); font-size: 11px; font-weight: 600; color: #8BBCCC; }}
.chronicle-bank {{ font-size: 11px; font-weight: 600; color: #8BBCCC; flex: 1; }}
.chronicle-date {{ font-size: 10px; color: var(--muted); font-family: var(--mono); }}
.chronicle-active {{ font-size: 9px; font-weight: 700; letter-spacing: 1px; background: rgba(204,0,0,0.2); color: #FF6666; padding: 1px 5px; border-radius: 8px; }}
.chronicle-hold {{ font-size: 9px; font-weight: 700; background: rgba(74,122,143,0.2); color: var(--text-3); padding: 1px 5px; border-radius: 8px; }}
.chronicle-cap {{ font-size: 9px; color: var(--amber); background: rgba(245,166,35,0.1); padding: 1px 5px; border-radius: 8px; }}
.chronicle-type {{ font-size: 10px; color: #3A5A6F; }}
.chronicle-impact {{ font-size: 11px; font-weight: 700; color: var(--amber); font-family: var(--mono); }}

/* -- Sources Grid ----------------------------------------------------------- */
.sources-grid {{ display: flex; flex-direction: column; gap: 4px; }}
.source-item {{ display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--border); }}
.source-item:last-child {{ border-bottom: none; }}
.dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
.dot-green {{ background: var(--teal); box-shadow: 0 0 4px rgba(0,175,160,0.6); }}
.dot-amber {{ background: var(--amber); box-shadow: 0 0 4px rgba(245,166,35,0.5); }}
.dot-grey {{ background: var(--border); }}
.source-name {{ font-size: 11px; font-weight: 500; color: var(--muted); flex: 1; }}
.source-weight {{ font-family: var(--mono); font-size: 11px; color: var(--text-3); }}

/* -- Delta ------------------------------------------------------------------ */
.delta {{ font-family: var(--mono); font-size: 11px; font-weight: 600; }}
.delta-na {{ font-family: var(--mono); font-size: 11px; color: var(--text-3); }}

/* -- Defaults Banner -------------------------------------------------------- */
.defaults-banner {{ margin: 12px 32px; padding: 10px 16px; background: rgba(245,166,35,0.06); border: 1px solid rgba(245,166,35,0.15); border-radius: 8px; font-size: 11px; color: var(--amber); }}
.defaults-banner ul {{ padding-left: 16px; margin-top: 4px; }}
.defaults-banner li {{ margin-top: 2px; }}

/* -- Footer ----------------------------------------------------------------- */
.footer {{ background: var(--topbar-bg); border-top: 1px solid var(--border); padding: 16px 32px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
.footer-item {{ font-size: 11px; color: #2A5A6F; font-family: var(--mono); letter-spacing: 1px; }}
.footer-sep {{ color: var(--border); }}
.footer-sovereign {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--blue); background: rgba(0,174,239,0.08); padding: 2px 8px; border-radius: 8px; }}

/* -- Ask Sonar Button ------------------------------------------------------- */
.ask-sonar-btn {{ position: fixed; bottom: 24px; right: 24px; background: #00AEEF; color: #001E30; border: none; border-radius: 24px; padding: 11px 20px 11px 16px; font-family: var(--sans); font-size: 13px; font-weight: 700; cursor: pointer; z-index: 1000; box-shadow: 0 4px 24px rgba(0,174,239,0.4); transition: transform 0.15s, box-shadow 0.15s; display: flex; align-items: center; gap: 8px; }}
.ask-sonar-btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 32px rgba(0,174,239,0.55); }}
.ask-sonar-btn svg {{ width: 16px; height: 16px; }}

/* -- Chat Panel ------------------------------------------------------------- */
.chat-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 999; }}
.chat-panel {{ position: fixed; bottom: 80px; right: 24px; width: 440px; height: 620px; max-height: calc(100vh - 110px); background: var(--card); border: 1px solid var(--border); border-radius: 12px; display: none; flex-direction: column; z-index: 1001; box-shadow: 0 8px 40px rgba(0,0,0,0.6); overflow: hidden; }}
.chat-panel.open {{ display: flex; }}
.chat-header {{ padding: 10px 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; background: var(--topbar-bg); }}
.chat-title {{ font-size: 13px; font-weight: 700; color: var(--text); flex: 1; }}
.chat-close {{ background: none; border: none; color: var(--text-3); cursor: pointer; font-size: 20px; line-height: 1; padding: 0 4px; }}
.chat-close:hover {{ color: var(--text); }}
.chat-iframe {{ flex: 1; border: 0; width: 100%; background: #00273D; }}
.chat-messages {{ flex: 1; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; min-height: 160px; }}
.chat-chips {{ padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 6px; border-top: 1px solid var(--border); }}
.chip {{ background: var(--border); color: var(--blue); border: 1px solid rgba(0,174,239,0.2); border-radius: 14px; padding: 4px 10px; font-size: 11px; cursor: pointer; transition: background 0.15s; }}
.chip:hover {{ background: rgba(0,174,239,0.1); }}
.chat-input-row {{ padding: 10px 12px; border-top: 1px solid var(--border); display: flex; gap: 8px; }}
.chat-input {{ flex: 1; background: var(--topbar-bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; font-family: var(--sans); font-size: 12px; color: var(--text); outline: none; }}
.chat-input:focus {{ border-color: var(--blue); }}
.chat-send {{ background: var(--blue); color: #001E30; border: none; border-radius: 6px; padding: 8px 14px; font-weight: 700; font-size: 12px; cursor: pointer; }}
.chat-msg {{ font-size: 12px; line-height: 1.5; padding: 8px 10px; border-radius: 8px; }}
.chat-msg.system {{ background: var(--border); color: var(--text); }}
.chat-msg.user {{ background: rgba(0,174,239,0.1); color: var(--blue); align-self: flex-end; }}
.chat-msg.error {{ background: rgba(204,0,0,0.1); color: #FF6666; }}

/* -- Responsive ------------------------------------------------------------- */
@media (max-width: 768px) {{
  .topbar {{ grid-template-columns: 1fr; gap: 12px; padding: 12px 16px; position: relative; }}
  .topbar-box {{ min-height: 280px; }}
  .sent-card-score {{ font-size: 48px; }}
  .body-wrapper {{ grid-template-columns: 1fr; }}
  .journey-row {{ flex-wrap: wrap; }}
  .journey-cell {{ min-width: 45%; }}
}}
</style>
</head>
<body>

<!-- -- Topbar -------------------------------------------------------------- -->
<div class="topbar">

  <!-- Box 1: Brand + Sentiment + Quote -->
  <div class="topbar-box topbar-left">
    <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
      <span class="topbar-logo" style="margin:0;">CJI SONAR &mdash; APP INTELLIGENCE</span>
    </div>
    <div class="topbar-box-body" style="gap:8px;">
      <div class="topbar-sent-card" style="margin-top:0;">
        <div class="sent-card-bar"></div>
        <div class="sent-card-inner">
          <div class="sent-row-1">
            <span class="sent-card-label">BARCLAYS SENTIMENT</span>
            <span class="sent-card-score" style="margin-left:auto;color:{score_num_color(barcl_score)};">{barcl_score_str}</span>
            <span class="sent-card-delta" style="color:{barcl_traj_color};">{barcl_delta_str}</span>
            <span class="sent-card-traj" style="color:{barcl_traj_color};">{barcl_traj_arrow} {barcl_trajectory}</span>
          </div>
          <div class="sent-row-2">
            <span class="sent-card-baseline">Baseline: {barcl_baseline_str}</span>
            <span class="sent-card-ts">{e(last_run_str)}</span>
          </div>
          <div class="sent-card-progress">
            <div class="sent-progress-fill" style="width:{barcl_pct:.0f}%;"></div>
          </div>
        </div>
      </div>
      {quote_box_html}
      <div class="brand-line">
        <span class="brand-dot brand-dot-blue"></span>
        <span>Live signals from App Store, Google Play, news and social &mdash; updated daily</span>
      </div>
      <div class="brand-line">
        <span class="brand-dot brand-dot-teal"></span>
        <span>Historical failure patterns applied &mdash; act on intelligence, not on incident reports</span>
      </div>
      <div class="topbar-pills" style="margin-top:auto;">
        <span class="version-pill">v{e(version_display)}</span>
        <span class="version-pill">{e(last_run_str)}</span>
        {"<span class='bootstrap-badge'>BASELINE ESTABLISHING</span>" if is_bootstrap else ""}
        <div class="live-dot">LIVE</div>
      </div>
      <div style="font-size:10px;color:#3A6A7F;margin-top:6px;line-height:1.4;">
        Sentiment score: 7-day rolling avg &middot; App Store &amp; Google Play &middot; Barclays only &middot; star ratings inc. text-free reviews
      </div>
    </div>
  </div>

{box2_html}
{exec_alert_panel_html}
</div>

<!-- -- Sentiment Ticker ---------------------------------------------------- -->
<div class="ticker-wrapper">
  {ticker_html}
</div>

<!-- -- Journey Sentiment Row ----------------------------------------------- -->
{journey_row_html}

<!-- -- Body: Left + Right Columns ------------------------------------------ -->
<div class="body-wrapper">
  <div class="left-col">
    {metrics_strip_html}
    {journey_cards_html}
  </div>
  <div class="right-col">
    {chronicle_html}
    {active_inferences_html}
    {sources_grid_html}
  </div>
</div>

<!-- -- Footer -------------------------------------------------------------- -->
<div class="footer">
  <span class="footer-item">INFERENCE LOCAL</span>
  <span class="footer-sep">-</span>
  <span class="footer-item">PUBLISHED OUTPUT ONLY</span>
  <span class="footer-sep">-</span>
  <span class="footer-item">sonar.cjipro.com/briefing</span>
  <span class="footer-sep">-</span>
  <span class="footer-item">Sonar v0.6</span>
  <span class="footer-sep">-</span>
  <span class="footer-sovereign">SOVEREIGN</span>
  <span class="footer-sep">-</span>
  <span class="footer-item">Article Zero</span>
  <span class="footer-sep">-</span>
  <span class="footer-item">Published {e(published_at)}</span>
</div>

<!-- -- Ask Sonar Button ----------------------------------------------------- -->
<button class="ask-sonar-btn" onclick="openChat()" aria-label="Ask CJI Pro">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
  Ask CJI Pro
</button>

<!-- -- Chat Panel (iframe → sonar.cjipro.com, the canonical UI) ------------ -->
<div class="chat-panel" id="chatPanel">
  <div class="chat-header">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#e8a030" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
    <span class="chat-title">Ask CJI Pro</span>
    <a href="https://sonar.cjipro.com/" target="_blank" rel="noopener" style="color:var(--text-3);text-decoration:none;font-size:11px;margin-right:8px" title="Open in new tab">↗</a>
    <button class="chat-close" onclick="closeChat()">&#215;</button>
  </div>
  <iframe id="chatFrame" class="chat-iframe" title="Ask CJI Pro" loading="lazy" src="about:blank"></iframe>
</div>

<script>
// -- Chat Panel (iframe-backed) ---------------------------------------------
// The chat UI lives at https://sonar.cjipro.com/ and is served by the same
// backend the briefing calls. The iframe lazy-loads on first open so the
// briefing page itself stays snappy.
const CHAT_URL = 'https://sonar.cjipro.com/';

function openChat() {{
  const panel = document.getElementById('chatPanel');
  const frame = document.getElementById('chatFrame');
  if (frame.src === 'about:blank' || !frame.src.startsWith(CHAT_URL)) {{
    frame.src = CHAT_URL;
  }}
  panel.classList.add('open');
}}
function closeChat() {{
  document.getElementById('chatPanel').classList.remove('open');
}}

// Close on outside click
document.addEventListener('click', function(e) {{
  const panel = document.getElementById('chatPanel');
  const btn = document.querySelector('.ask-sonar-btn');
  if (panel.classList.contains('open') && !panel.contains(e.target) && !btn.contains(e.target)) {{
    closeChat();
  }}
}});
</script>

</body>
</html>"""


# -----------------------------------------------------------------------------
# GITHUB PAGES PUBLISHING
# -----------------------------------------------------------------------------

def publish_to_github_pages(html_content: str, env: dict) -> tuple[bool, str]:
    """
    Push index.html to GitHub Pages repo at briefing/index.html.
    Returns (success, message).
    """
    token = env.get("GITHUB_TOKEN", "")
    repo_url = env.get("PUBLISH_REPO", "")

    if not token:
        return False, "GITHUB_TOKEN not set in .env"
    if not repo_url:
        return False, "PUBLISH_REPO not set in .env"

    # Normalise repo URL — accept both https://... and owner/repo shorthand
    if repo_url.startswith("https://"):
        auth_url = repo_url.replace("https://", f"https://{token}@")
    elif "/" in repo_url and not repo_url.startswith("git@"):
        # owner/repo shorthand → full GitHub HTTPS URL
        slug = repo_url.rstrip("/")
        if not slug.endswith(".git"):
            slug += ".git"
        auth_url = f"https://{token}@github.com/{slug}"
    else:
        return False, f"PUBLISH_REPO format not recognised: {repo_url[:40]}"

    commit_msg = f"publish: Sonar briefing {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        clone_dir = tmp / "pages_repo"

        print(f"  Cloning {repo_url} …")
        result = subprocess.run(
            ["git", "clone", "--depth=1", auth_url, str(clone_dir)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            # Mask token in error
            err = result.stderr.replace(token, "***")
            return False, f"git clone failed: {err.strip()}"

        # Write index.html to briefing/
        briefing_dir = clone_dir / "briefing"
        briefing_dir.mkdir(exist_ok=True)
        dest = briefing_dir / "index.html"
        dest.write_text(html_content, encoding="utf-8")
        print(f"  Written to {dest}")

        # git config (required in CI environments)
        subprocess.run(
            ["git", "-C", str(clone_dir), "config", "user.email", "sonar-publish@cjipro.com"],
            capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "config", "user.name", "Sonar Publisher"],
            capture_output=True
        )

        # git add
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "add", "briefing/index.html"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return False, f"git add failed: {result.stderr.strip()}"

        # git commit
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "commit", "-m", commit_msg],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            if "nothing to commit" in stdout or "nothing to commit" in stderr:
                return True, "Nothing to commit — page is already up to date"
            return False, f"git commit failed: {stderr}"

        # git push
        print("  Pushing to main …")
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "push", "origin", "main"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            err = result.stderr.replace(token, "***")
            return False, f"git push failed: {err.strip()}"

    return True, commit_msg


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n-- Sonar Briefing Publisher --")
    print(f"  MIL dir:   {MIL_DIR}")
    print(f"  Output:    {OUTPUT_DIR}")

    all_defaults: list[str] = []

    # 1. Load env
    env = load_env()
    if not env.get("GITHUB_TOKEN"):
        print("  WARN: GITHUB_TOKEN not found in .env")
    if not env.get("PUBLISH_REPO"):
        print("  WARN: PUBLISH_REPO not found in .env")

    # 2. Load findings
    print("\n[1/5] Loading mil_findings.json …")
    findings, errs = load_findings()
    if errs:
        all_defaults.extend(errs)
    findings_bound = bool(findings.get("findings"))
    print(f"  findings: {'LIVE (' + str(len(findings['findings'])) + ' entries)' if findings_bound else 'BOOTSTRAP (empty — using signal-derived analysis)'}")

    # 3. Load signals
    print("\n[2/5] Loading latest signals file …")
    signals, signals_filename, errs = load_latest_signals()
    if errs:
        all_defaults.extend(errs)
        print(f"  WARN: {errs}")
    else:
        print(f"  Loaded {len(signals)} signals from {signals_filename}")

    # 4. Compute data
    print("\n[3/5] Computing sentiment and journey analysis …")
    competitor_sentiment = compute_competitor_sentiment(signals)
    for comp, d in competitor_sentiment.items():
        marker = " ◀ Barclays (brand competitor)" if comp == "Barclays" else ""
        print(f"  {comp:12s} score={d['score'] or '—':>6}  n={d['count']:>4}  P1={d['p1']}  P2={d['p2']}{marker}")

    journey_analysis = compute_journey_analysis(signals, competitor_sentiment)
    issues_analysis = None  # populated from briefing_data.issues_performance if available
    source_coverage = detect_source_coverage(signals)
    version_current, version_previous = get_version_info(signals)

    # Merge findings data if available
    if findings.get("sentiment_scores"):
        print("  Merging findings.sentiment_scores …")
        for comp, score in findings["sentiment_scores"].items():
            if comp in competitor_sentiment:
                competitor_sentiment[comp]["score"] = score
    if findings.get("version_current"):
        version_current = findings["version_current"]
    if findings.get("version_previous"):
        version_previous = findings["version_previous"]

    print(f"  version_current={version_current}  version_previous={version_previous or 'N/A'}")
    active_sources = [k for k, v in source_coverage.items() if v == "active"]
    print(f"  active sources: {active_sources}")

    # ── Briefing data layer (enriched Refuel-8B data) ─────────────────────────
    exec_alert_override_html = ""
    bd_top_quote        = ""
    bd_top_quote_rating = 0
    bd_top_quote_source = ""
    bd_as_quote         = ""
    bd_as_quote_rating  = 0
    bd_as_quote_date    = ""
    bd_gp_quote         = ""
    bd_gp_quote_rating  = 0
    bd_gp_quote_date    = ""
    bd_box2_quote       = ""
    bd_box2_quote_rating = 0
    bd_box2_quote_source = ""
    bd_box2_quote_date  = ""
    bd_box2_issue_type  = ""
    bd_journey_meta     = {}
    if _BRIEFING_DATA_AVAILABLE:
        print("\n[3.5/5] Loading briefing data layer (enriched) …")
        try:
            bd = _get_briefing_data()

            # Override competitor scores from enriched records
            for item in bd.get("competitor_ticker", []):
                comp = item.get("competitor", "")
                score = item.get("score")
                if comp and score is not None:
                    if comp in competitor_sentiment:
                        competitor_sentiment[comp]["score"] = score
                    else:
                        competitor_sentiment[comp] = {
                            "score": score, "p0": 0, "p1": 0, "p2": 0,
                            "count": item.get("n_records", 0),
                            "avg_rating": None, "version": None, "reviews": [],
                        }
            # Pull Barclays trend + baseline from enriched ticker
            for item in bd.get("competitor_ticker", []):
                if item.get("competitor", "").lower() == "barclays":
                    # Match case-insensitively to the existing competitor_sentiment key
                    _bk = next((k for k in competitor_sentiment if k.lower() == "barclays"), None)
                    if _bk is None:
                        _bk = item["competitor"]
                        competitor_sentiment[_bk] = {
                            "score": None, "p0": 0, "p1": 0, "p2": 0,
                            "count": 0, "avg_rating": None, "version": None, "reviews": [],
                        }
                    competitor_sentiment[_bk]["bd_trend"]    = item.get("trend")
                    competitor_sentiment[_bk]["bd_baseline"] = item.get("baseline")
            print(f"  Competitor scores updated from enriched data.")

            # Journey row — what customers were trying to do
            bd_journeys = bd.get("journey_performance", [])
            if bd_journeys:
                journey_analysis = _bd_to_journey_analysis(bd_journeys)

            # Issues cards + metrics strip — what went wrong
            bd_issues = bd.get("issues_performance", [])
            if bd_issues:
                issues_analysis = _bd_to_journey_analysis(bd_issues)
                reg  = sum(1 for j in issues_analysis if j["status"] == "REGRESSION")
                wtch = sum(1 for j in issues_analysis if j["status"] == "WATCH")
                perf = sum(1 for j in issues_analysis if j["status"] == "PERFORMING WELL")
                print(f"  Journey analysis: {len(journey_analysis)} journeys  "
                      f"REGRESSION={reg} WATCH={wtch} PERFORMING={perf}")

            # Build exec_alert override from bd.executive_alert
            now_utc = datetime.now(timezone.utc)
            lr_raw = findings.get("generated_at") or (signals[0].get("timestamp") if signals else None)
            if lr_raw:
                try:
                    lr_dt = datetime.fromisoformat(str(lr_raw).replace("Z", "+00:00"))
                    lr_str = lr_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    lr_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
            else:
                lr_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")

            ea = bd.get("executive_alert", {})
            exec_alert_override_html = build_bd_exec_alert_html(ea, lr_str)
            fid = ea.get("finding_id") or "NOMINAL"
            bd_top_quote        = ea.get("top_quote", "")
            bd_top_quote_rating = ea.get("top_quote_rating", 0)
            bd_top_quote_source = ea.get("top_quote_source", "")
            bd_as_quote         = ea.get("as_quote", "")
            bd_as_quote_rating  = ea.get("as_quote_rating", 0)
            bd_as_quote_date    = ea.get("as_quote_date", "")
            bd_gp_quote         = ea.get("gp_quote", "")
            bd_gp_quote_rating  = ea.get("gp_quote_rating", 0)
            bd_gp_quote_date    = ea.get("gp_quote_date", "")
            bd_box2_quote       = bd.get("box2_quote", "")
            bd_box2_quote_rating = bd.get("box2_quote_rating", 0)
            bd_box2_quote_source = bd.get("box2_quote_source", "")
            bd_box2_quote_date  = bd.get("box2_quote_date", "")
            bd_box2_issue_type  = bd.get("box2_issue_type", "")
            bd_journey_meta     = bd.get("journey_row_meta", {})
            print(f"  Exec alert: {fid}")

        except Exception as exc:
            print(f"  WARN: briefing_data layer failed -- {exc}")
            all_defaults.append(f"briefing_data layer unavailable -- {exc}")
    else:
        print("\n[3.5/5] briefing_data layer not available -- using signal-derived analysis")
        all_defaults.append("briefing_data layer -- import failed, using signal-derived analysis")

    # Track defaults
    if not findings_bound:
        all_defaults.append("mil_findings.json empty — sentiment derived from raw signals")
    if version_previous is None:
        all_defaults.append("version_previous — no baseline, delta shown as '— no baseline'")
    if not signals:
        all_defaults.append("No signals found — page in full baseline state")

    # 5. Generate HTML
    print("\n[4/5] Generating HTML …")
    html_content = generate_html(
        findings=findings,
        signals=signals,
        signals_filename=signals_filename,
        competitor_sentiment=competitor_sentiment,
        journey_analysis=journey_analysis,
        source_coverage=source_coverage,
        version_current=version_current,
        version_previous=version_previous,
        defaults_used=all_defaults,
        exec_alert_override=exec_alert_override_html,
        issues_analysis=issues_analysis,
        top_quote=bd_top_quote,
        top_quote_rating=bd_top_quote_rating,
        top_quote_source=bd_top_quote_source,
        as_quote=bd_as_quote,
        as_quote_rating=bd_as_quote_rating,
        as_quote_date=bd_as_quote_date,
        gp_quote=bd_gp_quote,
        gp_quote_rating=bd_gp_quote_rating,
        gp_quote_date=bd_gp_quote_date,
        box2_quote=bd_box2_quote,
        box2_quote_rating=bd_box2_quote_rating,
        box2_quote_source=bd_box2_quote_source,
        box2_quote_date=bd_box2_quote_date,
        box2_issue_type=bd_box2_issue_type,
        journey_meta=bd_journey_meta,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = OUTPUT_DIR / "index.html"
    local_path.write_text(html_content, encoding="utf-8")
    size_kb = local_path.stat().st_size / 1024
    print(f"  Written: {local_path} ({size_kb:.1f} KB)")
    html_ok = True

    # 6. Publish
    print("\n[5/5] Publishing to GitHub Pages …")
    push_ok, push_msg = publish_to_github_pages(html_content, env)
    if push_ok:
        print(f"  OK: {push_msg}")
    else:
        print(f"  FAIL: {push_msg}")

    # -- Report -------------------------------------------------------------
    print("\n-- Report -------------------------------------------------------")
    print(f"  HTML generated:              {'YES' if html_ok else 'NO'}")
    print(f"  Data bound from findings:    {'YES' if findings_bound else 'NO (bootstrap — signal-derived)'}")
    if all_defaults:
        print(f"  Fields using safe defaults:")
        for d in all_defaults:
            print(f"    - {d}")
    print(f"  GitHub push result:          {'SUCCESS' if push_ok else 'FAIL — ' + push_msg}")
    print(f"  Live URL:                    https://cjipro.com/briefing")
    print(f"  Local copy:                  {local_path}")
    print("----------------------------------------------------------------\n")

    return 0 if (html_ok and push_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
