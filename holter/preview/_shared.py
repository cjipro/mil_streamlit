"""Shared primitives for all Holter preview surfaces.

Per Cannon's PR-panel ruling (HOL-35): no Holter renderer should import
helpers from another renderer. The 4-layer box discipline, body/headline
component family, engine-bridge functions, color maps, glossary
infrastructure, and sparkline helper all live here so that:

  - render_holter.py (HOL-3 Workspace, :8504)
  - render_home.py   (HOL-4 Pulse Home, :8505)
  - render_mlops.py  (HOL-6 MLOps Console, :8506)
  - future render_api.py / render_monitor.py / etc.

...all import from `_shared` as the single source of truth, and a
broken/failed import in any one renderer does NOT cascade to the others.

What IS in here:
  - The big `CSS` string (~685 lines) — design tokens (--bg, --card, etc.),
    box-discipline classes (.holter-box, .box-header/body/footer),
    body composables (.body-action-primary, .body-kpi-tile, .body-bar,
    .body-disclosure, .body-quality, .body-primary-kpi, etc.), headline
    shapes, glossary panel, sparkline, tooltip pattern. NOTE: also includes
    workspace-specific classes (.holter-filter-strip, .holter-ticker,
    .holter-journey-row, .hypothesis-controls) — these ride along for
    MLOps's wholesale import without breaking anything; a future ticket
    can split them into a smaller core.

What's NOT in here (intentionally):
  - render_home.py's self-contained CSS (HOL-4 Home built its own copy
    before _shared.py existed; deduplicating is a separate ticket)
  - Surface-specific helpers (Workspace's filter strip / ticker / journey
    row, Home's card-summary templates, MLOps's stub generators) — those
    are app-level concerns, not platform primitives

Domain neutrality: nothing in this file references friction, decisions,
or banking. CLARK Action tier strings appear in STATUS_GLOSSARY as
methodology vocabulary, but the token-registry pattern itself is generic.

When Hodos extraction begins, this file is the seed candidate. See
`docs/hodos-foundations.md` for the panel-validated inventory.
"""

from __future__ import annotations

import datetime as _dt
import functools
import hashlib
import sys
from html import escape as _e
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
PACKS_DIR = REPO / "pulse" / "decision_packs"
JOURNEY_TAXONOMY = REPO / "pulse" / "contracts" / "journey_taxonomy.yaml"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


NOW = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ─────────────────────────────────────────────────────────────────────────────
# Data discovery — engine bridge (Pulse-specific layout; only this module
# should know `pulse/decision_packs/` exists)
# ─────────────────────────────────────────────────────────────────────────────

def load_journey_taxonomy() -> dict[str, str]:
    if not JOURNEY_TAXONOMY.exists():
        return {}
    data = yaml.safe_load(JOURNEY_TAXONOMY.read_text(encoding="utf-8"))
    return data.get("journeys", {})


def discover_packs() -> list[dict]:
    packs: list[dict] = []
    if not PACKS_DIR.exists():
        return packs
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        meta_path = pack_dir / "metadata.yaml"
        samples_dir = pack_dir / "samples"
        hyp_path = pack_dir / "hypothesis.yaml"
        if not meta_path.exists() or not samples_dir.exists():
            continue
        raw_bytes = meta_path.read_bytes()
        meta = yaml.safe_load(raw_bytes.decode("utf-8"))
        hypothesis = (
            yaml.safe_load(hyp_path.read_text(encoding="utf-8"))
            if hyp_path.exists() else None
        )
        bank_md = (samples_dir / "bank.md").read_text(encoding="utf-8") \
            if (samples_dir / "bank.md").exists() else ""
        packs.append({
            "dir": pack_dir,
            "meta": meta,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "hypothesis": hypothesis,
            "bank_md": bank_md,
        })
    return packs


def short_hash(h: str) -> str:
    return f"{h[:7]}…{h[-4:]}"


def screen_short(screen_id: str) -> str:
    parts = screen_id.split(".")
    if len(parts) >= 2:
        return f"{parts[0]} · {parts[-1]}"
    return screen_id


def headline_pack(packs: list[dict]) -> dict:
    for p in packs:
        h = p["hypothesis"] or {}
        if h.get("cell_id") == 10:
            return p
    for p in packs:
        if "abandon" in p["meta"]["pack_name"] and "cards" in p["meta"]["pack_name"]:
            return p
    return packs[0] if packs else {}


# ─────────────────────────────────────────────────────────────────────────────
# Engine integration — per-pack PlacementCell from the worked scenario
# ─────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _build_pack_cell_index() -> dict[str, Any]:
    """Load the agentic-AI placement scenario and key its cells by pack_dir.

    Engine-bridge function — failure here cascades to every box that calls
    get_pack_cell() returning None, which renders as "UNAVAILABLE / PENDING".
    PR-panel fix (Torvalds + van Rossum): the previous bare-except silently
    swallowed every failure with zero diagnostic — a broken scenario.yaml
    or import-chain bug would manifest only as a cosmetic "no data" state
    and cost an afternoon to find. Now logs the exception so it's visible
    in stderr while still failing soft (renderer keeps working).
    """
    import logging
    try:
        from pulse.scenarios.agentic_ai_placement import run_placement_scenario
        scenario_path = REPO / "pulse" / "scenarios" / "agentic_ai_placement" / "scenario.yaml"
        with scenario_path.open("r", encoding="utf-8") as f:
            scenario = yaml.safe_load(f)
        pack_dirs = [c["pack_dir"] for c in scenario["cells"]]
        matrix = run_placement_scenario()
        return {pack_dir: cell for pack_dir, cell in zip(pack_dirs, matrix.cells)}
    except Exception:
        logging.exception(
            "_build_pack_cell_index failed — engine scenario unavailable; "
            "every box will render as UNAVAILABLE until fixed"
        )
        return {}


def get_pack_cell(pack_name: str):
    return _build_pack_cell_index().get(pack_name)


# ─────────────────────────────────────────────────────────────────────────────
# Engine integration — per-pack Cause-class analytics (PULSE-93/96 synthesis layer)
#
# The SECOND engine bridge, alongside get_pack_cell(). Where get_pack_cell()
# returns the DECISION-layer placement verdict, this returns the SYNTHESIS-layer
# `AnalyticOutputs`: the real confidence band / interval, calibration (Brier),
# fairness flag, and lineage anchor the surface must show (HOL-3 acceptance:
# "lineage hash visible on every rendering"). Before PULSE-93/96 shipped these
# were hardcoded placeholders ("Confidence 0.82", "awaiting PULSE-93 hydration").
#
# Fails soft exactly like get_pack_cell — fixture packs (no hypothesis.yaml),
# packs whose cell_id isn't in the FrictionBench corpus, or any engine error
# return None, logged to stderr so the failure is visible while the renderer
# keeps working. Callers render the honest "pending" state on None.
# ─────────────────────────────────────────────────────────────────────────────

# Match the analytics + /investigations/<pack>/run default so the surface shows
# the same numbers an API consumer would get.
_UI_SESSIONS_PER_CELL = 200


