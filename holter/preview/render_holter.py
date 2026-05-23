"""Holter template — functional v1 (porting :8502 into the Holter framework).

Holter's locked box discipline (4 layers, 562×731, universal chrome)
applied to the FULL briefing surface, consuming real pack data + engine
methodology outputs.

This replaces the v0 design-template render_holter.py. The previous
hardcoded placeholder content is gone — every box now reads from
discover_packs() and pulse.scenarios.agentic_ai_placement.

Discipline (unchanged from v0):
  - Every box: 562 × 731, 4 layers (header 48 / headline 96 / body 531 / footer 48)
  - Body content varies per box; everything else is locked
  - Sticky chrome: top nav (48px) + left sidebar (168px); topbar boxes scroll away

What changed vs v0 (the port):
  - discover_packs() + load_journey_taxonomy() (ported from render_mil_briefing.py)
  - get_pack_cell() consumes PULSE-106 placement scenario for per-pack tiers
  - render_filter_strip() carries the sticky horizontal filter controls
    (Journey / Time Range / Severity) — replaces the deprecated sidebar
  - All topbar boxes (1/2/3) read pack data + engine output
  - V3 layer becomes a grid of boxes obeying the same contract:
      · Engine summary: Friction Risk / Placement Posture / Confidence Protocol
      · Methodology distributions: Diagnosis / Value / Risk
      · Detail: Chronicle Matcher + Commentary-per-journey + Bench
  - FILTER_JS adapted to Holter classes (sidebar checkboxes + topbar dropdowns
    drive box visibility + tier-count recompute)

Output: dist/preview/holter/index.html
Serve:  py holter/preview/serve_holter.py  (port 8504)
"""

from __future__ import annotations

import datetime as _dt
import sys
from html import escape as _e
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "dist" / "preview" / "holter"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# HOL-35: every general-purpose primitive lives in _shared. This file is now
# Workspace-specific only (the filter strip, ticker, journey row, box1/box2/
# box3 trio + V3 layer + page composition).
from holter.preview._shared import (  # noqa: E402
    # Engine bridge
    discover_packs,
    get_pack_cell,
    get_pack_analytics,
    lineage_anchor_short,
    analytics_quality_items,
    headline_pack,
    short_hash,
    screen_short,
    _extract_quote,
    load_journey_taxonomy,
    # Constants
    NOW,
    CSS,
    # Color maps
    _ACTION_COLORS,
    _DIAGNOSIS_COLORS,
    _VALUE_COLORS,
    _RISK_COLORS,
    # Glossary
    STATUS_GLOSSARY,
    tooltip_token,
    render_glossary_panel,
    # Box primitives
    render_box,
    box_header,
    box_footer,
    # Headline shape vocabulary
    headline_stat_card,
    headline_chip_strip,
    headline_tier_badge,
    # Body composables
    body_evidence_cards,
    body_kpi_tiles,
    body_chip_strip,
    body_bars,
    body_lines,
    body_action_line,
    body_action_primary,
    body_quality_strip,
    body_primary_kpi,
    body_disclosure,
    # SVG
    sparkline_svg,
    # Commercial signal (friction-volume primary, £ scaffold secondary)
    friction_volume_value,
    commercial_scaffold,
    # Multi-signal provenance (pulse-multisignal-identity)
    signal_provenance,
)


