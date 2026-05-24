"""Pulse Home (HOL-4) — first-30-seconds entry feed for all roles.

Per HOL-4 spec: news-portal aesthetic, 3-7 heterogeneous cards, NO KPI
tiles, NO trend charts, NO personalisation, NO sidebar navigation. The
job of this surface is "what changed since I last looked" — cards link
out to the Workspace (HOL-3, :8504) for investigation.

Card categories (per HOL-4 spec):
  (a) FLAGGED — signals with recommended investigation templates
  (b) AWAITING REVIEW — completed investigations needing sign-off
  (c) MLOPS — model-ops alerts (drift, calibration, etc.)

Data sources:
  - FLAGGED cards: discover_packs() + get_pack_cell() filtered to
    ACUTE / REGULATORY-FLAG / COMMERCIAL-OPPORTUNITY action tiers
  - AWAITING REVIEW: stubbed (no review-state contract in engine yet)
  - MLOPS: stubbed (Surface 4 not yet built)

Output: dist/preview/home/index.html
Serve:  py holter/preview/serve_home.py  (port 8505)
"""

from __future__ import annotations

import datetime as _dt
import sys
from html import escape as _e
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "dist" / "preview" / "home"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# HOL-35: import shared primitives from _shared (not from render_holter).
# Per Cannon's PR-panel ruling, no renderer should depend on another
# renderer for helpers — _shared is the single source of truth so a
# broken render_holter doesn't cascade to Pulse Home.
from holter.preview._shared import (  # noqa: E402
    discover_packs,
    get_pack_cell,
    get_pack_analytics,
    lineage_anchor_short,
    headline_pack,
    short_hash,
    _ACTION_COLORS,
    _DIAGNOSIS_COLORS,
    _VALUE_COLORS,
    _RISK_COLORS,
    STATUS_GLOSSARY,
    tooltip_token,
    render_glossary_panel,
    friction_volume_value,
    commercial_scaffold,
    signal_provenance,
    _format_count,
)


def _live_friction_index() -> dict[tuple[str, str], int]:
    """HOL-66 / PULSE-127 — live detected friction-session counts keyed by
    (screen_id, signature). Fails soft: returns {} if the marts / DuckDB are
    unavailable, so the feed always renders (cards fall back to the engine
    ValueScore projection). Article Zero: degrade visibly, never crash."""
    try:
        from pulse.serving import read as _read
        return {
            (r["screen_id"], r["signature"]): int(r["friction_sessions"])
            for r in _read.friction_by_journey()
        }
    except Exception:
        import logging
        logging.exception(
            "live friction index unavailable; cards fall back to engine projection"
        )
        return {}


def _volume_and_scaffold(pack: dict, cs, live_index: dict[tuple[str, str], int]):
    """Option 1 (HOL-66): the verdict stays engine-of-record, but the
    friction-VOLUME number goes live. If PULSE-127 has a detected count for this
    card's (screen, signature), use it (marked `live`); else fall back to the
    engine's ValueScore projection."""
    screen = (pack.get("hypothesis") or {}).get("screen_id")
    live_n = live_index.get((screen, cs.signature_id)) if screen else None
    if live_n is not None:
        return f"~{_format_count(live_n)}", "live · PULSE-127"
    return friction_volume_value(cs.value, period="week"), commercial_scaffold(cs.value)

# PR-panel fix (Hettinger): the tier_color lookup in render_feed_card was
# always using _ACTION_COLORS regardless of tier_dim — silent wrong-color
# bug for non-action dimensions (NOMINAL means different things in
# Action/Value/Risk, and so does the colour). Route by dimension explicitly.
_DIM_COLOR_MAPS: dict[str, dict[str, str]] = {
    "action":    _ACTION_COLORS,
    "diagnosis": _DIAGNOSIS_COLORS,
    "value":     _VALUE_COLORS,
    "risk":      _RISK_COLORS,
}

NOW = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ─────────────────────────────────────────────────────────────────────────────
# Data shaping — pulls flagged signals from the pack registry
# ─────────────────────────────────────────────────────────────────────────────

_TIER_RANK = {
    "ACUTE":                    0,
    "REGULATORY-FLAG":          1,
    "COMMERCIAL-OPPORTUNITY":   2,
    "WATCH":                    3,
    "NOMINAL":                  4,
    "NEEDS_MORE_DATA":          5,
}

# HOL-55 — dual-queue split: which tiers belong to each lens. Compliance
# answers the CRO question; Commercial answers the CCO/COO question. Same
# corpus, two queues, no severity bias against commercial-tier packs
# (which was the audit-flagged structural failure mode).
_COMPLIANCE_TIERS = {"ACUTE", "REGULATORY-FLAG"}
_COMMERCIAL_VALUE_TIERS = {"COMMERCIAL-OPPORTUNITY", "SIGNIFICANT"}

# Value-tier rank — used to sort the commercial queue. Higher tier first,
# then sized monthly lift desc. Distinct from _TIER_RANK above which sorts
# Action tier (a Risk × Value composite).
_VALUE_TIER_RANK = {
    "COMMERCIAL-OPPORTUNITY": 0,
    "SIGNIFICANT":            1,
    "WATCH":                  2,
    "NOMINAL":                3,
}


def collect_flagged_signals(packs: list[dict]) -> list[dict]:
    """All packs sorted by Action tier severity, highest-first.

    HOL-55: this is the COMPLIANCE queue's input. Commercial queue is sorted
    by Value tier + sized lift via `collect_commercial_signals` below."""
    out = []
    for p in packs:
        cs = get_pack_cell(p["meta"]["pack_name"])
        if cs is None:
            continue
        out.append({
            "pack": p,
            "cell_score": cs,
            "tier": cs.action_tier,
            "rank": _TIER_RANK.get(cs.action_tier, 99),
            "journey": cs.journey_id,
        })
    out.sort(key=lambda r: r["rank"])
    return out


def collect_commercial_signals(packs: list[dict]) -> list[dict]:
    """HOL-55 — Commercial queue input. Packs sorted by Value tier first,
    then by sized monthly lift (descending). Packs without a sized lift
    (no ARPU for the journey) sort at the end of their tier band.

    Distinct from `collect_flagged_signals`: this lens IGNORES action_tier
    (which folds Risk into the ranking — that's the CRO question) and ranks
    purely by Value-axis output (the CCO question). The two queues may
    overlap on ACUTE packs (high value × high risk — these show up in
    both lenses; that's the load-bearing case)."""
    out = []
    for p in packs:
        cs = get_pack_cell(p["meta"]["pack_name"])
        if cs is None:
            continue
        value_tier = cs.value.tier
        if value_tier not in _COMMERCIAL_VALUE_TIERS:
            continue
        sessions_wk = getattr(cs.value, "recoverable_sessions_per_week", 0) or 0
        out.append({
            "pack": p,
            "cell_score": cs,
            "tier": cs.action_tier,             # for badge consistency
            "value_tier": value_tier,
            "sessions_per_week": sessions_wk,
            "rank": _VALUE_TIER_RANK.get(value_tier, 99),
            "journey": cs.journey_id,
        })
    # Sort: value-tier rank ascending (COMMERCIAL-OPPORTUNITY first), then
    # friction volume descending — sessions/wk recoverable, NOT £ (no-pound-
    # pandora: £ never drives the ranking; the friction is the signal).
    out.sort(key=lambda r: (r["rank"], -(r["sessions_per_week"] or 0)))
    return out