@functools.lru_cache(maxsize=32)
def get_pack_analytics(pack_name: str):
    """Real Cause-class AnalyticOutputs for a runnable pack, or None (fail-soft)."""
    import logging
    try:
        from pulse.analytics.cause import build_analytic_outputs
        return build_analytic_outputs(pack_name, sessions_per_cell=_UI_SESSIONS_PER_CELL)
    except Exception:
        logging.exception(
            "get_pack_analytics(%s) failed — synthesis analytics unavailable; "
            "quality strip + lineage badge render as PENDING for this pack",
            pack_name,
        )
        return None


def lineage_anchor_short(pack_name: str) -> str | None:
    """Short form of a pack's REAL lineage anchor (sha256 of the analytic facts),
    or None when analytics are unavailable. This is the hash the surface shows as
    the lineage badge — NOT the metadata-file sha (`pack["sha256"]`), which is
    pack identity, not run provenance."""
    out = get_pack_analytics(pack_name)
    if out is None:
        return None
    return short_hash(out.payload["lineage_anchor"])


def analytics_quality_items(pack_name: str) -> list[str] | None:
    """The four decision-QUALITY signals for body_quality_strip, sourced from the
    real synthesis analytics: confidence band + interval, calibration (Brier),
    fairness state, lineage anchor. None when analytics unavailable.

    Replaces the hardcoded 'Confidence 0.82 / Designed ceiling 0.85 / Fairness
    attested / Lineage anchored' strip. The Cause analytics layer does not produce
    a 'designed ceiling' (that is a FrictionBench/detection concept), so the
    fabricated ceiling literal is dropped in favour of the real Brier calibration
    score — an honest decision-quality signal the engine actually computes."""
    out = get_pack_analytics(pack_name)
    if out is None:
        return None
    p = out.payload
    conf = (
        f"Confidence {p['confidence_band']} "
        f"[{p['confidence_low']:.2f}–{p['confidence_high']:.2f}]"
    )
    brier = p.get("brier_score")
    calib = f"Brier {brier:.3f}" if brier is not None else "Brier —"
    ff = p.get("fairness_flag")
    fairness = (
        "Fairness within parity" if ff is None
        else f"Fairness FLAG {ff['disparity']:.2f} > {ff['threshold']:.2f}"
    )
    lineage = f"Lineage {short_hash(p['lineage_anchor'])}"
    return [conf, calib, fairness, lineage]


# ─────────────────────────────────────────────────────────────────────────────
# Commercial signal — friction-volume PRIMARY, £ scaffold SECONDARY.
#
# Single source of truth for how every surface renders the commercial signal.
# The rule (see no-pound-pandora): lead with friction-volume (sessions/week,
# the bank's own outcome vocabulary); show £ only as a derived scaffold that
# names its own cost-per-unit assumption. Raw £ as a primary stat is forbidden
# — it opens the assumption Pandora's box (ARPU / baseline scrutiny) and forces
# money-first framing on a customer-experience signal.
# ─────────────────────────────────────────────────────────────────────────────


