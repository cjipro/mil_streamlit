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
    """Return CSS color for a 0–100 score."""
    if score is None:
        return "#6b7088"
    if score < 45:
        return "#cc3333"
    if score < 65:
        return "#e8a030"
    return "#2a9a5a"


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
        color = "#e8a030" if is_barclays else score_color(score)
        score_str = f"{score:.1f}" if score is not None else "—"
        bar = score_bar_html(score, width=40)
        items.append(
            f'<span class="ticker-item{" ticker-barclays" if is_barclays else ""}">'
            f'<span class="ticker-name" style="color:{color};">{e(comp)}</span>'
            f'<span class="ticker-score" style="color:{color};">{score_str}</span>'
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


def build_journey_row_html(journey_analysis: list, competitor_sentiment: dict) -> str:
    """Build the 5-journey sentiment summary row."""
    # Reorder by journey ID for display (not by rank)
    by_id = {j["journey_id"]: j for j in journey_analysis}
    cells = []
    for jid in JOURNEY_IDS:
        j = by_id.get(jid, {})
        status = j.get("status", "WATCH")
        score = j.get("score")
        name = JOURNEY_NAMES.get(jid, jid)
        colors = {
            "REGRESSION": "var(--red)",
            "WATCH": "var(--amber)",
            "PERFORMING WELL": "var(--green)",
        }
        border_color = colors.get(status, "var(--amber)")
        score_str = f"{score:.0f}" if score is not None else "—"
        trajectory_icons = {
            "REGRESSION": "↘",
            "WATCH": "→",
            "PERFORMING WELL": "↗",
        }
        traj = trajectory_icons.get(status, "→")
        cells.append(
            f'<div class="journey-cell" style="border-top:3px solid {border_color};">'
            f'<div class="journey-cell-name">{e(name)}</div>'
            f'<div class="journey-cell-score" style="color:{border_color};">{score_str}</div>'
            f'<div class="journey-cell-meta">'
            f'<span class="traj-icon" style="color:{border_color};">{traj}</span>'
            f'<span class="journey-status-label" style="color:{border_color};">{e(status)}</span>'
            f'</div>'
            f'</div>'
        )
    return '<div class="journey-row">' + "".join(cells) + "</div>"


def build_metrics_strip_html(journey_analysis: list, competitor_sentiment: dict) -> str:
    """Build the 4 top-level metric cards."""
    regression_count = sum(1 for j in journey_analysis if j.get("status") == "REGRESSION")
    watch_count = sum(1 for j in journey_analysis if j.get("status") == "WATCH")
    performing_count = sum(1 for j in journey_analysis if j.get("status") == "PERFORMING WELL")
    barclays_score = competitor_sentiment.get("Barclays", {}).get("score")
    barclays_str = f"{barclays_score:.1f}" if barclays_score is not None else "—"

    def metric_card(label, value, color, sublabel=""):
        return (
            f'<div class="metric-card">'
            f'<div class="metric-value" style="color:{color};">{e(str(value))}</div>'
            f'<div class="metric-label">{e(label)}</div>'
            f'{"<div class=\"metric-sub\">" + e(sublabel) + "</div>" if sublabel else ""}'
            f'</div>'
        )

    cards = [
        metric_card("Needs Attention", regression_count, "var(--red)", "REGRESSION journeys"),
        metric_card("Watch", watch_count, "var(--amber)", "WATCH journeys"),
        metric_card("Performing Well", performing_count, "var(--green)", "across all sources"),
        metric_card("Barclays Sentiment", barclays_str, "var(--amber)", "brand competitor"),
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

    ticker_html = build_ticker_html(competitor_sentiment)
    journey_row_html = build_journey_row_html(journey_analysis, competitor_sentiment)
    metrics_strip_html = build_metrics_strip_html(journey_analysis, competitor_sentiment)
    inference_card_html = build_inference_card_html(findings)
    chronicle_html = build_chronicle_html()
    sources_grid_html = build_sources_grid_html(source_coverage)

    journey_cards_html = ""
    for j in journey_analysis:
        journey_cards_html += build_journey_card_html(j)

    defaults_note = ""
    if defaults_used:
        items_html = "".join(f"<li>{e(d)}</li>" for d in defaults_used)
        defaults_note = f'<div class="defaults-banner"><strong>Safe defaults applied:</strong><ul>{items_html}</ul></div>'

    published_at = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sonar — App Intelligence Briefing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* -- Reset & Base ----------------------------------------------------------- */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:        #12131a;
  --card:      #161820;
  --border:    #1e2030;
  --amber:     #e8a030;
  --red:       #cc3333;
  --green:     #2a9a5a;
  --text:      #e8e4d8;
  --dim:       #6b7088;
  --mono:      'DM Mono', monospace;
  --sans:      'DM Sans', sans-serif;
}}