def select_flagged_grid(flagged: list[dict], hero: dict, n: int = 3) -> list[dict]:
    """Pick N grid cards that diversify across BOTH journey AND signature class.

    HOL-25 introduced journey diversity. HOL-29 extends to signature diversity
    so the per-(signature × diagnosis) summary templates actually vary across
    the visible cards (Boykis: "all 3 FLAGGED cards happen to be the same
    (signature × diagnosis) combo, so the variation doesn't fire here").

    Selection passes:
      1. Skip hero pack; skip hero journey; pick ≤1 card per signature, ≤1 per
         journey — forces signature diversity at the cost of skipping some
         high-severity packs that would otherwise stack 3-in-a-row of one signature
      2. Fill with journey-diverse cards (allow signature repeats)
      3. Fill with anything left
    """
    hero_pack_name = hero["pack"]["meta"]["pack_name"]
    hero_journey = hero["journey"]
    hero_signature = hero["cell_score"].signature_id
    seen_journeys: set[str] = set()
    # Track picked packs by name (set lookup is O(1); previous identity-check
    # `if sig in out` was O(n²) and fragile if any upstream copies the dict)
    picked_pack_names: set[str] = {hero_pack_name}
    # Cap each signature at 1 occurrence including hero's so the grid
    # diversifies AWAY from whatever the hero is.
    sig_count: dict[str, int] = {hero_signature: 1}
    out: list[dict] = []

    # Pass 1: breadth-first by journey AND cap each signature at 1
    for sig in flagged:
        if sig["pack"]["meta"]["pack_name"] in picked_pack_names:
            continue
        if sig["journey"] == hero_journey:
            continue
        if sig["journey"] in seen_journeys:
            continue
        sigid = sig["cell_score"].signature_id
        if sig_count.get(sigid, 0) >= 1:
            continue
        seen_journeys.add(sig["journey"])
        sig_count[sigid] = sig_count.get(sigid, 0) + 1
        picked_pack_names.add(sig["pack"]["meta"]["pack_name"])
        out.append(sig)
        if len(out) >= n:
            return out

    # Pass 2: breadth-first by journey (allow signature repeats)
    for sig in flagged:
        if sig["pack"]["meta"]["pack_name"] in picked_pack_names:
            continue
        if sig["journey"] in seen_journeys:
            continue
        seen_journeys.add(sig["journey"])
        picked_pack_names.add(sig["pack"]["meta"]["pack_name"])
        out.append(sig)
        if len(out) >= n:
            return out

    # Pass 3: fill remaining slots with any unseen card
    for sig in flagged:
        if sig["pack"]["meta"]["pack_name"] in picked_pack_names:
            continue
        picked_pack_names.add(sig["pack"]["meta"]["pack_name"])
        out.append(sig)
        if len(out) >= n:
            return out

    return out


# HOL-25 — de-templated card summaries. Keyed by (signature, diagnosis); each
# combo carries 1-2 distinct sentence patterns so cards on the same journey
# read as distinct stories.
_CARD_SUMMARY_TEMPLATES: dict[tuple[str, str], list[str]] = {
    ("abandon_before_submit", "BOTH"): [
        "High-intent sessions reach the form's last field then leave — both the "
        "journey design and the in-flow support layer need attention.",
        "Late-stage abandonment driven by both the form itself and the absence "
        "of contextual help. Two-front fix.",
    ],
    ("abandon_before_submit", "JOURNEY_PROBLEM"): [
        "Sessions reach the form's last field then leave. Fix the journey design — "
        "assistance doesn't recover this kind of abandonment.",
    ],
    ("abandon_before_submit", "SUPPORT_PROBLEM"): [
        "Sessions abandon at the submission step but accept assistance when offered. "
        "Strengthen the in-flow support layer; the journey itself is sound.",
    ],
    ("abandon_before_submit", "INCONCLUSIVE"): [
        "Abandonment signal fires at the submission step. Engine can't yet separate "
        "journey-design causes from support-gap causes — collect more control sessions.",
    ],
    ("dwell_after_error", "BOTH"): [
        "Sessions stall after a validation error — both the error message itself "
        "and the inline help around it need work.",
        "Post-error dwell exceeds baseline on both the message wording and the "
        "absence of in-context recovery affordance.",
    ],
    ("dwell_after_error", "JOURNEY_PROBLEM"): [
        "Sessions stall after a validation error. The error message itself is the "
        "friction — fix the journey, not the support around it.",
    ],
    ("dwell_after_error", "SUPPORT_PROBLEM"): [
        "Sessions stall after a validation error but recover when assisted. "
        "Deploy in-context support at the moment the error fires.",
    ],
    ("dwell_after_error", "INCONCLUSIVE"): [
        "Post-error dwell detected. Engine can't yet attribute the friction to "
        "journey or support — collect more data before deciding.",
    ],
    ("multi_back_press", "BOTH"): [
        "Sessions backtrack repeatedly within a single screen — both the form "
        "flow and the help context need rework.",
    ],
    ("multi_back_press", "JOURNEY_PROBLEM"): [
        "Repeated back-presses signal users searching for fields they already left. "
        "The journey order is the friction — assistance doesn't fix navigation.",
    ],
    ("multi_back_press", "SUPPORT_PROBLEM"): [
        "Sessions show repeated back-navigation; assistance reduces it. "
        "Surface contextual help at the screens with highest re-entry.",
    ],
    ("multi_back_press", "INCONCLUSIVE"): [
        "Multi-back-press signal fires. Engine can't tell if this is journey "
        "navigation or unclear support — need more sessions.",
    ],
}


def summary_for(signature: str, diagnosis: str, pack_name: str) -> str:
    """HOL-25 — varied per-card prose. Falls back to engine recommendation."""
    templates = _CARD_SUMMARY_TEMPLATES.get((signature, diagnosis), [])
    if not templates:
        return ""  # caller falls back to placement_recommendation
    # Deterministic selection by pack-name hash so a given pack always shows the
    # same template (stable across reloads), but varies across the registry.
    idx = sum(ord(c) for c in pack_name) % len(templates)
    return templates[idx]


# ─────────────────────────────────────────────────────────────────────────────
# HOL-24 — per-card delta layer (stubs; engine returns these later)
# ─────────────────────────────────────────────────────────────────────────────