def _format_count(n: int) -> str:
    """Compact count: 1234 → '1.2k', 980 → '980'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _format_gbp(amount: float) -> str:
    """Compact £: 72000 → '£72k', 1_400_000 → '£1.4m'."""
    if amount >= 1_000_000:
        return f"£{amount / 1_000_000:.1f}m"
    if amount >= 1_000:
        return f"£{amount / 1_000:.0f}k"
    return f"£{amount:.0f}"


def friction_volume_value(value_score: Any, period: str = "week") -> str | None:
    """PRIMARY commercial unit — recoverable sessions per week/month.

    Returns a bare value string (e.g. '~300', '~1.3k') for use as a headline
    stat value, or None when the engine couldn't compute it. Always available
    when metrics exist (no ARPU dependency)."""
    attr = (
        "recoverable_sessions_per_week" if period == "week"
        else "recoverable_sessions_per_month"
    )
    n = getattr(value_score, attr, None)
    if n is None:
        return None
    return f"~{_format_count(int(n))}"


def friction_volume_label(period: str = "week") -> str:
    """The unit label paired with friction_volume_value."""
    return "SESSIONS/WK RECOVERABLE" if period == "week" else "SESSIONS/MO RECOVERABLE"


def friction_volume_headline(value_score: Any, period: str = "week") -> str | None:
    """PRIMARY commercial unit as a self-contained phrase, e.g.
    '~300 sessions/wk recoverable'. None when not computable."""
    val = friction_volume_value(value_score, period)
    if val is None:
        return None
    unit = "sessions/wk" if period == "week" else "sessions/mo"
    return f"{val} {unit} recoverable"


def commercial_scaffold(value_score: Any) -> str | None:
    """SECONDARY cost framing — derived from friction-volume × ARPU, with the
    per-session ARPU assumption named explicitly so the reader sees the
    assumption, not just the conclusion. Returns None when the deployment
    has not configured ARPU for the journey (then surfaces show friction
    volume only — never a bare £)."""
    lift = getattr(value_score, "estimated_monthly_lift_gbp", None)
    arpu = getattr(value_score, "arpu_per_session_gbp", None)
    if lift is None or arpu is None:
        return None
    return f"≈ {_format_gbp(lift)}/mo at £{arpu:.0f}/session"


def _extract_quote(pack: dict) -> str:
    """Pull a quotable sentence from a pack's bank_md.

    Returns HTML-escaped text — callers can safely f-string the result
    into a `data-tooltip` attribute OR a body text node without further
    escaping. PR-panel fix (Torvalds + van Rossum): bank_md is free
    text from authored markdown and could contain `<`, `&`, etc.
    """
    raw = pack.get("bank_md", "")
    cleaned = " ".join(
        ln.strip().lstrip("#").strip()
        for ln in raw.split("\n")
        if ln.strip() and not ln.startswith("```")
    )
    truncated = cleaned[:280] + ("…" if len(cleaned) > 280 else "")
    return _e(truncated, quote=True)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-signal provenance — Pulse is a MULTI-signal friction engine
# ([[pulse-multisignal-identity]]), not an app-analytics tool. A finding's
# provenance must show WHICH signal classes the engine fuses, and — honestly —
# which are not yet wired. Today the detection runtime (PULSE-126) operates on
# app-session behavioural events with demographic cohort context; the other
# channels are pending their gating foundation tickets. The strip never
# fabricates a signal: pending tokens name the ticket that unblocks them, so a
# CCO/CRO reading a finding sees the multi-signal shape AND its honest state.
# ─────────────────────────────────────────────────────────────────────────────

# (tooltip, fused-by-default) per signal class. Order = render order.
_SIGNAL_META: dict[str, tuple[str, bool]] = {
    "BEHAVIOUR": (
        "App-session behavioural events (dwell / abandon / back-press) — "
        "the detection runtime's primary signal (PULSE-126).", True),
    "DEMOGRAPHICS": (
        "Customer demographics (age_band, region, tenure) — fused as cohort "
        "context from CUST_DIM.", True),
    "VULNERABILITY": (
        "First-class in Pulse, but the vulnerability-classification "
        "methodology is unpublished (PULSE-122) — fused once the rubric ships.", False),
    "VOICE": (
        "Voice-of-customer (NPS, app-store reviews) — pending ingestion + "
        "the cross-channel joins (PULSE-121).", False),
    "CALLS": (
        "Contact-centre / cross-channel signal — pending the cross-channel "
        "joins (PULSE-121).", False),
}

SIGNAL_CLASSES: tuple[str, ...] = tuple(_SIGNAL_META)


def signal_provenance(*, label: str = "SIGNALS", fused: set[str] | None = None) -> str:
    """Render the multi-signal provenance strip — which signal classes are
    fused into this finding vs pending their gating join.

    `fused=None` uses the engine-state defaults in `_SIGNAL_META` (behaviour +
    demographics wired; vulnerability/voice/calls pending). Pass an explicit
    set to override per-finding once the engine returns provenance directly.
    Domain vocabulary lives here as methodology terms, same as STATUS_GLOSSARY.
    """
    toks = []
    for cls, (tip, default_on) in _SIGNAL_META.items():
        on = (cls in fused) if fused is not None else default_on
        state = "on" if on else "pending"
        safe = tip.replace('"', "&quot;")
        toks.append(
            f'<span class="signal-token {state}" data-tooltip="{safe}">'
            f'<span class="signal-dot"></span>{cls}</span>'
        )
    return (
        f'<div class="signal-strip">'
        f'<span class="signal-strip-label">{label}</span>'
        f'{"".join(toks)}'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Color maps — semantic palette for tier badges + chips
# ─────────────────────────────────────────────────────────────────────────────

# Tier colour maps (mirror HOL-11 / HOL-9)

_DIAGNOSIS_COLORS = {
    "SUPPORT_PROBLEM":  "var(--green)",
    "JOURNEY_PROBLEM":  "var(--amber)",
    "BOTH":             "var(--blue)",
    "INCONCLUSIVE":     "#7A7A7A",
}
_RISK_COLORS = {
    "NOMINAL":          "#5A6E7A",
    "WATCH":            "var(--teal)",
    "ESCALATE":         "var(--amber)",
    "REGULATORY-FLAG":  "var(--red)",
}
_VALUE_COLORS = {
    "NOMINAL":                  "#5A6E7A",
    "WATCH":                    "var(--teal)",
    "SIGNIFICANT":              "var(--amber)",
    "COMMERCIAL-OPPORTUNITY":   "var(--green)",
}
_ACTION_COLORS = {
    "ACUTE":                    "var(--red)",
    "REGULATORY-FLAG":          "var(--amber)",
    "COMMERCIAL-OPPORTUNITY":   "var(--green)",
    "WATCH":                    "var(--teal)",
    "NOMINAL":                  "#5A6E7A",
    "NEEDS_MORE_DATA":          "#7A7A7A",
}


# ─────────────────────────────────────────────────────────────────────────────
# HOL-14 — hover glossary, scoped by dimension because the same literal
# token (NOMINAL, WATCH, COMMERCIAL-OPPORTUNITY) has distinct meanings
# across Action / Value / Risk dimensions.
# ─────────────────────────────────────────────────────────────────────────────

STATUS_GLOSSARY: dict[str, dict[str, str]] = {
    "action": {
        "ACUTE":                  "Highest-priority tier — both value upside and risk exposure are large. Act now with full guardrails.",
        "REGULATORY-FLAG":        "Material regulatory exposure regardless of value. Compliance review required before any deployment or change.",
        "COMMERCIAL-OPPORTUNITY": "Large value upside with manageable risk. Strong candidate for the commercial roadmap.",
        "WATCH":                  "Material but bounded signal. Track over time; revisit if trend or cohort shifts.",
        "NOMINAL":                "No significant signal across value or risk dimensions. No action required at this time.",
        "NEEDS_MORE_DATA":        "Insufficient data to compute a confident verdict. Collect more sessions or widen the time window before deciding.",
        "PENDING":                "Engine has not yet produced a verdict for this selection.",
    },
    "diagnosis": {
        "SUPPORT_PROBLEM": "Assistance arm closes the failure gap — friction is in the support layer, not the journey design.",
        "JOURNEY_PROBLEM": "Assistance does not close the gap — the journey itself needs to change, not the support around it.",
        "BOTH":            "Assistance helps but a residual gap remains — both journey design and support layer need attention.",
        "INCONCLUSIVE":    "Assistance and no-assistance arms show indistinguishable outcomes — the data cannot separate support vs journey causes yet.",
    },
    "value": {
        "NOMINAL":                "Affected population × severity × counterfactual baseline is small. Low business value at stake.",
        "WATCH":                  "Material value signal but below intervention threshold. Track over time.",
        "SIGNIFICANT":            "Material value at stake — affected population or severity warrants intervention consideration.",
        "COMMERCIAL-OPPORTUNITY": "Large value upside — affected population, severity, or counterfactual baseline all favour intervention.",
    },
    "risk": {
        "NOMINAL":         "No regulatory or policy thresholds tripped. Standard handling applies.",
        "WATCH":           "Risk signals present but below escalation threshold. Monitor.",
        "ESCALATE":        "Material risk signal — internal escalation triggers met (policy thresholds or vulnerable-cohort over-representation).",
        "REGULATORY-FLAG": "Regulatory taxonomy match present — external regulator concern likely. Compliance involvement required.",
    },
    "severity": {
        "Positive": "Detector-class packs — signature is expected to fire on this journey.",
        "Negative": "Discriminator-class packs — signature must NOT fire (used to test for false positives).",
        "All":      "All packs across detector and discriminator classes.",
    },
}


def tooltip_token(dimension: str, token: str) -> str:
    """Wrap a status token in a hover-tooltip span if the glossary defines it.

    Uses the existing [data-tooltip]:hover::after CSS pattern (no JS).
    Falls back to the bare token if no glossary entry exists.
    """
    definition = STATUS_GLOSSARY.get(dimension, {}).get(token)
    if not definition:
        return token
    # Escape embedded double-quotes so the attribute parses cleanly
    safe = definition.replace('"', "&quot;")
    return f'<span data-tooltip="{safe}">{token}</span>'


def render_glossary_panel() -> str:
    """HOL-16 Part B — persistent glossary affordance.

    Renders the full STATUS_GLOSSARY as a grouped, scrollable panel that
    drops down from the top-nav glossary icon. Tokens listed per dimension
    so the reader sees how (e.g.) NOMINAL differs across Action / Value / Risk.
    """
    sections = []
    for dim, entries in STATUS_GLOSSARY.items():
        items = "".join(
            f'<div class="glossary-item">'
            f'<span class="glossary-token">{tok}</span>'
            f'<span class="glossary-def">{defn}</span>'
            f'</div>'
            for tok, defn in entries.items()
        )
        sections.append(
            f'<div class="glossary-section">'
            f'<div class="glossary-section-label">{dim.upper()}</div>'
            f'{items}'
            f'</div>'
        )
    return "".join(sections)


# ─────────────────────────────────────────────────────────────────────────────
# Box primitives — universal 4-layer discipline (header 48 / headline 96 /
# body 1fr / footer 48). Domain-neutral; lift these into Hodos as v0 primitive.
# ─────────────────────────────────────────────────────────────────────────────

def render_box(*, header: str, headline: str, body: str, footer: str,
               accent_color: str = "var(--border)",
               box_attrs: str = "") -> str:
    """Universal 4-layer box. accent_color drives:
       - left-edge severity border (3px)
       - subtle bottom underline under header (via --box-accent CSS var)
       - per-box visual identity inside the locked shape."""
    style = (
        f'style="border-left-color:{accent_color};'
        f'--box-accent:{accent_color};"'
    )
    return f'''
<div class="holter-box" {style} {box_attrs}>
  <div class="box-header">{header}</div>
  <div class="box-headline">{headline}</div>
  <div class="box-body">{body}</div>
  <div class="box-footer">{footer}</div>
</div>'''


def box_header(title: str, sub: str = "") -> str:
    sub_html = f'<span class="box-header-sub">{sub}</span>' if sub else ""
    return f'<span class="box-header-title">{title}</span>{sub_html}'


def box_footer(version: str, ts: str, live: bool = True, note: str = "") -> str:
    live_html = '<span class="box-footer-live">LIVE</span>' if live else ""
    pills = (
        f'<span class="box-footer-pill">{version}</span>'
        f'<span class="box-footer-pill">{ts}</span>'
        f'{live_html}'
    )
    note_html = f'<div class="box-footer-note">{note}</div>' if note else ""
    return f'<div class="box-footer-pills">{pills}</div>{note_html}'


# ─────────────────────────────────────────────────────────────────────────────
# Headline shape vocabulary — three patterns for three box purposes
# ─────────────────────────────────────────────────────────────────────────────

def headline_stat_card(*, label: str, value: str, delta: str, traj: str,
                        meta_left: str, meta_right: str, progress_pct: int) -> str:
    return f'''
<div class="headline-stat">
  <div class="headline-stat-row1">
    <span class="headline-stat-label">{label}</span>
    <span class="headline-stat-value">{value}</span>
    <span class="headline-stat-delta">{delta}</span>
    <span class="headline-stat-traj">{traj}</span>
  </div>
  <div class="headline-stat-meta">
    <span>{meta_left}</span>
    <span style="margin-left:auto;">{meta_right}</span>
  </div>
  <div class="headline-stat-progress">
    <div class="headline-stat-progress-fill" style="width:{progress_pct}%;"></div>
  </div>
</div>'''


def headline_chip_strip(chips: list[tuple[str, str, str]]) -> str:
    items = "".join(
        f'<span class="headline-chip" style="border-color:{color};">'
        f'<span class="headline-chip-value" style="color:{color};">{value}</span>'
        f'<span class="headline-chip-label">{label}</span>'
        f'</span>'
        for value, label, color in chips
    )
    return f'<div class="headline-chips">{items}</div>'


def headline_tier_badge(tier: str, color: str, context: str) -> str:
    return f'''
<div class="headline-tier">
  <span class="headline-tier-badge" style="color:{color};border-color:{color};">{tier}</span>
  <span class="headline-tier-context">{context}</span>
</div>'''


# ─────────────────────────────────────────────────────────────────────────────
# Body composables — SRP-clean helpers, each does one thing
# ─────────────────────────────────────────────────────────────────────────────

def body_evidence_cards(quotes: list[tuple[str, str]]) -> str:
    """Render evidence cards. Input contract: both tuple members must be
    pre-escaped HTML-safe strings (callers use `_e()` from html.escape).

    PR-panel fix: previous version did `q[0].replace(chr(34), chr(39))` as
    a half-measure for the data-tooltip attribute. Now that callers escape
    at the boundary (with quote=True), `"` is already `&quot;` and the
    replace is a no-op. Removed for clarity.
    """
    return "".join(
        f'<div class="body-evidence-card">'
        f'<div class="body-evidence-quote" data-tooltip="{q[0]}">{q[0]}</div>'
        f'<div class="body-evidence-attr">{q[1]}</div>'
        f'</div>'
        for q in quotes
    )


def body_kpi_tiles(tiles: list[tuple[str, str, str, str]]) -> str:
    items = "".join(
        f'<div class="body-kpi-tile" style="border-top-color:{color};">'
        f'<div class="body-kpi-value" style="color:{color};">{value}</div>'
        f'<div class="body-kpi-label">{label}</div>'
        f'<div class="body-kpi-sub">{sub}</div>'
        f'</div>'
        for value, label, sub, color in tiles
    )
    return f'<div class="body-kpi-grid">{items}</div>'


def body_chip_strip(chips: list[tuple[str, str, str]]) -> str:
    items = "".join(
        f'<span class="body-chip">'
        f'<span class="body-chip-dot" style="background:{color};"></span>'
        f'<span>{label}</span>'
        f'<span class="body-chip-count">{count}</span>'
        f'</span>'
        for label, count, color in chips
    )
    return f'<div class="body-chip-strip">{items}</div>'


def body_bars(bars: list[tuple[str, int, str, str]]) -> str:
    rows = "".join(
        f'<div class="body-bar-row">'
        f'<span class="body-bar-label">{label}</span>'
        f'<div class="body-bar-track">'
        f'<div class="body-bar-fill" style="width:{pct}%;background:{color};"></div>'
        f'</div>'
        f'<span class="body-bar-value">{value}</span>'
        f'</div>'
        for label, pct, value, color in bars
    )
    return f'<div class="body-bars">{rows}</div>'


def body_lines(lines: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="body-line">'
        f'<span class="body-line-dot" style="background:{color};"></span>'
        f'<span>{text}</span>'
        f'</div>'
        for text, color in lines
    )


def body_action_line(text: str, color: str) -> str:
    """Prominent action callout — full-width band, tier-coloured left rail."""
    return (
        f'<div class="body-action" style="border-left-color:{color};">'
        f'<span>{text}</span>'
        f'</div>'
    )


def body_action_primary(label: str, text: str, color: str) -> str:
    """PRIMARY action block — the dominant focal point of the box body.

    Used in Box 1 (VERDICT) where ACTION must outweigh supporting metadata
    (Diagnosis/Value/Risk chips and decision-quality strip). Larger padding,
    bigger type, thicker tier-coloured rail than body_action_line.
    """
    return (
        f'<div class="body-action-primary" '
        f'style="border-left-color:{color};">'
        f'<div class="body-action-primary-label" style="color:{color};">{label}</div>'
        f'<div class="body-action-primary-text">{text}</div>'
        f'</div>'
    )


def body_quality_strip(items: list[str], label: str = "DECISION QUALITY") -> str:
    """Small decision-quality strip — confidence, ceiling, fairness, lineage.

    Kozyrkov separation: decision-INPUT signals (Diagnosis/Value/Risk) and
    decision-QUALITY signals (Confidence/Ceiling/Fairness) must not mix.
    This strip is the visual container for the quality side.
    """
    items_html = "".join(f'<span>{i}</span>' for i in items)
    return (
        f'<div class="body-quality">'
        f'<span class="body-quality-label">{label}</span>'
        f'<span class="body-quality-items">{items_html}</span>'
        f'</div>'
    )


def body_primary_kpi(value: str, label: str, sub: str, color: str) -> str:
    """Single highlighted KPI — full-width supporting stat block (HOL-15).

    Used when one KPI deserves visual primacy after a hero element
    (e.g., Box 3 EVIDENCE's primary supporting stat after the sparkline).
    Replaces 3-tile clutter with one bold stat + room to breathe.
    """
    return (
        f'<div class="body-primary-kpi" style="border-top-color:{color};">'
        f'<div class="body-primary-kpi-value" style="color:{color};">{value}</div>'
        f'<div class="body-primary-kpi-meta">'
        f'<span class="body-primary-kpi-label">{label}</span>'
        f'<span class="body-primary-kpi-sub">{sub}</span>'
        f'</div>'
        f'</div>'
    )


def body_disclosure(summary: str, content: str) -> str:
    """Progressive-disclosure block — native HTML <details>/<summary> (HOL-15).

    Secondary KPIs and detail metadata hide here so the box body holds a
    single primary focal point. No JS — uses the <details> element which
    is keyboard/screen-reader accessible by default.
    """
    return (
        f'<details class="body-disclosure">'
        f'<summary class="body-disclosure-summary">{summary}</summary>'
        f'<div class="body-disclosure-content">{content}</div>'
        f'</details>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# SVG helpers
# ─────────────────────────────────────────────────────────────────────────────

def sparkline_svg(values: list[float], color: str, width: int = 220, height: int = 36,
                  reference_value: float | None = None,
                  reference_color: str = "rgba(180,200,210,0.55)") -> str:
    """Pure-SVG sparkline — no JS, no chart library, scales to the values given.

    HOL-17: optional reference_value renders as a dashed horizontal line
    (e.g., Designed Ceiling). The y-axis scale expands to fit both the
    trend extremes AND the reference, so the line is always visible.
    """
    if not values:
        return ""
    n = len(values)
    # Include reference in the y-axis range so it's always in-frame
    all_y = list(values) + ([reference_value] if reference_value is not None else [])
    vmin, vmax = min(all_y), max(all_y)
    span = (vmax - vmin) or 1.0
    step = width / max(n - 1, 1)
    pts = " ".join(
        f"{i*step:.1f},{height - ((v - vmin) / span) * height:.1f}"
        for i, v in enumerate(values)
    )
    last_x = (n - 1) * step
    last_y = height - ((values[-1] - vmin) / span) * height
    # Reference line (drawn behind polyline so the trend sits on top)
    ref_svg = ""
    if reference_value is not None:
        ref_y = height - ((reference_value - vmin) / span) * height
        ref_svg = (
            f'<line x1="0" y1="{ref_y:.1f}" x2="{width}" y2="{ref_y:.1f}" '
            f'stroke="{reference_color}" stroke-width="1" stroke-dasharray="3,3"/>'
        )
    return (
        f'<svg class="body-sparkline" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" preserveAspectRatio="none">'
        f'{ref_svg}'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.5" fill="{color}"/>'
        f'</svg>'
    )
CSS = """
:root {
  /* Multi-tone backgrounds for visual layering (was 2-tone in v0) */
  --bg:           #000810;   /* page background — slightly darker */
  --bg-strip:    #001020;   /* sticky chrome strips (filter / ticker / journey) */
  --card-2:      #001828;   /* box header band + footer band */
  --card:        #002A3F;   /* box body */
  --card-elev:  #002E47;   /* elevated content surface inside body */
  --border:     #003A5C;
  /* Stronger semantic palette (was muted in v0) */
  --blue:       #00B7F5;   /* boosted from #00AEEF */
  --teal:       #00C5B3;   /* boosted from #00AFA0 */
  --amber:      #FFB23D;   /* boosted from #F5A623 */
  --red:        #E63333;   /* boosted from #CC0000 */
  --green:      #3DB677;   /* boosted from #2a9a5a */
  --live:       #4FE583;   /* brighter green specifically for LIVE pill */
  --text:       #E8F4FA;
  --text-2:     #8DC2D9;   /* slightly brighter for body legibility */
  --text-3:     #3A6A7F;
  --sans: 'Plus Jakarta Sans', system-ui, sans-serif;
  --mono: 'DM Mono', 'Menlo', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: var(--bg); color: var(--text); font-family: var(--sans);
             font-size: 12px; line-height: 1.5; }

/* ── Layout shell ──────────────────────────────────────────────────────── */
.holter-app {
  display: flex; flex-direction: column;
  min-height: 100vh;
}
.holter-topnav {
  position: sticky; top: 0; z-index: 100;
  height: 48px;
  background: var(--card-2);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 12px;
  gap: 8px;
}
.holter-main {
  padding: 12px;
}
/* Box 0 dissolved into a sticky full-width horizontal filter strip
   beneath the topnav (page-chrome exception, like topnav/ticker/journey
   row). Filters always reachable; Box 0 sidebar is gone. */
.holter-filter-strip {
  position: sticky; top: 48px; z-index: 99;
  height: 64px;
  background: var(--bg-strip);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  display: flex; align-items: center; gap: 14px;
  padding: 0 16px;
  overflow-x: auto;
}
.holter-filter-section {
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
}
.holter-filter-label {
  font-size: 9px; font-weight: 700; letter-spacing: 1.5px;
  color: var(--text-3); text-transform: uppercase;
}
.holter-filter-sep {
  width: 1px; height: 28px; background: var(--border); flex-shrink: 0;
}
.holter-filter-select {
  background: var(--card-2); border: 1px solid var(--border);
  color: var(--text); font-family: var(--mono); font-size: 11px;
  padding: 4px 10px; border-radius: 2px; cursor: pointer; min-width: 120px;
}
.holter-filter-select.filter-on { border-color: var(--amber); color: var(--amber); }
.holter-filter-radios { display: flex; gap: 10px; }
.holter-filter-radios label {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--text-2); cursor: pointer; white-space: nowrap;
}
.holter-filter-actions { margin-left: auto; display: flex; gap: 6px; }