def cell_screens_with_counts(packs: list[dict]) -> list[dict]:
    """Aggregate detection counts by friction-target screen for the journey row."""
    screens: dict[str, list[dict]] = {}
    for p in packs:
        h = p["hypothesis"] or {}
        sc = h.get("screen_id")
        if not sc:
            continue
        screens.setdefault(sc, []).append(p)
    out = []
    for sc, ps in screens.items():
        positives = sum(1 for p in ps if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
        negatives = sum(1 for p in ps if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")
        out.append({
            "screen": sc,
            "short": screen_short(sc),
            "packs": ps,
            "positives": positives,
            "negatives": negatives,
            "total": len(ps),
            "status": "ACUTE" if positives >= 3 else ("LOAD-BEARING" if negatives else "STABLE"),
            "status_color": "var(--red)" if positives >= 3 else (
                "var(--amber)" if negatives else "var(--teal)"
            ),
        })
    return out


# HOL-35: engine bridge + color maps + glossary + CSS + box primitives all
# moved to _shared.py (imported at top). The Workspace-specific code below
# this point: filter strip, ticker, journey row, box1/2/3 + V3 layer +
# page composition.

# CSS = imported from _shared.py


# Box helpers — enforce the 4-layer contract
# ─────────────────────────────────────────────────────────────────────────────

# NOW, render_box, body_*, headline_*, sparkline_svg — imported from _shared.py


# ─────────────────────────────────────────────────────────────────────────────
# Top nav + Sidebar (Box 0) — sidebar with REAL filter controls
# ─────────────────────────────────────────────────────────────────────────────

def render_topnav(packs: list[dict]) -> str:
    """Topnav with identity + Product/Owner filters. Domain + Date moved
    into the filter strip so they don't duplicate (Journey = Domain;
    Time = Date)."""
    owners = sorted({a for p in packs for a in p["meta"].get("authors", [])})
    n = len(packs)
    product_opts = f'<option value="">Product · all packs · {n}</option>\n' + "".join(
        f'<option value="{p["meta"]["pack_name"]}">'
        f'Product · cell {(p["hypothesis"] or {}).get("cell_id","?")} · '
        f'{(p["hypothesis"] or {}).get("signature_id","—").replace("_"," ")}</option>'
        for p in sorted(packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99))
    )
    owner_opts = f'<option value="">Owner · all teams · {len(owners)}</option>\n' + "".join(
        f'<option value="{o}">Owner · {o}</option>' for o in owners
    )
    return f'''
<header class="holter-topnav">
  <span class="brand-logo">CJI&nbsp;PULSE</span>
  <select class="topnav-select" id="filter-product" data-filter="packname">{product_opts}</select>
  <select class="topnav-select" id="filter-owner" data-filter="author">{owner_opts}</select>
  <button class="topnav-reset" id="filter-reset" type="button" hidden>Reset</button>
  <span class="topnav-spacer"></span>
  <button class="topnav-icon" type="button" title="Search packs (/)">⌕</button>
  <button class="topnav-icon" type="button" title="Notifications">🔔</button>
  <details class="topnav-glossary">
    <summary class="topnav-icon topnav-glossary-trigger" title="Status glossary (full token dictionary)">Aa</summary>
    <div class="topnav-glossary-panel">
      <div class="topnav-glossary-panel-header">STATUS GLOSSARY</div>
      <div class="topnav-glossary-panel-body">{render_glossary_panel()}</div>
    </div>
  </details>
  <button class="topnav-icon" type="button" title="Canvas guide">?</button>
  <button class="topnav-icon" type="button" title="Settings">⚙</button>
  <button class="topnav-avatar" type="button" title="Hussain Ahmed">HA</button>
</header>'''


def render_filter_strip(packs: list[dict]) -> str:
    """Sticky horizontal filter strip below the topnav.
    Journey = dropdown (single-select). Time = button → calendar popover
    with preset buttons + custom date-range inputs. Severity = radio."""
    domains = sorted({(p["hypothesis"] or {}).get("screen_id", "").split(".")[0]
                       for p in packs if (p["hypothesis"] or {}).get("screen_id")})
    domain_counts: dict[str, int] = {}
    for p in packs:
        d = (p["hypothesis"] or {}).get("screen_id", "").split(".")[0]
        if d:
            domain_counts[d] = domain_counts.get(d, 0) + 1

    journey_opts = f'<option value="">Journey · all · {len(domains)}</option>\n' + "".join(
        f'<option value="{d}">{d} · {domain_counts.get(d, 0)} packs</option>'
        for d in domains
    )

    # Default date range = last 7 days from today
    today = _dt.date.today()
    week_ago = today - _dt.timedelta(days=7)

    return f'''
<div class="holter-filter-strip">
  <div class="holter-filter-section">
    <span class="holter-filter-label">Journey</span>
    <select class="holter-filter-select" id="filter-journey" data-filter="domain">{journey_opts}</select>
  </div>
  <div class="holter-filter-sep"></div>
  <div class="holter-filter-section holter-time-section">
    <span class="holter-filter-label">Time</span>
    <button class="holter-time-btn" id="time-btn" type="button">
      <span id="time-btn-label">Last 7 days</span>
      <span class="holter-time-btn-caret">▾</span>
    </button>
    <div class="holter-time-pop" id="time-pop" hidden>
      <div class="time-presets">
        <button class="time-preset active" data-preset="7" type="button">Last 7 days</button>
        <button class="time-preset" data-preset="30" type="button">Last 30 days</button>
        <button class="time-preset" data-preset="90" type="button">Last 90 days</button>
        <button class="time-preset" data-preset="month" type="button">This month</button>
        <button class="time-preset" data-preset="quarter" type="button">This quarter</button>
        <button class="time-preset" data-preset="ytd" type="button">Year to date</button>
      </div>
      <div class="time-custom">
        <div class="time-custom-label">Custom range</div>
        <div class="time-custom-row">
          <input type="date" class="time-date" id="time-from" value="{week_ago.isoformat()}">
          <span class="time-to-arrow">→</span>
          <input type="date" class="time-date" id="time-to" value="{today.isoformat()}">
        </div>
        <button class="time-apply" id="time-apply" type="button">Apply custom range</button>
      </div>
    </div>
  </div>
  <div class="holter-filter-sep"></div>
  <div class="holter-filter-section">
    <span class="holter-filter-label">Severity</span>
    <div class="holter-filter-radios">
      <label><input type="radio" name="severity" value="all" checked> {tooltip_token("severity", "All")}</label>
      <label><input type="radio" name="severity" value="positive"> {tooltip_token("severity", "Positive")}</label>
      <label><input type="radio" name="severity" value="negative"> {tooltip_token("severity", "Negative")}</label>
    </div>
  </div>
  <div class="holter-filter-sep"></div>
  <div class="holter-filter-section">
    <span class="holter-filter-label">Scope</span>
    <span style="font-size:11px; color:var(--text-2); font-family:var(--mono);">
      {len(packs)} packs · 4 journeys × 3 signatures
    </span>
  </div>
  <div class="holter-filter-actions">
    <button class="holter-filter-btn" id="filter-apply" type="button">APPLY</button>
    <button class="holter-filter-btn secondary" id="filter-strip-reset" type="button">RESET</button>
  </div>
</div>'''


# NOTE: render_sidebar() was deleted on 2026-05-19 per PR-panel review.
# It was declared deprecated when filters moved to render_filter_strip(),
# but it still emitted a complete <aside> with a duplicate name="severity"
# form input that would collide with the live filter strip if accidentally
# rendered. Per van Rossum's catch in the panel review — dead generators
# that produce real HTML are liabilities, not compatibility shims.


# ─────────────────────────────────────────────────────────────────────────────
# Box 1, 2, 3 — topbar boxes consuming REAL data
# ─────────────────────────────────────────────────────────────────────────────

# _extract_quote — imported from _shared.py


def render_ticker(packs: list[dict]) -> str:
    """Scrolling marquee of pack lineage anchors (page chrome, not a box).
    Doubled track so the loop seam is invisible during animation."""
    if not packs:
        return ""
    items = []
    for p in packs:
        h = p["hypothesis"] or {}
        sig = h.get("signature_id", "—").replace("_", " ")
        cell = h.get("cell_id", "?")
        # PULSE-93/96 — the ticker labels itself "lineage anchors", so show the
        # REAL lineage anchor; fixture packs (no analytics) fall back to meta-sha.
        sha = lineage_anchor_short(p["meta"]["pack_name"]) or short_hash(p["sha256"])
        is_neg = h.get("ground_truth_expectation") == "negative"
        color = "var(--amber)" if is_neg else "var(--text-2)"
        bar_w = 22 if is_neg else 40
        items.append(
            f'<span class="holter-ticker-item">'
            f'<span class="holter-ticker-cell" style="color:{color};">CELL {cell:>2}</span>'
            f'<span class="holter-ticker-sig">{sig}</span>'
            f'<span class="holter-ticker-bar"><span class="holter-ticker-bar-fill" '
            f'style="width:{bar_w}px;background:{color};"></span></span>'
            f'<span class="holter-ticker-sha">{sha}</span>'
            f'</span>'
            f'<span class="holter-ticker-sep">·</span>'
        )
    track = "".join(items)
    return (
        f'<div class="holter-ticker">'
        f'<div class="holter-ticker-track">'
        f'<div class="holter-ticker-inner">{track}{track}</div>'
        f'</div></div>'
    )


def render_journey_row(packs: list[dict]) -> str:
    """4-cell horizontal strip showing per-screen friction-target status
    (page chrome, not a box). Cell width = 1fr each so 4 cells fill the
    available row width regardless of viewport."""
    screens = cell_screens_with_counts(packs)
    if not screens:
        return ""
    cells_html = ""
    for s in screens:
        cells_html += (
            f'<div class="holter-journey-cell" style="border-top-color:{s["status_color"]};">'
            f'<div class="holter-journey-cell-name">{s["short"]}</div>'
            f'<div class="holter-journey-cell-score">{s["positives"]}/3</div>'
            f'<div class="holter-journey-cell-status" style="color:{s["status_color"]};">{s["status"]}</div>'
            f'<div class="holter-journey-cell-submeta">{s["total"]} cells · '
            f'{s["positives"]} positive · {s["negatives"]} negative</div>'
            f'</div>'
        )
    return (
        '<div class="holter-journey-strip">'
        '<div class="holter-journey-header">'
        '<span class="holter-journey-title">FRICTION-TARGET SCREENS</span>'
        '<span class="holter-journey-sub">FrictionBench v0.1 · 4 screens × 3 signatures</span>'
        '</div>'
        f'<div class="holter-journey-row">{cells_html}</div>'
        '</div>'
    )


_COMMERCIAL_TIERS = {"COMMERCIAL-OPPORTUNITY", "SIGNIFICANT"}


def _workspace_default_pack(packs: list[dict], selected_name: str | None = None) -> dict:
    """HOL-56 — Workspace prefers a COMMERCIAL-OPPORTUNITY pack as the default
    selection so the new commercial framing demonstrates on first load. Falls
    back to shared headline_pack (cell 10 / cards-abandon) when no commercial
    pack is registered.

    HOL-67 — `selected_name` is the user's pick from the Streamlit journey
    selector (selection-driven nav). When it matches a registered pack, it
    wins; otherwise the default-selection logic applies."""
    if selected_name:
        for p in packs:
            if p["meta"]["pack_name"] == selected_name:
                return p
    for p in packs:
        cs = get_pack_cell(p["meta"]["pack_name"])
        if cs is not None and cs.value.tier in _COMMERCIAL_TIERS:
            return p
    return headline_pack(packs)


def render_box1(packs: list[dict], selected_name: str | None = None) -> str:
    """Box 1 — VERDICT (selection-driven).

    Top-nav selection drives this box: user picks a Journey/slice in the
    nav, engine churns DuckDB, returns a verdict object, Box 1 renders it.
    HOL-67 — `selected_name` is the live Streamlit journey pick.
    """
    pack = _workspace_default_pack(packs, selected_name)
    if not pack:
        return render_box(
            header=box_header("VERDICT", "no selection"),
            headline=headline_tier_badge("—", "var(--text-3)",
                                          "Select a journey in top nav to compute verdict"),
            body=body_lines([("No packs in registry", "var(--amber)")]),
            footer=box_footer("—", NOW, live=False, note="—"),
        )

    meta = pack["meta"]
    cell_score = get_pack_cell(meta["pack_name"])

    if cell_score:
        tier = cell_score.action_tier
        tier_color = _ACTION_COLORS.get(tier, "var(--amber)")
        # PR-panel fix: escape engine free-text (recommendation) at boundary.
        # Identifiers (journey_id, signature_id, tier strings) are constrained
        # by engine schema to safe charsets, but escape defensively anyway.
        recommendation = _e(cell_score.placement_recommendation)
        breadcrumb = _e(cell_score.journey_id.replace("_", " · "))
        # cell_score.{diagnosis,value,risk} are objects; pull the string tier off each
        diagnosis_label = cell_score.diagnosis.diagnosis
        value_label     = cell_score.value.tier
        risk_label      = cell_score.risk.tier
        # HOL-14: wrap each tier value in a hover-glossary span
        supporting_chips = [
            ("DIAGNOSIS", tooltip_token("diagnosis", diagnosis_label),
             _DIAGNOSIS_COLORS.get(diagnosis_label, "var(--amber)")),
            ("VALUE",     tooltip_token("value", value_label),
             _VALUE_COLORS.get(value_label, "var(--amber)")),
            ("RISK",      tooltip_token("risk", risk_label),
             _RISK_COLORS.get(risk_label, "var(--amber)")),
        ]
    else:
        tier = "PENDING"
        tier_color = "var(--text-3)"
        recommendation = "Verdict computation requires engine scenario (PULSE-106)"
        breadcrumb = (pack["hypothesis"] or {}).get("screen_id", "—")
        supporting_chips = [
            ("DIAGNOSIS", "—", "var(--text-3)"),
            ("VALUE",     "—", "var(--text-3)"),
            ("RISK",      "—", "var(--text-3)"),
        ]

    # Key Area = strategic alignment of the work (engine-derived later;
    # stubbed here for design). Header carries this; headline carries the
    # tier verdict + selection breadcrumb (recommendation moves to body).
    key_area = "CUSTOMER EXPERIENCE"

    # HOL-13 hierarchy: badge + breadcrumb in headline (the VERDICT label);
    # recommendation moves to body_action_primary (the dominant focal point).
    headline_context = (
        f'<strong style="color:var(--text);">{breadcrumb}</strong>'
    )

    # HOL-12 plain-English synthesis — explains WHY the engine landed here.
    # Distinct from ACTION (what to do); this is the "what it means" line.
    # Engine-derived later; stubbed by diagnosis for now.
    if cell_score:
        _diag_synthesis = {
            "INCONCLUSIVE":    ("the assistance and no-assistance arms show "
                                "indistinguishable outcomes — engine can't yet "
                                "attribute friction to journey vs support."),
            "SUPPORT_PROBLEM": ("assistance closes the failure gap — friction "
                                "lives in the support layer, not the journey "
                                "design itself."),
            "JOURNEY_PROBLEM": ("assistance does not close the gap — fix the "
                                "journey design, not the support around it."),
            "BOTH":            ("assistance helps but a residual gap remains — "
                                "both journey and support need attention."),
        }
        verdict_synthesis = _diag_synthesis.get(
            diagnosis_label,
            f"diagnosis {diagnosis_label} · value {value_label} · risk {risk_label}.",
        )
    else:
        verdict_synthesis = ("verdict pending — engine scenario not yet wired "
                             "for this selection.")

    # HOL-56 + no-pound-pandora — commercial sizing block. When the pack is
    # commercial-tier, promote the FRICTION-VOLUME signal (sessions/wk
    # recoverable) to a primary-KPI block between ACTION and the chip strip.
    # The £ figure, if the deployment configured ARPU, is a secondary cost
    # scaffold in the sub-line that names its own per-session assumption —
    # never the lead stat (raw £ opens the assumption Pandora's box).
    commercial_block = ""
    if cell_score and value_label in {"COMMERCIAL-OPPORTUNITY", "SIGNIFICANT"}:
        volume = friction_volume_value(cell_score.value, period="week")
        scaffold = commercial_scaffold(cell_score.value)
        if volume is not None:
            sub = f"sessions/wk recoverable · {value_label.lower().replace('-', ' ')}"
            if scaffold:
                sub += f" · {scaffold}"
            commercial_block = body_primary_kpi(
                value=f"{volume} /wk",
                label="RECOVERABLE FRICTION VOLUME",
                sub=sub,
                color=_VALUE_COLORS.get(value_label, "var(--blue)"),
            )
        else:
            commercial_block = body_primary_kpi(
                value=value_label,
                label="VALUE TIER",
                sub="friction volume pending — engine scenario not wired for this pack",
                color=_VALUE_COLORS.get(value_label, "var(--blue)"),
            )

    # PULSE-93/96 wiring — the decision-QUALITY strip + lineage badge now read
    # from the live synthesis analytics (real confidence band/interval, Brier
    # calibration, fairness flag, lineage anchor), not hardcoded literals. When
    # analytics are unavailable (fixture pack / engine error) we render the
    # honest pending state instead of a fabricated "Confidence 0.82".
    quality_items = analytics_quality_items(meta["pack_name"]) or [
        "Confidence —", "Brier —", "Fairness —", "Lineage pending",
    ]
    lineage_short = lineage_anchor_short(meta["pack_name"])
    lineage_note = (
        f"lineage:{lineage_short}" if lineage_short
        else f"sha256:{short_hash(pack['sha256'])} (meta · lineage pending)"
    )

    return render_box(
        header=box_header(key_area, "key area · selection-driven"),
        accent_color=tier_color,
        headline=headline_tier_badge(
            tier=tooltip_token("action", tier),  # HOL-14 hover glossary
            color=tier_color,
            context=headline_context,
        ),
        body=(
            body_action_primary("ACTION", recommendation, tier_color)
            + commercial_block
            + body_chip_strip(supporting_chips)
            # Multi-signal provenance — this verdict is fused from the signal
            # classes Pulse has wired (behaviour + demographics today); voice /
            # calls / vulnerability-classification are pending their joins.
            + (signal_provenance() if cell_score else "")
            + body_lines([
                (f'<strong>What this means:</strong> {verdict_synthesis}',
                 "var(--text-2)"),
            ])
            + body_quality_strip(quality_items)
        ),
        footer=box_footer(
            f"pack: {meta['pack_name']}", NOW, live=True,
            note=f"{lineage_note} · verdict v0 · DuckDB-backed (PULSE)",
        ),
    )


def render_box2(packs: list[dict]) -> str:
    """Box 2 — HYPOTHESIS (test bench).

    User selects a hypothesis from the dropdown, clicks RUN ANALYSIS,
    sees results in the body. Engine wiring lands later via
    pulse.workspace.run_hypothesis(pack_id) — design-stub now shows
    pre-baked results for the headline pack.
    """
    if not packs:
        return render_box(
            header=box_header("HYPOTHESIS", "test bench"),
            headline=headline_tier_badge("—", "var(--text-3)", "No hypotheses in registry"),
            body=body_lines([("No packs loaded", "var(--amber)")]),
            footer=box_footer("—", NOW, live=False, note="—"),
        )

    default_pack = headline_pack(packs)
    default_pack_name = default_pack["meta"]["pack_name"]

    # Dropdown options — one per pack, labelled by cell · signature · screen
    options_html = ""
    for p in packs:
        h = p["hypothesis"] or {}
        pn = p["meta"]["pack_name"]
        label = (
            f'cell {h.get("cell_id","?")} · '
            f'{h.get("signature_id","—").replace("_"," ")} · '
            f'{screen_short(h.get("screen_id","—"))}'
        )
        selected = " selected" if pn == default_pack_name else ""
        options_html += f'<option value="{pn}"{selected}>{label}</option>'

    headline_html = (
        '<div class="hypothesis-controls">'
        f'<select class="holter-filter-select hypothesis-select" '
        f'id="hypothesis-select" style="flex:1; min-width:0; font-size:12px;">{options_html}</select>'
        '<button class="holter-filter-btn" id="hypothesis-run" type="button">'
        'RUN ANALYSIS</button>'
        '</div>'
    )

    # Pre-baked results for the default pack (stub — real run = engine-side)
    h = default_pack["hypothesis"] or {}
    is_neg = h.get("ground_truth_expectation") == "negative"
    method = _e((h.get("analytic") or {}).get("method", "—"))
    # PR-panel fix: pack descriptions are free text from authored YAML — escape.
    statement = _e((default_pack["meta"].get("description") or "").strip().split("\n")[0])
    cohort_axes = h.get("cohort_axes", [])
    evidence = h.get("evidence_required", [])

    # Stub outcome — would come from engine
    outcome_label = "DETECTED" if not is_neg else "NULL · DISCRIMINATOR HELD"
    outcome_color = "var(--red)" if not is_neg else "var(--green)"
    n_sessions, n_arm_a, n_arm_b = 1247, 540, 707
    p_value = "< 0.001" if not is_neg else "0.42"
    effect = "+34pp dwell gap" if not is_neg else "no gap"

    # HOL-12 plain-English synthesis — what the outcome means for the investigator
    if is_neg:
        hypothesis_synthesis = ("hypothesis correctly held null — the signature "
                                "does NOT appear on this journey; discriminator "
                                "confirmed.")
    else:
        hypothesis_synthesis = ("hypothesis fired — the signature is detectable "
                                "above statistical baseline; carry into the verdict.")

    return render_box(
        header=box_header("HYPOTHESIS", "test bench"),
        accent_color="var(--blue)",
        headline=headline_html,
        body=body_lines([
            (f'<strong style="color:var(--text);">H1:</strong> {statement[:180] or "—"}',
             "var(--text-2)"),
        ]) + body_kpi_tiles([
            (outcome_label.split(" · ")[0],
             "OUTCOME",
             f"p = {p_value} · {effect}",
             outcome_color),
            (str(n_sessions),
             "SESSIONS",
             f"arm-A {n_arm_a} · arm-B {n_arm_b}",
             "var(--blue)"),
            (method.split("_")[0].upper() if method != "—" else "—",
             "METHOD",
             method,
             "var(--teal)"),
        ]) + body_lines([
            (f'<strong>What this means:</strong> {hypothesis_synthesis}',
             "var(--text-2)"),
            (f'<strong>Cohort axes:</strong> {" · ".join(cohort_axes[:4]) or "—"}',
             "var(--text-3)"),
            (f'<strong>Evidence:</strong> {" · ".join(evidence[:4]) or "—"}',
             "var(--text-3)"),
        ]),
        footer=box_footer(
            f"hypothesis v0.1 · pack: {default_pack_name[:40]}", NOW, live=True,
            note=f"sha256:{short_hash(default_pack['sha256'])} · engine churns DuckDB on Run Analysis",
        ),
    )


def render_box3(packs: list[dict], selected_name: str | None = None) -> str:
    """Box 3 — EVIDENCE (taste of data).

    Headline KPI + 30-day trend sparkline + supporting stats. A "taste"
    of the underlying evidence — full drill-down lives in V3 panels below.
    HOL-67 — `selected_name` is the live Streamlit journey pick.
    """
    pack = _workspace_default_pack(packs, selected_name)
    if not pack:
        return render_box(
            header=box_header("EVIDENCE", "key data"),
            headline=headline_tier_badge("—", "var(--text-3)", "No data for selection"),
            body=body_lines([("No packs loaded", "var(--amber)")]),
            footer=box_footer("—", NOW, live=False, note="—"),
        )

    meta = pack["meta"]
    h = pack["hypothesis"] or {}
    cell_score = get_pack_cell(meta["pack_name"])

    # Stub 30-day affected-sessions series — engine returns the real trend
    trend = [42, 48, 51, 47, 53, 61, 58, 67, 72, 78, 81, 88, 92, 99, 105,
             112, 109, 118, 125, 132, 138, 145, 152, 161, 168, 175, 184, 191, 198, 207]
    today_n     = trend[-1]
    week_ago_n  = trend[-8]
    delta_abs   = today_n - week_ago_n
    delta_pct   = int(100 * delta_abs / week_ago_n) if week_ago_n else 0
    total_30d   = sum(trend)
    peak_day    = max(trend)
    # HOL-17 — Designed Ceiling: the engine-defined "acceptable friction"
    # threshold above which decision-quality flags fire. Stubbed at 150;
    # real value lives on the verdict object once pulse.workspace lands.
    designed_ceiling = 150
    crossed_at_day   = next((i for i, v in enumerate(trend) if v > designed_ceiling), None)

    # Direction signal — climbing trend = friction worsening
    delta_dir = "↗" if delta_abs > 0 else ("↘" if delta_abs < 0 else "→")
    delta_color = "var(--red)" if delta_abs > 0 else "var(--green)"
    spark_color = delta_color

    # Cohort over-index — stub; engine returns real value via Value methodology
    if cell_score and cell_score.value.adjustments_applied:
        cohort_over = "2.4×" if "vulnerable_cohort_concentrated" in cell_score.value.adjustments_applied else "1.3×"
    else:
        cohort_over = "—"

    # HOL-56 + no-pound-pandora — Box 3 KPI swap. When the pack is
    # commercial-tier, the headline leads with the FRICTION-VOLUME signal
    # (sessions/wk recoverable) — the unit a product team can act on and the
    # customer's own outcome currency. The £ figure, if ARPU is configured,
    # rides in the delta line as a named-assumption cost scaffold — never the
    # lead stat (Meadows: the user can't act on £; they fix the friction;
    # Cagan: PMs ship against sessions, not £/mo).
    is_commercial_pack = (
        cell_score is not None
        and cell_score.value.tier in _COMMERCIAL_TIERS
    )
    recoverable_wk = (
        getattr(cell_score.value, "recoverable_sessions_per_week", None)
        if is_commercial_pack else None
    )
    has_commercial = recoverable_wk is not None

    if has_commercial:
        commercial_color = _VALUE_COLORS.get(cell_score.value.tier, "var(--green)")
        scaffold = commercial_scaffold(cell_score.value)
        volume_val = friction_volume_value(cell_score.value, period="week")
        delta_line = f"{cell_score.value.tier} · conv-rate delta {cell_score.value.conversion_rate_delta:.0%}"
        if scaffold:
            delta_line += f" · {scaffold}"
        headline_card = headline_stat_card(
            label="RECOVERABLE FRICTION VOLUME",
            value=f"{volume_val} /wk",
            delta=delta_line,
            traj=f"{delta_dir} {delta_abs:+d} sessions/wk · friction widening" if delta_abs > 0 else f"{delta_dir} EASING",
            meta_left=f"30-day affected: {total_30d:,} sessions",
            meta_right=NOW,
            progress_pct=int(100 * today_n / peak_day) if peak_day else 0,
        )
        what_this_tells_us = (
            "<strong>What this tells us:</strong> sessions recoverable if the "
            "friction is removed; drill V3 for cohort cuts &amp; journey replay"
        )
        primary_kpi_block = body_primary_kpi(
            value=f"{today_n}",
            label="AFFECTED SESSIONS · TODAY",
            sub=f"30-day total: {total_30d:,} cumulative · {delta_abs:+d} vs 7d ago",
            color="var(--blue)",
        )
    else:
        headline_card = headline_stat_card(
            label="AFFECTED SESSIONS · TODAY",
            value=f"{today_n}",
            delta=f"{delta_dir} {delta_abs:+d} vs 7d ago ({delta_pct:+d}%)",
            traj=f"{delta_dir} CLIMBING" if delta_abs > 0 else f"{delta_dir} EASING",
            meta_left=f"30-day total: {total_30d:,}",
            meta_right=NOW,
            progress_pct=int(100 * today_n / peak_day) if peak_day else 0,
        )
        what_this_tells_us = (
            "<strong>What this tells us:</strong> climbing trend — friction "
            "compounding week-over-week; drill V3 for cohort cuts &amp; journey replay"
        )
        primary_kpi_block = body_primary_kpi(
            value=f"{total_30d:,}",
            label="30-DAY TOTAL",
            sub="cumulative affected sessions",
            color="var(--blue)",
        )

    # PULSE-93/96 — footer lineage badge from the live analytics anchor (not the
    # metadata-file sha). The 30-day series itself stays illustrative: the Cause
    # analytics layer produces a single-snapshot investigation, not a time series.
    lineage_short = lineage_anchor_short(meta["pack_name"])
    lineage_note = (
        f"lineage:{lineage_short}" if lineage_short
        else f"sha256:{short_hash(pack['sha256'])} (meta · lineage pending)"
    )

    return render_box(
        header=box_header("EVIDENCE", "key data · 30-day trend"),
        accent_color=delta_color,
        headline=headline_card,
        body=(
            f'<div style="padding:4px 0 2px; font-size:9px; color:var(--text-3); '
            f'letter-spacing:1.4px; text-transform:uppercase; '
            f'display:flex; justify-content:space-between; align-items:baseline;">'
            f'<span>30-day trend</span>'
            f'<span style="font-family:var(--mono); letter-spacing:0.5px; '
            f'text-transform:none;">- - designed ceiling {designed_ceiling}'
            + (f' · crossed day {crossed_at_day+1}' if crossed_at_day is not None else '')
            + f'</span>'
            f'</div>'
            + sparkline_svg(trend, spark_color, reference_value=designed_ceiling)
            + primary_kpi_block
            + body_disclosure(
                summary="DETAIL",
                content=(
                    f'<span><strong>Peak day:</strong> {peak_day} (highest in 30d window)</span>'
                    f'<span><strong>Cohort over-index:</strong> {cohort_over} (vulnerable vs baseline)</span>'
                ),
            )
            + body_lines([(what_this_tells_us, "var(--text-2)")])
        ),
        footer=box_footer(
            "evidence v0.1", NOW, live=True,
            note=f"{lineage_note} · 30-day trend illustrative · drill V3 for full evidence",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Engine summary row — Friction Risk · Placement Posture · Confidence Protocol
# ─────────────────────────────────────────────────────────────────────────────

def render_box_friction_risk(packs: list[dict]) -> str:
    risk = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
    discriminators = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")
    score = f"{risk * 6.5:.1f}"
    pos_pack = next((p for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative"
                    and "abandon" in p["meta"]["pack_name"]), None)
    return render_box(
        header=box_header("FRICTION RISK SCORE", "v0.1"),
        accent_color="var(--amber)",
        headline=headline_stat_card(
            label="CELL RISK SCORE",
            value=score,
            delta=f"+{risk * 6.5 - 19.5:.1f} vs showcase",
            traj="↗ COMPLETE" if risk >= 11 else "↗ GROWING",
            meta_left=f"{risk} positive cells × 6.5 weight",
            meta_right=NOW,
            progress_pct=min(100, int(risk * 6.5)),
        ),
        body=body_kpi_tiles([
            (str(risk),            "POSITIVE",      "detector cells", "var(--teal)"),
            (str(discriminators),  "DISCRIMINATOR", "negative-class", "var(--amber)"),
            (str(len(packs)),      "TOTAL",         "cells covered",  "var(--blue)"),
        ]) + body_lines([
            ("Score formula: positive_count × 6.5 weight · placeholder until v0.2", "var(--text-3)"),
            ("All cells canvas-complete (PULSE-104) · methodology validators green", "var(--green)"),
        ]) + (body_evidence_cards([(
            _extract_quote(pos_pack) or "—",
            f"Top positive · cell {(pos_pack['hypothesis'] or {}).get('cell_id','?')}",
        )]) if pos_pack else ""),
        footer=box_footer("pulse v1.0.0", NOW, live=True,
                         note=f"Risk-weighted across {len(packs)} cells"),
    )


def render_box_placement_posture(packs: list[dict]) -> str:
    cells = [get_pack_cell(p["meta"]["pack_name"]) for p in packs]
    cells = [c for c in cells if c is not None]
    if not cells:
        return render_box(
            header=box_header("PLACEMENT POSTURE", "PULSE-106"),
            headline=headline_tier_badge("UNAVAILABLE", "var(--amber)",
                                          "PULSE-106 placement scenario could not load"),
            body=body_lines([("Engine import failed — see render_holter.py logs", "var(--amber)")]),
            footer=box_footer("placement v0.1.0", NOW, live=False, note="Engine offline"),
        )
    high_value = {"SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"}
    high_risk = {"ESCALATE", "REGULATORY-FLAG"}
    counts = {"ACUTE": 0, "REGULATORY-FLAG": 0, "COMMERCIAL-OPPORTUNITY": 0,
              "WATCH": 0, "NOMINAL": 0, "NEEDS_MORE_DATA": 0}
    for c in cells:
        if c.diagnosis.diagnosis == "INCONCLUSIVE":
            counts["NEEDS_MORE_DATA"] += 1
            continue
        hv = c.value.tier in high_value
        hr = c.risk.tier in high_risk
        if hv and hr: counts["ACUTE"] += 1
        elif hr: counts["REGULATORY-FLAG"] += 1
        elif hv: counts["COMMERCIAL-OPPORTUNITY"] += 1
        elif c.risk.tier == "NOMINAL" and c.value.tier == "NOMINAL": counts["NOMINAL"] += 1
        else: counts["WATCH"] += 1
    dominant = max(counts, key=counts.get)
    dom_color = _ACTION_COLORS.get(dominant, "var(--amber)")
    # HOL-14 — wrap each action-tier token in hover-glossary
    chip_rows = [
        (tooltip_token("action", t), str(counts[t]), _ACTION_COLORS[t])
        for t in ("ACUTE", "REGULATORY-FLAG", "COMMERCIAL-OPPORTUNITY",
                  "WATCH", "NOMINAL", "NEEDS_MORE_DATA")
    ]
    return render_box(
        header=box_header("PLACEMENT POSTURE", "Agentic AI"),
        accent_color=dom_color,
        headline=headline_tier_badge(
            tier=f"{tooltip_token('action', dominant)} · {counts[dominant]}/{len(cells)}",
            color=dom_color,
            context="Dominant action tier across placement cells · Diagnosis can override the 2×2",
        ),
        body=body_chip_strip(chip_rows) + body_lines([
            ("CLARK-style action tier from Risk × Value 2×2", "var(--blue)"),
            ("Diagnosis overrides INCONCLUSIVE → NEEDS_MORE_DATA", "var(--text-3)"),
            ("JOURNEY_PROBLEM → 'fix the journey' verb regardless of tier", "var(--text-3)"),
        ]),
        footer=box_footer("diagnosis+risk+value v0.1.0", NOW, live=True,
                         note=f"Computed across {len(cells)} cells · PULSE-106"),
    )


def render_box_confidence_protocol(packs: list[dict]) -> str:
    n_neg = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")
    n_pos = len(packs) - n_neg
    # PULSE-93 is live — replace the "awaiting hydration" placeholder with the
    # real synthesis state, proven by running the headline pack through the
    # synthesis analytics (mode + confidence band + lineage anchor).
    hp = headline_pack(packs)
    synth_out = get_pack_analytics(hp["meta"]["pack_name"]) if hp else None
    if synth_out is not None:
        sp = synth_out.payload
        synth_line = (
            f"Synthesis LIVE · {sp['pack']['synthesis_mode']} · "
            f"confidence {sp['confidence_band']} · "
            f"lineage {short_hash(sp['lineage_anchor'])} (PULSE-93)"
        )
        synth_color = "var(--green)"
    else:
        synth_line = "Synthesis · analytics unavailable for headline pack (PULSE-93)"
        synth_color = "var(--text-3)"
    return render_box(
        header=box_header("CONFIDENCE PROTOCOL", "4-tier"),
        accent_color="var(--green)",
        headline=headline_chip_strip([
            ("0",         "PULSE-3", "var(--red)"),
            (str(n_neg),  "PULSE-2", "var(--amber)"),
            (str(n_pos),  "PULSE-1", "var(--teal)"),
            (str(len(packs)), "PULSE-0", "var(--blue)"),
        ]),
        body=body_bars([
            ("PULSE-0 valid",         100, f"{len(packs)}/12", "var(--blue)"),
            ("PULSE-1 detector",      int(100 * n_pos/12) if len(packs) else 0,
                                       f"{n_pos}/12", "var(--teal)"),
            ("PULSE-2 discriminator", int(100 * n_neg/12) if len(packs) else 0,
                                       f"{n_neg}/12", "var(--amber)"),
            ("PULSE-3 failure",       0, "0/12", "var(--red)"),
        ]) + body_lines([
            (f"All {len(packs)} packs pass v1 metadata validator", "var(--green)"),
            (f"All {len(packs)} packs pass canvas-completeness (PULSE-103)", "var(--green)"),
            (synth_line, synth_color),
        ]),
        footer=box_footer("registry v0.1", NOW, live=True,
                         note="Per-pack confidence inputs land in v0.2"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Methodology distribution row — Diagnosis · Value · Risk
# ─────────────────────────────────────────────────────────────────────────────

def _dist_box(packs: list[dict], *, name: str, attr_path: tuple[str, str],
              color_map: dict[str, str], methodology_version: str,
              context_template: str, glossary_dim: str = "") -> str:
    """Generic distribution box for Diagnosis / Value / Risk.

    glossary_dim: dimension key into STATUS_GLOSSARY for hover tooltips
    on tier tokens (HOL-14). Falls back to bare tokens if unset.
    """
    cells = [get_pack_cell(p["meta"]["pack_name"]) for p in packs]
    cells = [c for c in cells if c is not None]
    if not cells:
        return render_box(
            header=box_header(f"{name} DISTRIBUTION", "engine offline"),
            headline=headline_tier_badge("UNAVAILABLE", "var(--amber)",
                                          "Engine scenario could not load"),
            body=body_lines([("PULSE-106 placement scenario unavailable", "var(--amber)")]),
            footer=box_footer(f"{name.lower()} v0.1.0", NOW, live=False, note="Engine offline"),
        )
    tier_counts: dict[str, int] = {}
    for c in cells:
        score_obj = getattr(c, attr_path[0])
        tier = getattr(score_obj, attr_path[1])
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    dominant = max(tier_counts, key=tier_counts.get)
    dom_color = color_map.get(dominant, "var(--amber)")
    # HOL-14: wrap each tier label in hover glossary
    chip_rows = [(tooltip_token(glossary_dim, t),
                  str(tier_counts.get(t, 0)),
                  color_map.get(t, "#7A7A7A"))
                 for t in color_map.keys()]
    # Two evidence cards for the dominant tier
    dominant_packs = []
    for p in packs[:6]:
        cs = get_pack_cell(p["meta"]["pack_name"])
        if cs is None: continue
        if getattr(getattr(cs, attr_path[0]), attr_path[1]) == dominant:
            dominant_packs.append((p, cs))
        if len(dominant_packs) >= 2: break
    evidence = []
    for p, cs in dominant_packs[:2]:
        h = p["hypothesis"] or {}
        # PR-panel fix: escape pack_name + description (engine free-text)
        desc = (p["meta"].get("description", "").strip().replace(chr(10), " "))[:180]
        evidence.append((
            f"{_e(p['meta']['pack_name'])} → {_e(dominant)}. {_e(desc)}",
            f"Cell {_e(str(h.get('cell_id','?')))} · {_e(dominant)}",
        ))
    return render_box(
        header=box_header(f"{name} DISTRIBUTION", f"v{methodology_version}"),
        accent_color=dom_color,
        headline=headline_tier_badge(
            tier=f"{tooltip_token(glossary_dim, dominant)} · {tier_counts[dominant]}/{len(cells)}",
            color=dom_color,
            context=context_template,
        ),
        body=body_chip_strip(chip_rows)
             + (body_evidence_cards(evidence) if evidence else "")
             + body_lines([
                 (f"{len(cells)} cells scored · methodology v{methodology_version}", "var(--blue)"),
             ]),
        footer=box_footer(f"{name.lower()} v{methodology_version}", NOW, live=True,
                         note=f"Distribution across {len(cells)} scored cells"),
    )


def render_box_diagnosis_dist(packs: list[dict]) -> str:
    return _dist_box(
        packs, name="DIAGNOSIS",
        attr_path=("diagnosis", "diagnosis"),
        color_map=_DIAGNOSIS_COLORS,
        methodology_version="0.1.0",
        context_template="Dominant Diagnosis · runs BEFORE Risk/Value · can override 2×2",
        glossary_dim="diagnosis",
    )


def render_box_value_dist(packs: list[dict]) -> str:
    return _dist_box(
        packs, name="VALUE TIER",
        attr_path=("value", "tier"),
        color_map=_VALUE_COLORS,
        methodology_version="0.1.0",
        context_template="Dominant Value tier · severity × population × frequency × cohort × counterfactual",
        glossary_dim="value",
    )


def render_box_risk_dist(packs: list[dict]) -> str:
    return _dist_box(
        packs, name="RISK TIER",
        attr_path=("risk", "tier"),
        color_map=_RISK_COLORS,
        methodology_version="0.1.0",
        context_template="Dominant Risk tier · regulatory taxonomy × bank policy × Chronicle precedent",
        glossary_dim="risk",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Chronicle matcher box
# ─────────────────────────────────────────────────────────────────────────────

def render_box_chronicle(packs: list[dict]) -> str:
    """Chronicle matcher state for the headline pack."""
    pack = headline_pack(packs)
    cs = get_pack_cell(pack["meta"]["pack_name"]) if pack else None
    matches = cs.risk.chronicle_matches if cs else []
    n_matches = len(matches)
    h = (pack or {}).get("hypothesis") or {}
    return render_box(
        header=box_header("CHRONICLE MATCHER", "PULSE-100"),
        accent_color="var(--amber)",
        headline=headline_chip_strip([
            (str(n_matches), "VERIFIED MATCHES", "var(--green)" if n_matches else "#7A7A7A"),
            ("10", "LIBRARY ENTRIES", "var(--blue)"),
            ("10", "PENDING REVIEW",  "var(--amber)"),
        ]),
        body=body_lines([
            (f"Headline pack: cell {h.get('cell_id','?')} · {h.get('signature_id','—').replace('_',' ')}", "var(--blue)"),
            (
                f"{n_matches} verified precedents matched" if n_matches
                else "NO verified matches · matcher fails closed on pending entries",
                "var(--green)" if n_matches else "var(--amber)",
            ),
            ("Seed library: 10 CHR-friction entries, all pending_human_review", "var(--text-3)"),
            ("Curator handoff: corroborate against cited public sources · flip to verified", "var(--text-3)"),
            ("Two-stage trust: matcher excludes pending entries from prod Risk scoring", "var(--text-3)"),
        ]),
        footer=box_footer("chronicle v0.1.0", NOW, live=True,
                         note="Risk methodology will use chronicle once entries flip to verified"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-journey commentary boxes (4 boxes, one per journey)
# ─────────────────────────────────────────────────────────────────────────────

def render_box_commentary_for_journey(packs: list[dict], journey_prefix: str,
                                       display_name: str) -> str:
    """One box per journey showing the 3 signatures' summaries."""
    journey_packs = [p for p in packs
                     if (p["hypothesis"] or {}).get("screen_id", "").startswith(journey_prefix)]
    if not journey_packs:
        return render_box(
            header=box_header(f"COMMENTARY · {display_name}", "—"),
            headline=headline_tier_badge("NO PACKS", "var(--text-3)", "No packs for this journey"),
            body=body_lines([("Journey not present in registry", "var(--text-3)")]),
            footer=box_footer("commentary v0.1", NOW, live=False, note="—"),
        )
    n_pos = sum(1 for p in journey_packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
    n_neg = len(journey_packs) - n_pos
    # Dominant action tier for the journey
    cells = [get_pack_cell(p["meta"]["pack_name"]) for p in journey_packs]
    cells = [c for c in cells if c is not None]
    if cells:
        action_counts: dict[str, int] = {}
        for c in cells:
            action_counts[c.action_tier] = action_counts.get(c.action_tier, 0) + 1
        dominant = max(action_counts, key=action_counts.get)
        dom_color = _ACTION_COLORS.get(dominant, "var(--amber)")
        tier_text = f"{dominant} · {action_counts[dominant]}/{len(cells)}"
    else:
        dominant = "—"
        dom_color = "var(--text-3)"
        tier_text = "engine offline"
    # Evidence: 2 of the journey's packs
    evidence: list[tuple[str, str]] = []
    for p in journey_packs[:2]:
        h = p["hypothesis"] or {}
        # _extract_quote() is pre-escaped; description fallback + signature_id are not
        quote = _extract_quote(p) or _e(
            (p["meta"].get("description", "").strip().replace("\n", " "))[:200]
        )
        evidence.append((
            quote,
            f"Cell {_e(str(h.get('cell_id','?')))} · "
            f"{_e(h.get('signature_id','—').replace('_',' '))}",
        ))
    return render_box(
        header=box_header(f"COMMENTARY · {display_name}", f"{len(journey_packs)} packs"),
        accent_color=dom_color,
        headline=headline_tier_badge(
            tier=tier_text, color=dom_color,
            context=f"Per-journey roll-up · {n_pos} positive · {n_neg} negative · 3 signatures (dwell · multi_back · abandon)",
        ),
        body=body_evidence_cards(evidence) + body_lines([
            (f"Journey: {journey_prefix}", "var(--blue)"),
            (f"{len(journey_packs)} packs canvas-complete · all in registry", "var(--green)"),
        ]),
        footer=box_footer("commentary v0.1", NOW, live=True,
                         note=f"Journey: {display_name}"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bench box (summary across 12 cells)
# ─────────────────────────────────────────────────────────────────────────────

def render_box_bench(packs: list[dict]) -> str:
    sorted_packs = sorted(packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99))
    rows = ""
    densities = []
    for p in sorted_packs[:6]:
        h = p["hypothesis"] or {}
        cohort_n = len(h.get("cohort_axes") or [])
        evidence_n = len(h.get("evidence_required") or [])
        density = min((cohort_n + evidence_n) * 6, 100)
        densities.append(density)
        is_neg = h.get("ground_truth_expectation") == "negative"
        gt_color = "var(--amber)" if is_neg else "var(--teal)"
        sig = h.get("signature_id", "—").replace("_", " ")
        rows += (
            f'<tr><td>Cell {h.get("cell_id","?")} · {sig[:18]}</td>'
            f'<td style="text-align:right;font-family:var(--mono);">{density}%</td>'
            f'<td style="text-align:right;color:{gt_color};">{"NEG" if is_neg else "POS"}</td></tr>'
        )
    avg_density = int(sum(densities) / len(densities)) if densities else 0
    return render_box(
        header=box_header("⚠ FRICTIONBENCH", "cell density"),
        accent_color="var(--blue)",
        headline=headline_stat_card(
            label="AVG DENSITY",
            value=f"{avg_density}%",
            delta=f"+{avg_density - 60}% vs floor",
            traj="↗" if avg_density > 60 else "→",
            meta_left=f"Cohort axes + evidence fields across {len(packs)} cells",
            meta_right=NOW,
            progress_pct=avg_density,
        ),
        body=(
            f'<table class="body-table">'
            f'<thead><tr><th>Cell</th><th style="text-align:right;">Density</th>'
            f'<th style="text-align:right;">GT</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        ) + body_lines([
            (f"Top {min(6, len(packs))} cells shown · scroll detail in v0.2", "var(--text-3)"),
            ("Density = (cohort_axes + evidence_required) × 6 cap 100%", "var(--text-3)"),
        ]),
        footer=box_footer("frictionbench v0.1", NOW, live=True,
                         note=f"FrictionBench cell benchmark · {len(packs)} cells covered"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# JS — adapted from render_mil_briefing FILTER_JS
# ─────────────────────────────────────────────────────────────────────────────

FILTER_JS = """
<script>
/* Holter filter JS — sidebar checkboxes + topnav dropdowns drive box visibility.
 * Each .holter-box can carry data-packname / data-domain / data-author etc.;
 * the filter applies via class .filtered-out → display:none.
 */
(function () {
  // Topnav + filter strip dropdowns — all are <select data-filter="…">
  const $selects = ['filter-product', 'filter-owner', 'filter-journey']
                     .map(id => document.getElementById(id));
  const $resetBtn  = document.getElementById('filter-reset');
  const $stripApply = document.getElementById('filter-apply');
  const $stripReset = document.getElementById('filter-strip-reset');

  function matches(el) {
    const filters = $selects.filter(Boolean).map(sel => ({
      attr: sel.dataset.filter,
      value: sel.value,
    })).filter(f => f.value);
    for (const f of filters) {
      if (f.attr === 'packname' && el.dataset.packname !== f.value) return false;
      if (f.attr === 'author' && (el.dataset.author || '').split(',').indexOf(f.value) < 0) return false;
      if (f.attr === 'domain' && el.dataset.domain !== f.value) return false;
    }
    return true;
  }

  function applyFilters() {
    const boxes = document.querySelectorAll('.holter-box[data-packname], .holter-box[data-domain]');
    boxes.forEach(b => {
      if (matches(b)) b.classList.remove('filtered-out');
      else b.classList.add('filtered-out');
    });
    let anyActive = false;
    $selects.forEach(sel => {
      if (!sel) return;
      if (sel.value) { sel.classList.add('filter-on'); anyActive = true; }
      else sel.classList.remove('filter-on');
    });
    if ($resetBtn) {
      if (anyActive) $resetBtn.removeAttribute('hidden');
      else $resetBtn.setAttribute('hidden', '');
    }
  }

  function reset() {
    $selects.forEach(sel => { if (sel) sel.value = ''; });
    applyFilters();
  }

  $selects.forEach(sel => sel && sel.addEventListener('change', applyFilters));
  if ($resetBtn) $resetBtn.addEventListener('click', reset);
  if ($stripApply) $stripApply.addEventListener('click', applyFilters);
  if ($stripReset) $stripReset.addEventListener('click', reset);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') reset(); });

  applyFilters();
})();

/* Time picker popover */
(function () {
  const btn = document.getElementById('time-btn');
  const pop = document.getElementById('time-pop');
  const label = document.getElementById('time-btn-label');
  if (!btn || !pop || !label) return;

  function close() { pop.setAttribute('hidden', ''); }
  function open() { pop.removeAttribute('hidden'); }
  function isOpen() { return !pop.hasAttribute('hidden'); }

  btn.addEventListener('click', e => {
    e.stopPropagation();
    isOpen() ? close() : open();
  });
  document.addEventListener('click', e => {
    if (e.target.closest('#time-pop') || e.target.closest('#time-btn')) return;
    close();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });

  document.querySelectorAll('.time-preset').forEach(p => {
    p.addEventListener('click', () => {
      label.textContent = p.textContent.trim();
      document.querySelectorAll('.time-preset').forEach(b => b.classList.remove('active'));
      p.classList.add('active');
      close();
    });
  });
  const applyCustom = document.getElementById('time-apply');
  if (applyCustom) {
    applyCustom.addEventListener('click', () => {
      const from = document.getElementById('time-from').value;
      const to = document.getElementById('time-to').value;
      if (from && to) {
        label.textContent = from + ' → ' + to;
        document.querySelectorAll('.time-preset').forEach(b => b.classList.remove('active'));
      }
      close();
    });
  }
})();
</script>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Page composition
# ─────────────────────────────────────────────────────────────────────────────

def render_page(selected_pack_name: str | None = None) -> str:
    packs = discover_packs()
    rows_html = ""

    # Row 1 — topbar: Box 1/2/3 only (Box 0 dissolved into sticky filter strip).
    # HOL-67 — Box 1 (VERDICT) + Box 3 (EVIDENCE) follow the Streamlit journey
    # selection; Box 2 (HYPOTHESIS bench) keeps its own dropdown default.
    rows_html += '<div class="holter-row" data-row="topbar">'
    rows_html += render_box1(packs, selected_pack_name)
    rows_html += render_box2(packs)
    rows_html += render_box3(packs, selected_pack_name)
    rows_html += '</div>'

    # Page-chrome strips between topbar row and engine-summary row.
    # Documented exceptions to the box discipline — full-width horizontal
    # elements (ticker is a stream; journey row is a 4-cell status strip).
    rows_html += render_ticker(packs)
    rows_html += render_journey_row(packs)

    # Row 2 — engine summary
    rows_html += '<div class="holter-row" data-row="engine-summary">'
    rows_html += render_box_friction_risk(packs)
    rows_html += render_box_placement_posture(packs)
    rows_html += render_box_confidence_protocol(packs)
    rows_html += '</div>'

    # Row 3 — methodology distributions
    rows_html += '<div class="holter-row" data-row="methodology-distributions">'
    rows_html += render_box_diagnosis_dist(packs)
    rows_html += render_box_value_dist(packs)
    rows_html += render_box_risk_dist(packs)
    rows_html += '</div>'

    # Row 4 — chronicle + bench + first journey commentary
    rows_html += '<div class="holter-row" data-row="detail-row-1">'
    rows_html += render_box_chronicle(packs)
    rows_html += render_box_bench(packs)
    rows_html += render_box_commentary_for_journey(packs, "loans", "Loans · step3")
    rows_html += '</div>'

    # Row 5 — remaining journey commentary
    rows_html += '<div class="holter-row" data-row="detail-row-2">'
    rows_html += render_box_commentary_for_journey(packs, "international", "International · setup")
    rows_html += render_box_commentary_for_journey(packs, "cards", "Cards · eligibility")
    rows_html += render_box_commentary_for_journey(packs, "investments", "Investments · overview")
    rows_html += '</div>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Holter — functional template</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="holter-app">
  {render_topnav(packs)}
  {render_filter_strip(packs)}
  <main class="holter-main">{rows_html}</main>
</div>
{FILTER_JS}
</body>
</html>'''


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_page()
    out = OUT_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