_DELTA_TIMES = ["2h ago", "6h ago", "yesterday", "3 days ago", "last week"]
_DELTA_CHANGES = [
    ("→ new",                          "var(--blue)"),
    ("↑ escalated from WATCH",         "var(--amber)"),
    ("↑ escalated from REGULATORY-FLAG", "var(--red)"),
    ("↑ escalated from COMMERCIAL-OPP", "var(--amber)"),
    ("→ existing",                     "var(--text-3)"),
    ("↓ de-escalated from ACUTE",      "var(--green)"),
]
_DELTA_CONFIDENCE = [
    ("HIGH",   "0.91", "var(--green)"),
    ("HIGH",   "0.88", "var(--green)"),
    ("MEDIUM", "0.74", "var(--amber)"),
    ("MEDIUM", "0.69", "var(--amber)"),
    ("LOW",    "0.62", "var(--red)"),
    ("LOW",    "0.55", "var(--red)"),
]


_CONF_BAND_COLORS = {"high": "var(--green)", "medium": "var(--amber)", "low": "var(--red)"}


def _real_confidence(pack_name: str) -> tuple[str, str, str] | None:
    """PULSE-93/96 — real confidence (band label, percentile-interval string,
    colour) from the synthesis analytics, or None when the pack isn't runnable.
    The interval is the honest signal: a single fabricated point score is what
    we're replacing."""
    out = get_pack_analytics(pack_name)
    if out is None:
        return None
    p = out.payload
    band = p["confidence_band"]  # high / medium / low
    interval = f"{p['confidence_low']:.2f}–{p['confidence_high']:.2f}"
    return band.upper(), interval, _CONF_BAND_COLORS.get(band, "var(--amber)")


def _lineage_meta(pack: dict) -> str:
    """Card meta line lineage badge — the REAL lineage anchor when available,
    metadata-file sha as the honest fallback for fixture/non-runnable packs."""
    la = lineage_anchor_short(pack["meta"]["pack_name"])
    return f"lineage:{la}" if la else f"sha:{short_hash(pack['sha256'])}"