/* Box 2 hypothesis test bench — dropdown + Run Analysis button in headline */
.hypothesis-controls {
  display: flex; align-items: center; gap: 8px; width: 100%;
}
.hypothesis-select {
  height: 32px;            /* taller than filter strip select — anchor element of the box */
  padding: 4px 10px !important;
}

/* Time picker: button + calendar-style popover with presets + custom range */
.holter-time-section { position: relative; }
.holter-time-btn {
  background: var(--card-2); border: 1px solid var(--border);
  color: var(--text); font-family: var(--mono); font-size: 11px;
  padding: 4px 10px; border-radius: 2px; cursor: pointer;
  display: flex; align-items: center; gap: 6px;
}
.holter-time-btn:hover { border-color: var(--blue); }
.holter-time-btn-caret { color: var(--text-3); font-size: 9px; }
.holter-time-pop {
  position: absolute; top: 100%; left: 0; margin-top: 6px;
  background: var(--card); border: 1px solid var(--border);
  padding: 10px; border-radius: 2px;
  z-index: 200; min-width: 260px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.7);
}
.holter-time-pop[hidden] { display: none; }
.time-presets { display: flex; flex-direction: column; gap: 1px;
                padding-bottom: 8px; border-bottom: 1px solid var(--border);
                margin-bottom: 8px; }