html, body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
}}

a {{ color: var(--amber); text-decoration: none; }}

/* -- Topbar ----------------------------------------------------------------- */
.topbar {{
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: #0e0f15;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}}
.topbar-logo {{
  font-weight: 700;
  font-size: 15px;
  letter-spacing: 0.08em;
  color: var(--amber);
}}
.topbar-sep {{ color: var(--border); font-size: 18px; }}
.topbar-meta {{ font-size: 12px; color: var(--dim); font-family: var(--mono); }}
.live-dot {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--green);
  font-weight: 600;
  letter-spacing: 0.05em;
}}
.live-dot::before {{
  content: '';
  width: 7px;
  height: 7px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}}
@keyframes pulse {{
  0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(42,154,90,0.4); }}
  50% {{ opacity: 0.7; box-shadow: 0 0 0 5px rgba(42,154,90,0); }}
}}
.topbar-right {{ margin-left: auto; display: flex; align-items: center; gap: 12px; }}
.bootstrap-badge {{
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #1a1500;
  color: var(--amber);
  border: 1px solid var(--amber);
  font-family: var(--mono);
  letter-spacing: 0.05em;
}}

/* -- Ticker ----------------------------------------------------------------- */
.ticker-wrapper {{
  overflow: hidden;
  background: #0e0f15;
  border-bottom: 1px solid var(--border);
  padding: 8px 0;
}}
.ticker-track {{
  overflow: hidden;
  white-space: nowrap;
}}
.ticker-inner {{
  display: inline-flex;
  align-items: center;
  animation: ticker-scroll 30s linear infinite;
}}
.ticker-inner:hover {{
  animation-play-state: paused;
}}
@keyframes ticker-scroll {{
  0%   {{ transform: translateX(0); }}
  100% {{ transform: translateX(-50%); }}
}}
.ticker-item {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 20px;
  font-size: 12px;
}}
.ticker-barclays {{ background: rgba(232,160,48,0.06); border-radius: 4px; }}
.ticker-name {{ font-weight: 600; letter-spacing: 0.02em; }}
.ticker-score {{ font-family: var(--mono); font-size: 13px; font-weight: 500; }}
.ticker-delta {{ font-size: 11px; }}
.ticker-sep {{ color: var(--border); padding: 0 4px; }}

/* -- Mini Bar --------------------------------------------------------------- */
.mini-bar {{
  display: inline-flex;
  align-items: center;
  width: 60px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}}
.mini-bar-fill {{
  height: 4px;
  border-radius: 2px;
  transition: width 0.3s ease;
}}