def card_delta(pack_name: str) -> dict:
    """Per-card delta values. time / change / velocity / n_findings stay
    deterministic stubs (no feed-state contract in the engine yet), but the
    CONFIDENCE is now the REAL synthesis-analytics band + interval for runnable
    packs (PULSE-93/96), falling back to the stub for non-runnable packs."""
    h = sum(ord(c) for c in pack_name)
    time_str = _DELTA_TIMES[h % len(_DELTA_TIMES)]
    change_str, change_color = _DELTA_CHANGES[(h // 3) % len(_DELTA_CHANGES)]
    conf_label, conf_score, conf_color = _DELTA_CONFIDENCE[(h // 7) % len(_DELTA_CONFIDENCE)]
    real_conf = _real_confidence(pack_name)
    if real_conf is not None:
        conf_label, conf_score, conf_color = real_conf
    n_findings = 1 + (h % 7)
    # HOL-27 — categorical velocity tag (Klein's "structure fire vs vehicle
    # fire" framing wants categorical, not continuous). Derived from
    # time-since-surfaced + tier-change direction.
    velocity = _classify_velocity(time_str, change_str)
    return {
        "time": time_str,
        "change": change_str,
        "change_color": change_color,
        "conf_label": conf_label,
        "conf_score": conf_score,
        "conf_color": conf_color,
        "n_findings": n_findings,
        "velocity": velocity,  # {label, color, icon}
    }


def _classify_velocity(time_str: str, change_str: str) -> dict:
    """HOL-27 — pick one of 4 categorical velocity tags from time + change."""
    # Falling tier overrides time — engine has confirmed de-escalation
    if change_str.startswith("↓"):
        return {"icon": "▽", "label": "COOLING",  "color": "var(--green)"}
    # Fresh + escalating (or fresh + new) = the "structure fire" case
    if time_str in {"2h ago", "6h ago"}:
        return {"icon": "▲", "label": "JUST HOT", "color": "var(--blue)"}
    # Mid-range = steady-state observation window
    if time_str == "yesterday":
        return {"icon": "▬", "label": "STEADY",   "color": "var(--text-3)"}
    # Long-lived same-tier = plateau, the "been hot for days" case
    return {"icon": "═", "label": "PLATEAU",  "color": "var(--amber)"}


def render_velocity_tag(delta: dict) -> str:
    """Small mono badge — categorical tempo signal (HOL-27, Klein)."""
    v = delta.get("velocity")
    if not v:
        return ""
    return (
        f'<span class="velocity-tag" '
        f'style="color:{v["color"]};border-color:{v["color"]};" '
        f'data-tooltip="Tempo of this signal — distinguishes &quot;just went hot&quot; from &quot;been hot for days&quot;.">'
        f'{v["icon"]} {v["label"]}'
        f'</span>'
    )


def render_confidence_chip(delta: dict) -> str:
    """Small chip next to the tier badge — engine confidence in the verdict.

    HOL-55 — prefix with "CONF" so the dimension is visible without hover.
    Audit-flagged ambiguity: numeric chip on its own ("MEDIUM 8.10") read
    as severity/value/risk to non-specialist viewers."""
    return (
        f'<span class="confidence-chip" '
        f'style="color:{delta["conf_color"]};border-color:{delta["conf_color"]};" '
        f'data-tooltip="Engine confidence in this verdict — drivers visible in Workspace (HOL-19).">'
        f'CONF {delta["conf_label"]} {delta["conf_score"]}'
        f'</span>'
    )


def render_delta_strip(delta: dict, preview_text: str = "",
                       suppress_change: bool = False) -> str:
    """One-line meta strip: time-since-surfaced · tier-change · preview.

    HOL-30: `suppress_change=True` hides the tier-change chip (used by
    render_flagged_feed to avoid 3-in-a-row of identical "↑ escalated from X"
    signals collapsing into visual noise per Silver's R2 critique).
    """
    preview_html = f'<span>· {preview_text}</span>' if preview_text else ""
    change_html = ""
    if not suppress_change:
        change_html = (
            f'<span style="color:{delta["change_color"]};">'
            f'· {delta["change"]}</span>'
        )
    return (
        f'<div class="delta-strip">'
        f'<span>surfaced {delta["time"]}</span>'
        f'{change_html}'
        f'{preview_html}'
        f'</div>'
    )


# Stub data for AWAITING REVIEW and MLOPS — placeholders until engine
# returns review-state and MLOps surface ships
_STUB_AWAITING_REVIEW = [
    {
        "title": "International beneficiary setup · validation-error friction",
        "summary": ("Investigation pack closed by automated detector. "
                    "Reviewer needed for fairness sign-off — affected sessions "
                    "skew toward non-English-language-preference cohort."),
        "owner": "Compliance · UK Banking",
        "submitted": "4h ago",
        "pack_hint": "international_beneficiary_setup__dwell_after_error",
    },
]

_STUB_MLOPS_ALERTS = [
    {
        "title": "Diagnosis methodology — control-arm sample size drifted below threshold",
        "summary": ("Cell 10 (investments premier portfolio overview) "
                    "control arm dropped to n=540, below the 600 floor. "
                    "Verdict will mark NEEDS_MORE_DATA until backfill."),
        "severity": "WATCH",
        "raised": "1h ago",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# CSS — news-portal aesthetic (distinct from Workspace box discipline)
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg:         #000810;
  --bg-strip:   #001020;
  --card-2:     #001828;
  --card:       #002A3F;
  --card-elev:  #002E47;
  --border:     #003A5C;
  --blue:       #00B7F5;
  --teal:       #4FE5C2;
  --green:      #4FE583;
  --amber:      #FFB84A;
  --red:        #FF5A6E;
  --live:       #4FE583;
  --text:       #DAE6EE;
  --text-2:     #A8BCC8;  /* HOL-26 — was #94A8B6; lifted for WCAG AA on card-2 */
  --text-3:     #7A8C9A;  /* HOL-26 — was #607080; lifted for working-text legibility */
  --mono:       'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  --sans:       'Inter', 'SF Pro Text', system-ui, sans-serif;
  --serif:      'Source Serif Pro', Georgia, serif;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font-family: var(--sans);
  font-size: 14px; line-height: 1.5;
  min-height: 100vh;
}
a { color: var(--blue); text-decoration: none; }

/* ── Top nav (shared identity strip with Workspace) ─────────────────────── */
.home-topnav {
  height: 48px;
  background: var(--bg-strip);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 14px;
  padding: 0 24px;
  position: sticky; top: 0; z-index: 100;
}
.brand-logo {
  font-family: var(--mono);
  font-size: 13px; font-weight: 800;
  letter-spacing: 2px;
  color: var(--blue);
  text-shadow: 0 0 12px rgba(0,183,245,0.4);
}
.topnav-spacer { flex: 1; }
.topnav-icon, .topnav-avatar {
  background: transparent; border: 1px solid var(--border);
  color: var(--text-2); border-radius: 50%;
  width: 30px; height: 30px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 13px;
}
.topnav-icon:hover, .topnav-avatar:hover { color: var(--text); background: var(--card); }
.topnav-avatar {
  font-family: var(--mono); font-size: 10px; font-weight: 800;
  background: var(--card); color: var(--blue);
}

/* HOL-16 glossary panel — copied from Workspace for consistency */
.topnav-glossary { position: relative; }
.topnav-glossary > summary.topnav-glossary-trigger {
  list-style: none; cursor: pointer;
  font-family: var(--mono); font-size: 13px; font-weight: 700;
}
.topnav-glossary > summary::-webkit-details-marker { display: none; }
.topnav-glossary-panel {
  position: absolute; top: calc(100% + 4px); right: 0;
  background: var(--card-2); border: 1px solid var(--blue);
  width: 520px; max-height: 72vh;
  overflow-y: auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.7);
  z-index: 220; padding: 14px 16px;
}
.topnav-glossary-panel-header {
  font-size: 10px; font-weight: 800;
  letter-spacing: 1.8px; color: var(--blue);
  text-transform: uppercase;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.glossary-section { margin-bottom: 14px; }
.glossary-section-label {
  font-size: 9px; font-weight: 800; letter-spacing: 1.4px;
  color: var(--text-3); text-transform: uppercase;
  padding-bottom: 4px; margin-bottom: 6px;
  border-bottom: 1px dashed var(--border);
}
.glossary-item {
  display: grid; grid-template-columns: 150px 1fr; gap: 12px;
  padding: 4px 0; font-size: 10px;
}
.glossary-token { font-family: var(--mono); font-weight: 700; color: var(--text); }
.glossary-def { color: var(--text-2); line-height: 1.45; }

/* ── Page layout ───────────────────────────────────────────────────────── */
.home-main {
  max-width: 1240px;
  margin: 0 auto;
  padding: 32px 24px 64px;
  display: flex; flex-direction: column;
  gap: 28px;
}

/* Page-level dateline + masthead (news portal feel) */
/* HOL-26 — Spiekermann: ONE serif lead per page.
   Masthead demoted to mono nameplate (like a newspaper flag); hero card
   headline is the unambiguous lead. Eye lands once, reads down. */
.home-masthead {
  display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}
.home-masthead-title {
  font-family: var(--mono);
  font-size: 12px; font-weight: 800;
  letter-spacing: 2.4px;
  text-transform: uppercase;
  color: var(--text-3);
}
.home-masthead-dateline {
  font-family: var(--mono);
  font-size: 11px; color: var(--text-3);
  letter-spacing: 1.2px; text-transform: uppercase;
}

/* ── Section label (FLAGGED / AWAITING REVIEW / MLOPS) ─────────────────── */
.section-label {
  display: flex; align-items: center; gap: 10px;
  font-family: var(--mono);
  font-size: 10px; font-weight: 800;
  letter-spacing: 2px; text-transform: uppercase;
  color: var(--text-3);
  padding-bottom: 2px;
}
.section-label::after {
  content: ""; flex: 1; height: 1px;
  background: var(--border);
  margin-left: 6px;
}
.section-label-count {
  font-family: var(--mono);
  color: var(--text-2);
  font-weight: 700;
  background: var(--card-2);
  padding: 2px 8px; border-radius: 2px;
  font-size: 10px; letter-spacing: 0.5px;
}

/* ── HERO card (full-width, top of feed, highest-severity signal) ──────── */
.hero-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-left: 4px solid var(--red);  /* overridden inline per tier */
  padding: 24px 28px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 24px;
  align-items: start;
}
.hero-card-meta {
  display: flex; align-items: center; gap: 10px;
  font-family: var(--mono); font-size: 10px;
  letter-spacing: 1.4px; text-transform: uppercase;
  color: var(--text-3);
  margin-bottom: 10px;
}
.hero-card-tier-badge {
  font-family: var(--mono); font-weight: 800;
  letter-spacing: 1.4px; font-size: 10px;
  padding: 3px 8px;
  border: 1px solid currentColor;
  border-radius: 2px;
}
.hero-card-headline {
  font-family: var(--serif);
  font-size: 28px; font-weight: 700;
  color: var(--text);
  line-height: 1.25;
  margin: 6px 0 10px;
}
.hero-card-summary {
  font-size: 15px; color: var(--text);  /* HOL-26 — working text gets full contrast, not text-2 */
  line-height: 1.6;
  max-width: 720px;
}
.hero-card-foot {
  display: flex; align-items: center; gap: 16px;
  margin-top: 16px;
  font-family: var(--mono); font-size: 10px; color: var(--text-3);
  letter-spacing: 0.5px;
}
.hero-card-cta {
  align-self: end;
  background: var(--blue);
  color: var(--bg);
  font-family: var(--mono); font-weight: 800; letter-spacing: 1.2px;
  font-size: 11px;
  padding: 10px 18px;
  border: 0; border-radius: 2px;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
}
.hero-card-cta:hover { background: var(--teal); color: var(--bg); }

/* ── FEED grid — secondary cards ───────────────────────────────────────── */
.feed-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
@media (max-width: 1100px) { .feed-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 700px)  { .feed-grid { grid-template-columns: 1fr; } }

.feed-card {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);
  padding: 16px 18px;
  display: flex; flex-direction: column;
  gap: 8px;
  min-height: 220px;
}
.feed-card-meta {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--mono); font-size: 9px;
  letter-spacing: 1.4px; text-transform: uppercase;
  color: var(--text-3);
}
.feed-card-tag {
  font-family: var(--mono); font-weight: 800; font-size: 9px;
  letter-spacing: 1.4px;
  padding: 2px 7px;
  border: 1px solid currentColor;
  border-radius: 2px;
}
.feed-card-tier-badge {
  font-family: var(--mono); font-weight: 800;
  font-size: 9px; letter-spacing: 1.4px;
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  margin-left: auto;
}
.feed-card-headline {
  font-family: var(--serif);
  font-size: 16px; font-weight: 600;
  color: var(--text);
  line-height: 1.3;
  margin: 4px 0;
}
.feed-card-summary {
  font-size: 13px; color: var(--text);  /* HOL-26 — working text full contrast */
  line-height: 1.55;
  flex: 1;
}
.feed-card-foot {
  display: flex; align-items: center; gap: 12px;
  padding-top: 8px;
  margin-top: 8px;
  border-top: 1px solid var(--border);
  font-family: var(--mono); font-size: 9px; color: var(--text-3);
  letter-spacing: 0.5px;
}
.feed-card-cta {
  margin-left: auto;
  color: var(--blue);
  font-family: var(--mono); font-weight: 700; font-size: 10px;
  letter-spacing: 1px;
  text-decoration: none;
}
.feed-card-cta:hover { color: var(--teal); }

/* HOL-28 — AWAITING REVIEW pending state. Held packs must not read as
   live signals (Vinh). Dashed left rail + small HELD tag + slight
   opacity reduction so the card recedes from the FLAGGED grid weight. */
.feed-card.is-pending {
  border-left-style: dashed !important;
  border-left-width: 2px !important;
  opacity: 0.92;
  background: linear-gradient(180deg, var(--card-2), color-mix(in srgb, var(--card-2) 70%, var(--bg)));
}
.feed-card.is-pending .feed-card-tag {
  opacity: 0.7;
}
.feed-card-held-tag {
  margin-left: auto;
  font-family: var(--mono); font-weight: 800;
  font-size: 9px; letter-spacing: 1.4px;
  color: var(--text-3);
  background: var(--bg-strip);
  border: 1px dashed var(--text-3);
  padding: 2px 7px;
  border-radius: 2px;
  text-transform: uppercase;
}

/* HOL-24 — confidence chip + delta strip */
.confidence-chip {
  font-family: var(--mono); font-weight: 800;
  font-size: 9px; letter-spacing: 1px;
  padding: 2px 7px;
  border: 1px solid currentColor;
  border-radius: 2px;
}
/* HOL-27 — velocity tag (categorical tempo: JUST HOT / STEADY / COOLING / PLATEAU) */
.velocity-tag {
  font-family: var(--mono); font-weight: 800;
  font-size: 9px; letter-spacing: 1px;
  padding: 2px 7px;
  border: 1px solid currentColor;
  border-radius: 2px;
}
.delta-strip {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--mono); font-size: 10px;
  letter-spacing: 0.4px;
  color: var(--text-3);
  margin-top: 6px;
}
.delta-strip > span { white-space: nowrap; }

/* Hover tooltip — reused pattern from Workspace */
[data-tooltip] { position: relative; }
[data-tooltip]:hover::after {
  content: attr(data-tooltip);
  position: absolute; bottom: 100%; left: 50%;
  transform: translateX(-50%);
  margin-bottom: 6px;
  background: var(--card-2); color: var(--text);
  border: 1px solid var(--blue);
  padding: 8px 10px; border-radius: 2px;
  font-size: 11px; line-height: 1.5;
  white-space: normal; width: max-content; max-width: 320px;
  z-index: 200;
  box-shadow: 0 4px 12px rgba(0,0,0,0.6);
  pointer-events: none;
}

/* ──────────────────────────────────────────────────────────────────────
   HOL-55 — Dual-queue feed: Compliance Escalations | Commercial Opportunities
   ────────────────────────────────────────────────────────────────────── */

.dual-hero {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin-bottom: 24px;
}
.dual-queue {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin-bottom: 24px;
}
@media (max-width: 1100px) {
  .dual-hero, .dual-queue { grid-template-columns: 1fr; }
}

.dual-hero-cell {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.dual-hero-label {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 1.6px;
  text-transform: uppercase;
  color: var(--text-2);
  display: flex; align-items: baseline; gap: 10px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}
.dual-hero-label-sub {
  color: var(--text-3);
  font-weight: 400;
  letter-spacing: 0.8px;
}

/* When inside dual-hero, hero-card must shrink — single-column layout */
.dual-hero .hero-card {
  margin: 0;
  min-height: 240px;
}
.hero-card--commercial { border-left-color: var(--green); }

.section-label--queue {
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
}
.section-label-sub {
  color: var(--text-3);
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0.8px;
  text-transform: uppercase;
}
.home-queue {
  min-width: 0;
}

/* Inside a dual-queue, each queue's feed-grid renders 1 column (3 cards
   stacked vertically), since the queue itself occupies one column of the
   parent dual-queue grid. */
.feed-grid--single {
  grid-template-columns: 1fr;
}
.feed-grid--single .feed-card { min-height: 180px; }

.commercial-queue-empty {
  background: var(--card-2);
  border: 1px dashed var(--border);
  padding: 24px;
  color: var(--text-3);
  font-size: 12px;
  text-align: center;
  border-radius: 2px;
}

/* Sized commercial lift strip on hero + feed cards */
.hero-card-lift,
.feed-card-lift {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(0, 175, 160, 0.07);
  border-left: 2px solid var(--green);
  border-radius: 2px;
  font-family: var(--mono);
  font-size: 10px;
  margin-top: 6px;
  width: fit-content;
}
.hero-card-lift-label,
.feed-card-lift-label {
  color: var(--text-3);
  font-size: 9px;
  letter-spacing: 1.2px;
  text-transform: uppercase;
}
.hero-card-lift-value,
.feed-card-lift-value {
  color: var(--green);
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.hero-card-lift-sub,
.feed-card-lift-sub {
  color: var(--text-3);
  font-size: 9px;
  letter-spacing: 0.4px;
}

/* ── Multi-signal provenance strip (pulse-multisignal-identity) ──────────── */
/* Pulse fuses many signal classes; this strip shows which are wired vs
   pending (pending tokens name their gating ticket on hover). Mirrors the
   _shared.py strip used by Workspace/MLOps; Home keeps its own CSS copy. */
.signal-strip {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  margin-top: 10px;
}
.signal-strip-label {
  font-family: var(--mono); font-size: 9px; font-weight: 800;
  letter-spacing: 1.4px; text-transform: uppercase;
  color: var(--text-3); margin-right: 2px;
}
.signal-token {
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--mono); font-size: 9px; font-weight: 700;
  letter-spacing: 0.5px;
  padding: 2px 8px; border: 1px solid var(--border); border-radius: 2px;
  color: var(--text-3); cursor: help;
}
.signal-token .signal-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: transparent; border: 1px solid currentColor; flex-shrink: 0;
}
.signal-token.on { color: var(--teal); border-color: var(--teal); }
.signal-token.on .signal-dot {
  background: var(--teal); border-color: var(--teal);
  box-shadow: 0 0 6px var(--teal);
}
.signal-token.pending { color: var(--text-3); border-style: dashed; opacity: 0.85; }
"""


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def render_topnav() -> str:
    """Same identity strip as Workspace — CJI PULSE logo + utility cluster."""
    return f"""
<header class="home-topnav">
  <span class="brand-logo">CJI&nbsp;PULSE</span>
  <span class="topnav-spacer"></span>
  <button class="topnav-icon" type="button" title="Search packs (/)">⌕</button>
  <button class="topnav-icon" type="button" title="Notifications">🔔</button>
  <details class="topnav-glossary">
    <summary class="topnav-icon topnav-glossary-trigger" title="Status glossary (full token dictionary)">Aa</summary>
    <div class="topnav-glossary-panel">
      <div class="topnav-glossary-panel-header">STATUS GLOSSARY</div>
      <div>{render_glossary_panel()}</div>
    </div>
  </details>
  <button class="topnav-icon" type="button" title="Canvas guide">?</button>
  <button class="topnav-icon" type="button" title="Settings">⚙</button>
  <button class="topnav-avatar" type="button" title="Hussain Ahmed">HA</button>
</header>"""


def render_masthead() -> str:
    today = _dt.date.today().strftime("%A · %d %b %Y")
    return f"""
<div class="home-masthead">
  <div class="home-masthead-title">Pulse Home — what changed</div>
  <div class="home-masthead-dateline">{today} · {NOW}</div>
</div>"""


def render_hero(top_signal: dict, lens: str = "compliance",
                live_index: dict[tuple[str, str], int] | None = None) -> str:
    """The top-of-feed urgency card.

    HOL-55 — `lens` chooses the dimension that drives the tier badge:
      "compliance" → action_tier (current behaviour; what CRO sees)
      "commercial" → value_tier (what CCO/COO sees)
    HOL-66 — `live_index` (PULSE-127) supplies the live friction-volume number;
    the verdict stays engine-of-record."""
    pack = top_signal["pack"]
    cs   = top_signal["cell_score"]
    if lens == "commercial":
        tier = cs.value.tier
        color = _VALUE_COLORS.get(tier, "var(--green)")
        tier_dim = "value"
    else:
        tier = cs.action_tier
        color = _ACTION_COLORS.get(tier, "var(--amber)")
        tier_dim = "action"
    # PR-panel fix (Torvalds + van Rossum): all engine free-text gets
    # html.escape() at the interpolation boundary before f-stringing into
    # the DOM. The engine doesn't return markup today, but this is a
    # defensive boundary — don't trust ANY engine string in the renderer.
    journey = _e(cs.journey_id.replace("_", " · "))
    signature = _e(cs.signature_id.replace("_", " "))
    # Headline reads as news. Diagnosis becomes the "why" prefix.
    _DIAG_PREFIX = {
        "SUPPORT_PROBLEM": "Support gap detected",
        "JOURNEY_PROBLEM": "Journey design gap detected",
        "BOTH":            "Journey and support gaps both detected",
        "INCONCLUSIVE":    "Friction detected, attribution unclear",
    }
    diag_prefix = _DIAG_PREFIX.get(cs.diagnosis.diagnosis, "Friction detected")
    headline = f"{diag_prefix} on {journey.title()}"
    # HOL-25 — use de-templated summary (varied per signature × diagnosis),
    # falling back to engine recommendation if no template matches.
    varied_summary = summary_for(cs.signature_id, cs.diagnosis.diagnosis,
                                  pack["meta"]["pack_name"])
    # Templates are author-controlled (safe); placement_recommendation is
    # engine-controlled (escape).
    summary = (
        f'<strong>Signature:</strong> {signature}. '
        f'{varied_summary or _e(cs.placement_recommendation)}'
    )
    # HOL-25 — slug breadcrumb killed. Provenance moves to a hover-tooltip
    # on the INVESTIGATE → CTA so a curious reader can still verify lineage.
    # PULSE-93/96 — real lineage anchor in the provenance tooltip (meta-sha fallback).
    la = lineage_anchor_short(pack["meta"]["pack_name"])
    lineage_str = f"lineage:{la}" if la else f"sha256:{short_hash(pack['sha256'])} (meta)"
    provenance_tooltip = _e(
        f"pack: {pack['meta']['pack_name']} · {lineage_str} · "
        f"verdict v0 · DuckDB-backed (PULSE)"
    , quote=True)
    # HOL-24 — delta meta: confidence chip + time-since-surfaced + tier-change + click preview
    delta = card_delta(pack["meta"]["pack_name"])
    preview_text = f"{delta['n_findings']} sub-findings · open in Workspace"
    # HOL-55 + no-pound-pandora — friction-volume signal on the hero.
    # Primary unit is sessions/wk recoverable; £ scaffold (if ARPU set) rides
    # in the sub-line, never as the headline number.
    # HOL-66 — live PULSE-127 detected count when available, else engine projection.
    volume_label, scaffold = _volume_and_scaffold(pack, cs, live_index or {})
    hero_lift_html = (
        f'<div class="hero-card-lift">'
        f'<span class="hero-card-lift-label">RECOVERABLE</span>'
        f'<span class="hero-card-lift-value">{volume_label}/wk</span>'
        f'<span class="hero-card-lift-sub">sessions · '
        f'{scaffold if scaffold else "friction volume"}</span>'
        f'</div>'
        if volume_label else ""
    )
    tag_label = "OPPORTUNITY" if lens == "commercial" else "FLAGGED"
    return f"""
<a class="hero-card hero-card--{lens}" style="border-left-color:{color}; text-decoration:none; color:inherit;"
   href="http://localhost:8504/" target="_blank">
  <div>
    <div class="hero-card-meta">
      <span class="hero-card-tier-badge" style="color:{color};">
        {tooltip_token(tier_dim, tier)}
      </span>
      {render_confidence_chip(delta)}
      {render_velocity_tag(delta)}
      <span>{tag_label} · {journey}</span>
    </div>
    <div class="hero-card-headline">{headline}</div>
    <div class="hero-card-summary">{summary}</div>
    {hero_lift_html}
    {signal_provenance()}
    {render_delta_strip(delta, preview_text)}
  </div>
  <span class="hero-card-cta" data-tooltip="{provenance_tooltip}">INVESTIGATE →</span>
</a>"""


def render_feed_card(*, tag: str, tag_color: str, headline: str, summary: str,
                     tier: str | None = None, tier_dim: str = "action",
                     meta_left: str = "", meta_right: str = "",
                     cta_label: str = "OPEN →", accent: str = "var(--border)",
                     delta: dict | None = None, preview_text: str = "",
                     suppress_change: bool = False,
                     is_pending: bool = False,
                     volume_label: str | None = None,
                     scaffold: str | None = None) -> str:
    """Generic feed card — reused for FLAGGED, AWAITING REVIEW, MLOPS.

    HOL-24: optional `delta` adds confidence chip beside tier badge AND
    a delta strip (time-since-surfaced + tier-change + preview) below
    the summary. `preview_text` is the "X sub-findings · ..." pre-click hint.
    HOL-55 + no-pound-pandora: `volume_label` is the friction-volume primary
    (e.g. "~300"); `scaffold` is the optional £ secondary shown in the sub.
    """
    tier_html = ""
    if tier:
        color_map = _DIM_COLOR_MAPS.get(tier_dim, _ACTION_COLORS)
        tier_color = color_map.get(tier, "var(--amber)")
        tier_html = (
            f'<span class="feed-card-tier-badge" style="color:{tier_color};">'
            f'{tooltip_token(tier_dim, tier)}</span>'
        )
    confidence_html = render_confidence_chip(delta) if delta else ""
    velocity_html = render_velocity_tag(delta) if delta else ""
    delta_html = (
        render_delta_strip(delta, preview_text, suppress_change=suppress_change)
        if delta else ""
    )
    # HOL-28 — pending state: dashed left rail + HELD tag in top-right
    pending_class = " is-pending" if is_pending else ""
    held_tag = (
        '<span class="feed-card-held-tag">HELD · awaiting sign-off</span>'
        if is_pending else ""
    )
    # HOL-55 + no-pound-pandora — friction-volume strip. Primary unit is
    # sessions/wk recoverable; £ scaffold (if any) rides in the sub-line
    # with its per-session assumption named. Falls back silently when None.
    lift_html = (
        f'<div class="feed-card-lift">'
        f'<span class="feed-card-lift-label">RECOVERABLE</span>'
        f'<span class="feed-card-lift-value">{volume_label}/wk</span>'
        f'<span class="feed-card-lift-sub">sessions · '
        f'{scaffold if scaffold else "friction volume"}</span>'
        f'</div>'
        if volume_label else ""
    )
    return f"""
<a class="feed-card{pending_class}" style="border-left-color:{accent}; text-decoration:none; color:inherit;"
   href="http://localhost:8504/" target="_blank">
  <div class="feed-card-meta">
    <span class="feed-card-tag" style="color:{tag_color};">{tag}</span>
    {confidence_html}
    {velocity_html}
    {tier_html}
    {held_tag}
  </div>
  <div class="feed-card-headline">{headline}</div>
  <div class="feed-card-summary">{summary}</div>
  {lift_html}
  {delta_html}
  <div class="feed-card-foot">
    <span>{meta_left}</span>
    <span>{meta_right}</span>
    <span class="feed-card-cta">{cta_label}</span>
  </div>
</a>"""


def render_flagged_feed(flagged: list[dict], hero: dict,
                        live_index: dict[tuple[str, str], int] | None = None) -> str:
    """3-card grid of next-most-urgent signals (after the hero).

    HOL-25 — uses select_flagged_grid() to deduplicate against the hero's
    journey and prefer breadth across journeys, and per-card varied summary
    so the cards don't read as the same recommendation pasted three times.
    """
    grid = select_flagged_grid(flagged, hero, n=3)
    # HOL-30 — pre-compute deltas so we can suppress duplicate `change` chips.
    # First card with a given change keeps it; subsequent cards with the same
    # change render without the chip (Silver: "render the indicator on only
    # the FIRST card; the rest get suppressed").
    deltas = [card_delta(s["pack"]["meta"]["pack_name"]) for s in grid]
    seen_changes: set[str] = set()
    suppress_flags: list[bool] = []
    for d in deltas:
        if d["change"] in seen_changes:
            suppress_flags.append(True)
        else:
            seen_changes.add(d["change"])
            suppress_flags.append(False)

    cards = []
    for sig, delta, suppress in zip(grid, deltas, suppress_flags):
        pack = sig["pack"]
        cs = sig["cell_score"]
        tier = cs.action_tier
        accent = _ACTION_COLORS.get(tier, "var(--amber)")
        # PR-panel fix: escape engine free-text at the boundary.
        journey = _e(cs.journey_id.replace("_", " · ").title())
        signature = _e(cs.signature_id.replace("_", " "))
        varied = summary_for(cs.signature_id, cs.diagnosis.diagnosis,
                              pack["meta"]["pack_name"])
        # Templates are author-controlled (safe); recommendation is engine-controlled.
        summary = varied if varied else _e(cs.placement_recommendation)
        if len(summary) > 180:
            summary = summary[:177] + "…"
        preview = f"{delta['n_findings']} sub-findings"
        # HOL-55 — even on the compliance lens, surface friction volume when
        # the engine has it. ACUTE packs are often also COMMERCIAL-OPPORTUNITY
        # on the Value axis (the load-bearing dual-lens case).
        # HOL-66 — live PULSE-127 detected count when available.
        volume_label, scaffold = _volume_and_scaffold(pack, cs, live_index or {})
        cards.append(render_feed_card(
            tag="FLAGGED",
            tag_color="var(--red)" if tier == "ACUTE" else "var(--amber)",
            headline=f"{journey} — {signature}",
            summary=summary,
            tier=tier,
            tier_dim="action",
            meta_left=_lineage_meta(pack),
            meta_right=NOW,
            cta_label="INVESTIGATE →",
            accent=accent,
            delta=delta,
            preview_text=preview,
            suppress_change=suppress,
            volume_label=volume_label,
            scaffold=scaffold,
        ))
    if not cards:
        return ""
    remaining = max(0, len(flagged) - 1 - len(cards))
    count_label = f"{remaining} more in pipeline" if remaining else "all surfaced"
    return f"""
<section class="home-queue home-queue--compliance">
  <div class="section-label section-label--queue">
    Compliance Escalations
    <span class="section-label-sub">CRO lens · severity-sorted</span>
    <span class="section-label-count">{count_label}</span>
  </div>
  <div class="feed-grid feed-grid--single">{"".join(cards)}</div>
</section>"""


def render_commercial_queue(signals: list[dict], hero: dict | None,
                            live_index: dict[tuple[str, str], int] | None = None) -> str:
    """HOL-55 — Commercial Opportunities queue. Value-tier-sorted feed cards
    answering the CCO/COO question. Each card carries sized monthly lift
    where ARPU is configured for the journey. Falls back gracefully when
    no commercial-tier packs are in the registry."""
    if not signals:
        return f"""
<section class="home-queue home-queue--commercial">
  <div class="section-label section-label--queue">
    Commercial Opportunities
    <span class="section-label-sub">CCO lens · value-sorted</span>
    <span class="section-label-count">queue empty</span>
  </div>
  <div class="commercial-queue-empty">
    No commercial-tier packs in registry. Run worked-example scenario or
    ingest live signals to populate this lens.
  </div>
</section>"""

    # Reuse the diversity selector — same shape of input dicts.
    grid = select_flagged_grid(signals, hero, n=3) if hero else signals[:3]

    cards: list[str] = []
    for sig in grid:
        pack = sig["pack"]
        cs = sig["cell_score"]
        value_tier = sig["value_tier"]
        accent = _VALUE_COLORS.get(value_tier, "var(--green)")
        journey = _e(cs.journey_id.replace("_", " · ").title())
        signature = _e(cs.signature_id.replace("_", " "))
        varied = summary_for(cs.signature_id, cs.diagnosis.diagnosis,
                              pack["meta"]["pack_name"])
        summary = varied if varied else _e(cs.placement_recommendation)
        if len(summary) > 180:
            summary = summary[:177] + "…"
        delta = card_delta(pack["meta"]["pack_name"])
        preview = f"{delta['n_findings']} sub-findings"
        # HOL-66 — live PULSE-127 detected count when available.
        volume_label, scaffold = _volume_and_scaffold(pack, cs, live_index or {})
        cards.append(render_feed_card(
            tag="OPPORTUNITY",
            tag_color="var(--green)" if value_tier == "COMMERCIAL-OPPORTUNITY" else "var(--amber)",
            headline=f"{journey} — {signature}",
            summary=summary,
            tier=value_tier,
            tier_dim="value",
            meta_left=_lineage_meta(pack),
            meta_right=NOW,
            cta_label="INVESTIGATE →",
            accent=accent,
            delta=delta,
            preview_text=preview,
            suppress_change=False,
            volume_label=volume_label,
            scaffold=scaffold,
        ))

    # Aggregate headline across the queue — friction volume (sessions/wk),
    # NOT £ (no-pound-pandora). This is the CCO's board-ready number.
    total_sessions = sum(s.get("sessions_per_week", 0) for s in signals)
    total_label = f"~{total_sessions:,} sessions/wk recoverable" if total_sessions else None
    remaining = max(0, len(signals) - len(cards))
    count_label = (
        f"{total_label} · {remaining} more"
        if total_label and remaining
        else (total_label if total_label else
              (f"{remaining} more in queue" if remaining else "all surfaced"))
    )

    return f"""
<section class="home-queue home-queue--commercial">
  <div class="section-label section-label--queue">
    Commercial Opportunities
    <span class="section-label-sub">CCO lens · value-sorted</span>
    <span class="section-label-count">{count_label}</span>
  </div>
  <div class="feed-grid feed-grid--single">{"".join(cards)}</div>
</section>"""


def render_awaiting_review(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for it in items:
        # HOL-24 — synthetic delta for stub items (consistent shape, unique seed)
        delta = card_delta(it.get("pack_hint", it["title"]))
        cards.append(render_feed_card(
            tag="AWAITING REVIEW",
            tag_color="var(--teal)",
            headline=it["title"],
            summary=it["summary"],
            meta_left=f"owner: {it['owner']}",
            meta_right=f"closed {it['submitted']}",
            cta_label="REVIEW →",
            accent="var(--teal)",
            delta=delta,
            preview_text="1 reviewer assigned · fairness sign-off required",
            is_pending=True,  # HOL-28 — held packs render with pending wash
        ))
    return f"""
<section>
  <div class="section-label">
    Awaiting review
    <span class="section-label-count">{len(items)}</span>
  </div>
  <div class="feed-grid">{"".join(cards)}</div>
</section>"""


def render_mlops_alerts(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for it in items:
        sev_color = "var(--amber)" if it["severity"] == "WATCH" else "var(--red)"
        delta = card_delta(it["title"])
        cards.append(render_feed_card(
            tag="MLOPS",
            tag_color=sev_color,
            headline=it["title"],
            summary=it["summary"],
            tier=it["severity"],
            tier_dim="risk",
            meta_left=f"raised {it['raised']}",
            meta_right="MLOps Console (HOL-6 pending)",
            cta_label="ACKNOWLEDGE →",
            accent=sev_color,
            delta=delta,
            preview_text="affects 1 cell · auto-resolves on backfill",
        ))
    return f"""
<section>
  <div class="section-label">
    MLOps alerts
    <span class="section-label-count">{len(items)}</span>
  </div>
  <div class="feed-grid">{"".join(cards)}</div>
</section>"""


# ─────────────────────────────────────────────────────────────────────────────
# Page composition
# ─────────────────────────────────────────────────────────────────────────────

def render_page() -> str:
    packs = discover_packs()
    flagged = collect_flagged_signals(packs)
    commercial = collect_commercial_signals(packs)
    # HOL-66 — live friction volume (PULSE-127). Built once; fails soft to {}.
    live_index = _live_friction_index()

    sections: list[str] = []
    # HOL-55 — dual-hero. Left = compliance lens (severity-sorted). Right =
    # commercial lens (value-sorted, sized lift first). Both load on first
    # paint so a CCO and CRO both see their entry point without filtering.
    compliance_hero = flagged[0] if flagged else None
    commercial_hero = commercial[0] if commercial else None
    if compliance_hero or commercial_hero:
        left_block = (
            f'<div class="dual-hero-cell">'
            f'<div class="dual-hero-label">'
            f'COMPLIANCE ESCALATIONS '
            f'<span class="dual-hero-label-sub">CRO lens · severity-sorted</span>'
            f'</div>'
            f'{render_hero(compliance_hero, lens="compliance", live_index=live_index) if compliance_hero else ""}'
            f'</div>'
        )
        right_block = (
            f'<div class="dual-hero-cell">'
            f'<div class="dual-hero-label">'
            f'COMMERCIAL OPPORTUNITIES '
            f'<span class="dual-hero-label-sub">CCO lens · value-sorted</span>'
            f'</div>'
            f'{render_hero(commercial_hero, lens="commercial", live_index=live_index) if commercial_hero else ""}'
            f'</div>'
        )
        sections.append(
            f'<section class="dual-hero">{left_block}{right_block}</section>'
        )

    # HOL-55 — dual queue below the hero. Same split: compliance left,
    # commercial right. Stacks to 1 column on narrow viewports via CSS.
    queues: list[str] = []
    if flagged and compliance_hero:
        queues.append(render_flagged_feed(flagged, compliance_hero, live_index))
    queues.append(render_commercial_queue(commercial, commercial_hero, live_index))
    if queues:
        sections.append(
            f'<section class="dual-queue">{"".join(queues)}</section>'
        )

    sections.append(render_awaiting_review(_STUB_AWAITING_REVIEW))
    sections.append(render_mlops_alerts(_STUB_MLOPS_ALERTS))

    body = "".join(sections)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pulse Home — what changed</title>
<style>{CSS}</style>
</head>
<body>
{render_topnav()}
<main class="home-main">
{render_masthead()}
{body}
</main>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "index.html"
    html = render_page()
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