.time-preset {
  background: transparent; border: 0; color: var(--text-2);
  text-align: left; padding: 6px 8px; font-size: 11px; cursor: pointer;
  border-radius: 2px; font-family: var(--sans);
}
.time-preset:hover { background: var(--card-2); color: var(--text); }
.time-preset.active { color: var(--blue); background: var(--card-2); }
.time-custom { display: flex; flex-direction: column; gap: 6px; }
.time-custom-label {
  font-size: 9px; letter-spacing: 1.5px; color: var(--text-3);
  text-transform: uppercase; font-weight: 700;
}
.time-custom-row { display: flex; align-items: center; gap: 6px; }
.time-date {
  background: var(--card-2); border: 1px solid var(--border);
  color: var(--text); padding: 4px 6px; font-family: var(--mono);
  font-size: 11px; border-radius: 2px; flex: 1;
  color-scheme: dark;
}
.time-to-arrow { color: var(--text-3); font-family: var(--mono); }
.time-apply {
  background: var(--blue); color: var(--bg); border: 0;
  padding: 6px 12px; border-radius: 2px; font-family: var(--mono);
  font-size: 10px; font-weight: 700; cursor: pointer; letter-spacing: 0.5px;
  margin-top: 4px;
}
.holter-filter-btn {
  background: var(--blue); color: var(--bg);
  border: 0; padding: 6px 14px; border-radius: 2px;
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  letter-spacing: 0.5px; cursor: pointer;
}
.holter-filter-btn.secondary {
  background: transparent; color: var(--text-2); border: 1px solid var(--border);
}