/* -- Journey Row ------------------------------------------------------------ */
.journey-row {{
  display: flex;
  gap: 1px;
  background: var(--border);
  border-bottom: 1px solid var(--border);
}}
.journey-cell {{
  flex: 1;
  padding: 12px 16px;
  background: var(--card);
  cursor: default;
  transition: background 0.15s;
}}
.journey-cell:hover {{ background: #1a1c28; }}
.journey-cell-name {{ font-size: 11px; color: var(--dim); font-weight: 500; margin-bottom: 4px; }}
.journey-cell-score {{ font-size: 22px; font-weight: 700; font-family: var(--mono); margin-bottom: 4px; }}
.journey-cell-meta {{ display: flex; align-items: center; gap: 6px; }}
.traj-icon {{ font-size: 14px; }}
.journey-status-label {{ font-size: 10px; font-weight: 600; letter-spacing: 0.06em; }}

/* -- Metrics Strip ---------------------------------------------------------- */
.metrics-strip {{
  display: flex;
  gap: 1px;
  background: var(--border);
  border-bottom: 1px solid var(--border);
}}
.metric-card {{
  flex: 1;
  padding: 16px 20px;
  background: var(--card);
}}
.metric-value {{ font-size: 32px; font-weight: 700; font-family: var(--mono); line-height: 1; margin-bottom: 4px; }}
.metric-label {{ font-size: 12px; font-weight: 600; letter-spacing: 0.04em; color: var(--text); }}
.metric-sub {{ font-size: 11px; color: var(--dim); margin-top: 2px; }}

/* -- Body Layout ------------------------------------------------------------ */
.body-wrapper {{
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 1px;
  background: var(--border);
  min-height: calc(100vh - 200px);
}}
.left-col {{ background: var(--bg); padding: 20px; display: flex; flex-direction: column; gap: 16px; }}
.right-col {{ background: var(--bg); padding: 20px; display: flex; flex-direction: column; gap: 16px; }}

/* -- Journey Cards ---------------------------------------------------------- */
.journey-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.card-header {{
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}}
.rank-num {{
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--dim);
  min-width: 24px;
}}
.journey-name {{
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  flex: 1;
}}
.badge {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: 3px;
}}
.derived-note {{
  font-size: 10px;
  font-family: var(--mono);
  color: var(--amber);
  background: rgba(232,160,48,0.08);
  padding: 3px 8px;
  border-radius: 3px;
  letter-spacing: 0.03em;
}}
.verdict-label {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--dim);
}}
.verdict-text {{
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}}
.verdict-baseline {{
  color: var(--dim);
  font-weight: 400;
  font-style: italic;
}}
.version-delta-row {{
  display: flex;
  align-items: center;
  gap: 12px;
}}
.version-label {{
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
  background: #0d0e14;
  padding: 2px 6px;
  border-radius: 3px;
}}
.version-delta {{
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 500;
  background: #0d0e14;
  padding: 2px 8px;
  border-radius: 3px;
}}
.signal-counts {{
  display: flex;
  gap: 8px;
}}
.sig-count {{
  font-family: var(--mono);
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
}}
.sig-p1 {{ background: rgba(204,51,51,0.15); color: #ff6666; }}
.sig-p2 {{ background: rgba(232,160,48,0.12); color: var(--amber); }}
.voice-label {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--dim);
}}
.pills {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.pill {{
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 500;
}}
.pill-neg {{ background: rgba(204,51,51,0.15); color: #ff6666; border: 1px solid rgba(204,51,51,0.2); }}
.pill-pos {{ background: rgba(42,154,90,0.15); color: #4ad88a; border: 1px solid rgba(42,154,90,0.2); }}
.market-note {{ font-size: 11px; color: var(--dim); font-style: italic; }}

/* -- Right Panel ------------------------------------------------------------ */
.panel-section {{ display: flex; flex-direction: column; gap: 10px; }}
.panel-title {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--dim);
  text-transform: uppercase;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}}

/* -- Inference Card --------------------------------------------------------- */
.inference-card {{
  background: #12140a;
  border: 1px solid var(--amber);
  border-radius: 6px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.inference-header {{ display: flex; align-items: center; gap: 8px; }}
.inference-label {{ font-size: 10px; font-weight: 700; letter-spacing: 0.08em; color: var(--amber); }}
.severity-badge {{
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
}}
.severity-p0 {{ background: rgba(204,51,51,0.3); color: #ff4444; }}
.severity-p1 {{ background: rgba(204,51,51,0.15); color: #ff6666; }}
.inference-finding {{ font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.4; }}
.blind-spots {{ list-style: none; padding-left: 0; display: flex; flex-direction: column; gap: 4px; }}
.blind-spot-item {{ font-size: 11px; color: var(--dim); padding-left: 12px; position: relative; }}
.blind-spot-item::before {{ content: '⚠'; position: absolute; left: 0; font-size: 9px; color: var(--amber); }}
.chronicle-anchor {{ font-family: var(--mono); font-size: 11px; color: var(--amber); }}
.inference-actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.action-btn {{
  background: #1a1500;
  color: var(--amber);
  border: 1px solid var(--amber);
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}}
.action-btn:hover {{ background: rgba(232,160,48,0.15); }}

/* -- Chronicle -------------------------------------------------------------- */
.chronicle-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}}
.chronicle-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.chronicle-id {{ font-family: var(--mono); font-size: 11px; font-weight: 700; color: var(--amber); }}
.chronicle-bank {{ font-size: 12px; font-weight: 600; color: var(--text); flex: 1; }}
.chronicle-date {{ font-size: 10px; color: var(--dim); font-family: var(--mono); }}
.chronicle-active {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  background: rgba(204,51,51,0.2);
  color: #ff6666;
  padding: 1px 5px;
  border-radius: 3px;
}}
.chronicle-hold {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.05em;
  background: rgba(107,112,136,0.2);
  color: var(--dim);
  padding: 1px 5px;
  border-radius: 3px;
}}
.chronicle-cap {{
  font-size: 9px;
  color: var(--amber);
  background: rgba(232,160,48,0.1);
  padding: 1px 5px;
  border-radius: 3px;
}}
.chronicle-type {{ font-size: 11px; color: var(--text); font-weight: 500; }}
.chronicle-impact {{ font-size: 11px; color: var(--amber); font-weight: 600; font-family: var(--mono); }}

/* -- Sources Grid ----------------------------------------------------------- */
.sources-grid {{ display: flex; flex-direction: column; gap: 6px; }}
.source-item {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
}}
.source-item:last-child {{ border-bottom: none; }}
.dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.dot-green {{ background: var(--green); box-shadow: 0 0 4px rgba(42,154,90,0.6); }}
.dot-amber {{ background: var(--amber); box-shadow: 0 0 4px rgba(232,160,48,0.5); }}
.dot-grey {{ background: #3a3d52; }}
.source-name {{ font-size: 12px; color: var(--text); flex: 1; }}
.source-weight {{ font-family: var(--mono); font-size: 11px; color: var(--dim); }}

/* -- Delta ------------------------------------------------------------------ */
.delta {{ font-family: var(--mono); font-size: 11px; font-weight: 600; }}
.delta-na {{ font-family: var(--mono); font-size: 11px; color: var(--dim); }}

/* -- Defaults Banner -------------------------------------------------------- */
.defaults-banner {{
  margin: 12px 24px;
  padding: 10px 16px;
  background: rgba(232,160,48,0.08);
  border: 1px solid rgba(232,160,48,0.2);
  border-radius: 5px;
  font-size: 11px;
  color: var(--amber);
}}
.defaults-banner ul {{ padding-left: 16px; margin-top: 4px; }}
.defaults-banner li {{ margin-top: 2px; }}

/* -- Footer ----------------------------------------------------------------- */
.footer {{
  background: #0e0f15;
  border-top: 1px solid var(--border);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}}
.footer-item {{ font-size: 11px; color: var(--dim); font-family: var(--mono); }}
.footer-sep {{ color: var(--border); }}
.footer-sovereign {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--amber);
  background: rgba(232,160,48,0.08);
  padding: 2px 8px;
  border-radius: 3px;
}}

/* -- Ask Sonar Button ------------------------------------------------------- */
.ask-sonar-btn {{
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--amber);
  color: #12131a;
  border: none;
  border-radius: 28px;
  padding: 12px 22px;
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  z-index: 1000;
  box-shadow: 0 4px 20px rgba(232,160,48,0.4);
  transition: transform 0.15s, box-shadow 0.15s;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.ask-sonar-btn:hover {{
  transform: translateY(-2px);
  box-shadow: 0 6px 28px rgba(232,160,48,0.55);
}}
.ask-sonar-btn svg {{ width: 16px; height: 16px; }}

/* -- Chat Panel ------------------------------------------------------------- */
.chat-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 999;
}}
.chat-panel {{
  position: fixed;
  bottom: 80px;
  right: 24px;
  width: 360px;
  max-height: 500px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  display: none;
  flex-direction: column;
  z-index: 1001;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
  overflow: hidden;
}}
.chat-panel.open {{ display: flex; }}
.chat-header {{
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}}
.chat-title {{ font-size: 13px; font-weight: 700; color: var(--text); flex: 1; }}
.chat-close {{
  background: none;
  border: none;
  color: var(--dim);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  padding: 0 4px;
}}
.chat-close:hover {{ color: var(--text); }}
.chat-messages {{
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 160px;
}}
.chat-chips {{
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid var(--border);
}}
.chip {{
  background: #1a1c28;
  color: var(--amber);
  border: 1px solid rgba(232,160,48,0.25);
  border-radius: 14px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s;
}}
.chip:hover {{ background: rgba(232,160,48,0.12); }}
.chat-input-row {{
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 8px;
}}
.chat-input {{
  flex: 1;
  background: #0e0f15;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--text);
  outline: none;
}}
.chat-input:focus {{ border-color: var(--amber); }}
.chat-send {{
  background: var(--amber);
  color: #12131a;
  border: none;
  border-radius: 6px;
  padding: 8px 14px;
  font-weight: 700;
  font-size: 12px;
  cursor: pointer;
}}
.chat-msg {{
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 10px;
  border-radius: 6px;
}}
.chat-msg.system {{ background: #1a1c28; color: var(--text); }}
.chat-msg.user {{ background: rgba(232,160,48,0.1); color: var(--amber); align-self: flex-end; }}
.chat-msg.error {{ background: rgba(204,51,51,0.1); color: #ff6666; }}

/* -- Responsive ------------------------------------------------------------- */
@media (max-width: 900px) {{
  .body-wrapper {{ grid-template-columns: 1fr; }}
  .metrics-strip {{ flex-wrap: wrap; }}
  .metric-card {{ min-width: 45%; }}
  .journey-row {{ flex-wrap: wrap; }}
  .journey-cell {{ min-width: 45%; }}
}}
</style>
</head>
<body>

<!-- -- Topbar -------------------------------------------------------------- -->
<div class="topbar">
  <div class="topbar-logo">SONAR / APP INTELLIGENCE</div>
  <span class="topbar-sep">|</span>
  <div class="topbar-meta">v{e(version_display)}</div>
  <span class="topbar-sep">|</span>
  <div class="topbar-meta">{e(last_run_str)}</div>
  <div class="topbar-right">
    {"<span class='bootstrap-badge'>BASELINE ESTABLISHING</span>" if is_bootstrap else ""}
    <div class="live-dot">LIVE</div>
  </div>
</div>

<!-- -- Sentiment Ticker ---------------------------------------------------- -->
<div class="ticker-wrapper">
  {ticker_html}
</div>

<!-- -- Journey Sentiment Row ----------------------------------------------- -->
{journey_row_html}

<!-- -- Metrics Strip ------------------------------------------------------- -->
{metrics_strip_html}

{defaults_note}

<!-- -- Body ---------------------------------------------------------------- -->
<div class="body-wrapper">

  <!-- Left: Journey Stack -->
  <div class="left-col">
    {journey_cards_html}
  </div>

  <!-- Right: Side Panel -->
  <div class="right-col">
    {inference_card_html}
    {chronicle_html}
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
<button class="ask-sonar-btn" onclick="openChat()" aria-label="Ask Sonar">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
  Ask Sonar
</button>

<!-- -- Chat Panel ----------------------------------------------------------- -->
<div class="chat-panel" id="chatPanel">
  <div class="chat-header">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#e8a030" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
    <span class="chat-title">Ask Sonar</span>
    <button class="chat-close" onclick="closeChat()">&#215;</button>
  </div>
  <div class="chat-messages" id="chatMessages">
    <div class="chat-msg system">Sonar is ready. Ask about any competitor journey, signal pattern, or CHRONICLE match.</div>
  </div>
  <div class="chat-chips">
    <span class="chip" onclick="sendChip(this)">What is Barclays login score?</span>
    <span class="chip" onclick="sendChip(this)">Any active P0 signals?</span>
    <span class="chip" onclick="sendChip(this)">CHRONICLE match for Lloyds?</span>
    <span class="chip" onclick="sendChip(this)">Which journey is regressing?</span>
  </div>
  <div class="chat-input-row">
    <input type="text" class="chat-input" id="chatInput" placeholder="Ask about market signals…" onkeydown="if(event.key==='Enter')sendChat()">
    <button class="chat-send" onclick="sendChat()">Send</button>
  </div>
</div>

<script>
// -- Chat Panel ------------------------------------------------------------
const PROXY_URL = 'https://sonar.cjipro.com/api/ask';

function openChat() {{
  document.getElementById('chatPanel').classList.add('open');
}}
function closeChat() {{
  document.getElementById('chatPanel').classList.remove('open');
}}
function sendChip(el) {{
  document.getElementById('chatInput').value = el.textContent;
  sendChat();
}}
async function sendChat() {{
  const input = document.getElementById('chatInput');
  const messages = document.getElementById('chatMessages');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';

  // User message
  const userMsg = document.createElement('div');
  userMsg.className = 'chat-msg user';
  userMsg.textContent = text;
  messages.appendChild(userMsg);
  messages.scrollTop = messages.scrollHeight;

  // Send to proxy
  try {{
    const res = await fetch(PROXY_URL, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{query: text, version: '{e(version_display)}'}})
    }});
    const data = await res.json();
    const reply = document.createElement('div');
    reply.className = 'chat-msg system';
    reply.textContent = data.response || 'No response from Sonar.';
    messages.appendChild(reply);
  }} catch (err) {{
    const errMsg = document.createElement('div');
    errMsg.className = 'chat-msg error';
    errMsg.textContent = 'Proxy unavailable — sonar.cjipro.com/api/ask not reachable.';
    messages.appendChild(errMsg);
  }}
  messages.scrollTop = messages.scrollHeight;
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