/* ── Top nav ───────────────────────────────────────────────────────────── */
.brand-logo {
  font-size: 13px; font-weight: 800; letter-spacing: 2.5px;
  color: var(--blue); text-transform: uppercase;
}
.topnav-spacer { flex: 1; }
.topnav-icon, .topnav-avatar {
  font-family: var(--mono); font-size: 14px; color: var(--text-3);
  background: transparent; border: 0; cursor: pointer;
  padding: 4px 8px; border-radius: 4px;
}
.topnav-icon:hover, .topnav-avatar:hover { color: var(--text); background: var(--card); }
.topnav-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--amber); color: var(--bg); font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center; font-size: 10px;
}
.topnav-select {
  background: var(--card-2); border: 1px solid var(--border);
  color: var(--blue); font-family: var(--mono); font-size: 11px;
  padding: 4px 10px; border-radius: 2px; cursor: pointer;
}
.topnav-select:disabled { color: var(--text-3); cursor: not-allowed; }
.topnav-select.filter-on { border-color: var(--amber); color: var(--amber); }
.topnav-reset {
  background: transparent; border: 1px solid var(--amber); color: var(--amber);
  font-family: var(--mono); font-size: 10px; padding: 3px 10px;
  border-radius: 2px; cursor: pointer;
}

/* ── Sidebar (Box 0) ───────────────────────────────────────────────────── */
.sidebar-inner { padding: 14px 12px; display: flex; flex-direction: column; gap: 16px; }
.sidebar-section-label {
  font-size: 9px; font-weight: 700; letter-spacing: 1.2px;
  color: var(--text-3); text-transform: uppercase;
  margin-bottom: 6px;
}
.sidebar-check {
  display: flex; align-items: center; gap: 6px; padding: 4px 0;
  font-size: 11px; color: var(--text-2); cursor: pointer;
}
.sidebar-check input { cursor: pointer; }
.sidebar-check-count {
  margin-left: auto; font-family: var(--mono); font-size: 9px; color: var(--text-3);
}
.sidebar-radio { display: flex; flex-direction: column; gap: 3px; }
.sidebar-radio label {
  display: flex; align-items: center; gap: 6px; cursor: pointer;
  font-size: 11px; color: var(--text-2);
}
.sidebar-select {
  width: 100%; background: var(--card-2); border: 1px solid var(--border);
  color: var(--text); font-family: var(--mono); font-size: 11px;
  padding: 4px 6px; border-radius: 2px;
}
.sidebar-actions { display: flex; gap: 6px; margin-top: 4px; }
.sidebar-btn {
  flex: 1; background: var(--blue); color: var(--bg);
  border: 0; padding: 6px 10px; border-radius: 2px;
  font-family: var(--mono); font-size: 10px; font-weight: 700; cursor: pointer;
  letter-spacing: 0.5px;
}
.sidebar-btn.secondary { background: transparent; color: var(--text-2); border: 1px solid var(--border); }

/* ── Universal box (THE locked discipline) ─────────────────────────────── */
.holter-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
@media (max-width: 1100px) {
  .holter-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .holter-row { grid-template-columns: 1fr; }
}
.holter-box {
  width: 100%;                              /* responsive — fills 1fr grid cell */
  height: clamp(520px, 78vh, 731px);        /* responsive — scales with viewport height */
  background: var(--card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);     /* default; per-box accent overrides */
  display: grid;
  grid-template-rows: 48px 96px 1fr 48px;   /* header + headline + body(1fr) + footer */
  overflow: visible;                        /* HOL-16: tooltips escape box edge.
                                              Each layer clips its OWN content. */
  transition: border-left-color 0.2s;
}
.box-header {
  background: var(--card-2);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  padding: 0 14px;
  position: relative;
}
.box-header::before {
  /* subtle bottom underline accent in box-accent colour, set inline */
  content: ""; position: absolute; left: 0; right: 0; bottom: -1px;
  height: 2px; background: var(--box-accent, transparent);
  opacity: 0.6;
}
.box-header-title {
  font-size: 12px; font-weight: 800; letter-spacing: 1.8px;
  color: var(--blue); text-transform: uppercase;
  text-shadow: 0 0 12px rgba(0,183,245,0.25);
}
.box-header-sub {
  margin-left: auto;
  font-size: 10px; color: var(--text-3); font-family: var(--mono);
}
.box-headline {
  padding: 12px 14px;
  border-bottom: 1px solid var(--card-2);
  display: flex; align-items: center;
  overflow: hidden;
}
.box-body {
  padding: 14px;
  overflow: visible;                        /* HOL-16: hover tooltips on chips escape body */
  display: flex; flex-direction: column; gap: 10px;
}
.box-footer {
  border-top: 1px solid var(--card-2);
  background: var(--card-2);
  padding: 0 14px;
  display: flex; flex-direction: column; justify-content: center; gap: 2px;
}
.box-footer-pills { display: flex; align-items: center; gap: 8px;
                    font-family: var(--mono); font-size: 9px; }
.box-footer-pill { border: 1px solid var(--border); border-radius: 2px;
                   padding: 1px 6px; color: var(--text-2); }
.box-footer-live {
  background: var(--live); color: var(--bg); padding: 1px 7px;
  border-radius: 2px; font-weight: 700; letter-spacing: 0.5px;
  animation: live-pulse 2.4s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgba(79,229,131,0.6);
}
@keyframes live-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(79,229,131,0.5);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(79,229,131,0);
    transform: scale(1.04);
  }
}
.box-footer-note { font-size: 9px; color: var(--text-3);
                   white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ── Headline shape vocabulary ─────────────────────────────────────────── */
.headline-stat { display: flex; flex-direction: column; gap: 4px; width: 100%; }
.headline-stat-row1 { display: flex; align-items: baseline; gap: 8px; }
.headline-stat-label { font-size: 9px; font-weight: 700; letter-spacing: 1.5px;
                       color: var(--text-3); text-transform: uppercase; }
.headline-stat-value {
  font-size: 32px; font-weight: 800; color: var(--text);
  font-family: var(--mono); line-height: 1;
  text-shadow: 0 0 18px rgba(0,183,245,0.2);
}
.headline-stat-delta {
  font-size: 11px; color: var(--green); font-weight: 600;
  font-family: var(--mono);
}
.headline-stat-traj {
  font-size: 11px; color: var(--green); margin-left: auto; font-weight: 700;
  letter-spacing: 0.5px;
}
.headline-stat-meta { font-size: 9px; color: var(--text-3); font-family: var(--mono);
                      display: flex; gap: 12px; }
.headline-stat-progress { height: 3px; background: var(--card-2);
                          border-radius: 1px; overflow: hidden; }
.headline-stat-progress-fill { height: 100%; background: var(--blue); }

.headline-chips { display: flex; gap: 10px; width: 100%; align-items: center; }
.headline-chip {
  display: inline-flex; flex-direction: column; gap: 2px;
  padding: 6px 10px; border-radius: 2px;
  border: 1px solid var(--border); background: var(--card-2);
  min-width: 80px;
}
.headline-chip-value {
  font-family: var(--mono); font-size: 26px; font-weight: 800;
  text-shadow: 0 0 12px currentColor;
}
.headline-chip-label { font-size: 9px; letter-spacing: 1px; color: var(--text-3);
                       text-transform: uppercase; }

.headline-tier { display: flex; align-items: center; gap: 10px; width: 100%; }
.headline-tier-badge {
  display: inline-block; padding: 7px 14px;
  font-family: var(--mono); font-weight: 800; font-size: 14px;
  letter-spacing: 0.5px; background: var(--card-2);
  border: 1px solid; border-radius: 2px;
  text-shadow: 0 0 10px currentColor;
  box-shadow: 0 0 16px -8px currentColor;
}
.headline-tier-context { font-size: 11px; color: var(--text-2); line-height: 1.4;
                         display: -webkit-box; -webkit-line-clamp: 3;
                         -webkit-box-orient: vertical; overflow: hidden; }

/* ── Body shape vocabulary ─────────────────────────────────────────────── */
.body-evidence-card {
  border-left: 3px solid var(--blue); padding: 10px 12px;
  background: var(--card-elev);
  box-shadow: -8px 0 16px -10px var(--blue);
}
.body-evidence-quote {
  font-size: 11px; color: var(--text); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: help;
  border-bottom: 1px dotted transparent;
}
.body-evidence-quote[data-tooltip]:hover { border-bottom-color: var(--text-3); }
.body-evidence-attr {
  margin-top: 4px;
  font-size: 9px; font-family: var(--mono); color: var(--text-3);
  letter-spacing: 0.5px;
}
.body-kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.body-kpi-tile { background: var(--card-2); border: 1px solid var(--border);
                 border-top-width: 3px; padding: 10px;
                 display: flex; flex-direction: column; gap: 4px; }
.body-kpi-value { font-family: var(--mono); font-size: 20px; font-weight: 700; }
.body-kpi-label { font-size: 9px; letter-spacing: 1px; color: var(--text-3); text-transform: uppercase; }
.body-kpi-sub { font-size: 10px; color: var(--text-2); }

.body-chip-strip { display: flex; flex-wrap: wrap; gap: 8px; }
.body-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 8px; border-radius: 2px;
  background: var(--card-2); border: 1px solid var(--border);
  font-size: 10px;
}
.body-chip-dot { width: 8px; height: 8px; border-radius: 50%; }
.body-chip-count { font-family: var(--mono); font-weight: 700; color: var(--text); margin-left: 4px; }

.body-bars { display: flex; flex-direction: column; gap: 6px; }
.body-bar-row { display: flex; align-items: center; gap: 8px; font-size: 10px; }
.body-bar-label { width: 130px; color: var(--text-2);
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.body-bar-track { flex: 1; height: 14px; background: var(--card-2); border-radius: 1px; overflow: hidden; }
.body-bar-fill { height: 100%; }
.body-bar-value { width: 40px; text-align: right; color: var(--text); font-family: var(--mono); }

.body-line { font-size: 11px; color: var(--text-2);
             display: flex; align-items: center; gap: 8px;
             overflow: hidden; text-overflow: ellipsis; }
.body-line-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  box-shadow: 0 0 8px currentColor;
}
.body-line-dot[style*="background"] {
  /* the dot's inline background sets currentColor for the shadow */
}

/* Prominent action callout — sits between KPI tiles and ancillary lines */
.body-action {
  background: var(--card-elev);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);  /* overridden inline per tier */
  padding: 8px 12px;
  font-size: 12px; color: var(--text);
  line-height: 1.5;
}

/* PRIMARY action block — Box 1 dominant focal point (HOL-13).
   Bigger / louder / tier-railed than .body-action. */
.body-action-primary {
  background: var(--card-elev);
  border: 1px solid var(--border);
  border-left: 6px solid var(--border);  /* overridden inline per tier */
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 6px;
}
.body-action-primary-label {
  font-size: 9px; font-weight: 800; letter-spacing: 1.8px;
  text-transform: uppercase;
}
.body-action-primary-text {
  font-size: 13px; color: var(--text);
  line-height: 1.5;
}

/* Decision-quality strip — Kozyrkov separation: keep quality signals
   visually distinct from decision-INPUT signals (Diagnosis/Value/Risk). */
.body-quality {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 0;
  border-top: 1px dashed var(--border);
  font-size: 10px; color: var(--text-3);
}
.body-quality-label {
  font-weight: 800; letter-spacing: 1.4px;
  color: var(--text-3); text-transform: uppercase;
  flex-shrink: 0;
}
.body-quality-items { display: flex; gap: 14px; color: var(--text-2);
                      font-family: var(--mono); }

/* Sparkline container — sits inside body, full-width SVG */
.body-sparkline { display: block; }

/* Single highlighted supporting KPI block (HOL-15 — Box 3 simplification).
   One bold stat block replaces the 3-tile clutter. */
.body-primary-kpi {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-top-width: 3px;
  padding: 12px 14px;
  display: flex; align-items: baseline; gap: 14px;
}
.body-primary-kpi-value {
  font-family: var(--mono);
  font-size: 28px; font-weight: 700; line-height: 1;
}
.body-primary-kpi-meta {
  display: flex; flex-direction: column; gap: 2px;
}
.body-primary-kpi-label {
  font-size: 9px; letter-spacing: 1.2px;
  color: var(--text-3); text-transform: uppercase;
  font-weight: 800;
}
.body-primary-kpi-sub {
  font-size: 10px; color: var(--text-2);
}

/* Progressive-disclosure block (HOL-15) — native <details>, no JS. */
.body-disclosure {
  border-top: 1px dashed var(--border);
  padding-top: 4px;
}
.body-disclosure-summary {
  font-size: 9px; color: var(--text-3);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 1.4px;
  padding: 4px 0;
  list-style: none;
  font-weight: 800;
}
.body-disclosure-summary::-webkit-details-marker { display: none; }
.body-disclosure-summary::after { content: " ▾"; color: var(--text-3); }
details[open] > .body-disclosure-summary::after { content: " ▴"; }
.body-disclosure-content {
  padding: 6px 0 2px;
  font-size: 10px; color: var(--text-2);
  display: flex; flex-direction: column; gap: 4px;
  font-family: var(--mono);
}

.body-table { width: 100%; border-collapse: collapse; font-size: 10px; }
.body-table th { text-align: left; padding: 4px 6px; font-size: 9px;
                 color: var(--text-3); letter-spacing: 0.5px;
                 border-bottom: 1px solid var(--border); text-transform: uppercase; }
.body-table td { padding: 4px 6px; color: var(--text-2);
                 border-bottom: 1px solid var(--card-2); }
.body-table tr:last-child td { border-bottom: 0; }

/* ── Pure-CSS hover tooltip ────────────────────────────────────────────── */
[data-tooltip] { position: relative; }
[data-tooltip]:hover::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 100%;
  left: 50%;                              /* HOL-16: center-anchor */
  transform: translateX(-50%);
  margin-bottom: 6px;
  background: var(--card-2); color: var(--text);
  border: 1px solid var(--blue);
  padding: 8px 10px; border-radius: 2px;
  font-size: 11px; line-height: 1.5;
  white-space: normal;
  width: max-content;
  max-width: 320px;                       /* HOL-16: was 480px — fits adjacent boxes */
  z-index: 200;
  box-shadow: 0 4px 12px rgba(0,0,0,0.6);
  pointer-events: none;                   /* avoid hover-leave jitter */
}
/* HOL-16: opt-in to "tooltip below" for triggers with limited space above
   (e.g., severity filter labels right under the topnav). Apply via
   class="tooltip-below". */
[data-tooltip].tooltip-below:hover::after {
  bottom: auto;
  top: 100%;
  margin-bottom: 0;
  margin-top: 6px;
}

/* HOL-16 Part B — Persistent glossary affordance.
   Top-nav <details> drops down a scrollable panel listing every defined
   token in STATUS_GLOSSARY, grouped by dimension. */
.topnav-glossary { position: relative; }
.topnav-glossary > summary.topnav-glossary-trigger {
  list-style: none;
  cursor: pointer;
  font-family: var(--mono);
  font-size: 13px; font-weight: 700;
}
.topnav-glossary > summary::-webkit-details-marker { display: none; }
.topnav-glossary-panel {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: var(--card-2);
  border: 1px solid var(--blue);
  width: 520px;
  max-height: 72vh;
  overflow-y: auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.7);
  z-index: 220;
  padding: 14px 16px;
}
.topnav-glossary-panel-header {
  font-size: 10px; font-weight: 800;
  letter-spacing: 1.8px;
  color: var(--blue);
  text-transform: uppercase;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.glossary-section { margin-bottom: 14px; }
.glossary-section:last-child { margin-bottom: 0; }
.glossary-section-label {
  font-size: 9px; font-weight: 800;
  letter-spacing: 1.4px;
  color: var(--text-3);
  text-transform: uppercase;
  padding-bottom: 4px;
  margin-bottom: 6px;
  border-bottom: 1px dashed var(--border);
}
.glossary-item {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 12px;
  padding: 4px 0;
  font-size: 10px;
}
.glossary-token {
  font-family: var(--mono);
  font-weight: 700;
  color: var(--text);
  word-break: break-word;
}
.glossary-def {
  color: var(--text-2);
  line-height: 1.45;
}

/* Filtered-out box visibility */
.holter-box.filtered-out { display: none; }

/* ── Page chrome strips — ticker + journey row (documented exceptions) ── */
/* Not boxes — full-width horizontal strips between row sections. Same
   role as topnav/footer: page chrome that lives outside the box grid. */

.holter-ticker {
  overflow: hidden; background: var(--bg-strip);
  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
.holter-ticker-track { overflow: hidden; white-space: nowrap; }
.holter-ticker-inner {
  display: inline-flex; align-items: center;
  padding: 10px 0;
  animation: holter-ticker-scroll 120s linear infinite;
}
.holter-ticker-inner:hover { animation-play-state: paused; }
@keyframes holter-ticker-scroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
.holter-ticker-item {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 0 20px;
}
.holter-ticker-cell {
  font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
  font-family: var(--mono);
}
.holter-ticker-sig {
  font-size: 11px; color: var(--text-2);
}
.holter-ticker-bar {
  width: 40px; height: 6px; background: var(--card); border-radius: 1px;
  overflow: hidden;
}
.holter-ticker-bar-fill { height: 100%; }
.holter-ticker-sha {
  font-family: var(--mono); font-size: 9px; color: var(--text-3);
}
.holter-ticker-sep { color: var(--border); padding: 0 4px; font-size: 16px; }

.holter-journey-strip {
  margin-bottom: 12px;
}
.holter-journey-header {
  display: flex; align-items: baseline; gap: 12px;
  padding: 0 4px 8px;
}
.holter-journey-title {
  font-size: 11px; font-weight: 800; letter-spacing: 1.5px;
  color: var(--text-2); text-transform: uppercase;
}
.holter-journey-sub {
  font-size: 10px; color: var(--text-3); font-family: var(--mono);
}
.holter-journey-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
}
.holter-journey-cell {
  background: var(--bg-strip);
  padding: 12px 16px;
  border-top: 3px solid;
  display: flex; flex-direction: column; gap: 4px;
}
.holter-journey-cell-name {
  font-size: 12px; font-weight: 700; color: var(--text-2);
  letter-spacing: 0.5px;
}
.holter-journey-cell-score {
  font-size: 32px; font-weight: 800; font-family: var(--mono);
  color: var(--text);
  line-height: 1;
  text-shadow: 0 0 12px rgba(0,183,245,0.25);
}
.holter-journey-cell-status {
  font-size: 10px; font-weight: 700; letter-spacing: 1px;
}
.holter-journey-cell-submeta {
  font-size: 9px; color: var(--text-3); font-family: var(--mono);
}

/* ── Multi-signal provenance strip (pulse-multisignal-identity) ──────────── */
/* Shows which signal classes the engine fuses into a finding; `pending`
   tokens are dashed/dim and name their gating ticket on hover. */
.signal-strip {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
}
.signal-strip-label {
  font-family: var(--mono); font-size: 8px; font-weight: 800;
  letter-spacing: 1.4px; text-transform: uppercase;
  color: var(--text-3); margin-right: 2px;
}
.signal-token {
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--mono); font-size: 9px; font-weight: 700;
  letter-spacing: 0.5px;
  padding: 2px 7px; border: 1px solid var(--border); border-radius: 2px;
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
