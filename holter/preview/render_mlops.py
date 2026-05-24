"""MLOps Console (HOL-6) — procurement-gate surface for ML eng + MRM.

Per HOL-6 spec (CLAUDE.md surface 4): mandatory before any live bank
deployment; built BEFORE any LLM_AUGMENTED synthesis is enabled in prod.

Four panes:
  1. DRIFT MONITORS — per FrictionBench cell × signature; time-series of
     detection rate / false-positive rate / accuracy gap
  2. FAIRNESS RE-CHECK — demographic_parity / equalised_odds /
     calibration_by_cohort over time, per template, per cohort dim
  3. LINEAGE VERIFIER — hash-chain health, broken-chain alerts,
     last-verified timestamp per pack
  4. SYNTHESIS-MODE GOVERNANCE — table of every pack with synthesis_mode
     (DETERMINISTIC / LLM_AUGMENTED), attestation status, reviewer + date

Critical mitigation — narrative layer (eats own dogfood):
  Every drift alert + fairness deviation MUST produce a deterministic
  one-paragraph narrative via the "What changed, for whom, with what
  evidence, what's the recommended response" template. Engine returns
  these later via pulse.synthesis.base.TemplateSynthesisProvider; stubbed
  here for design preview.

Out of scope: NO model training UI, NO notebook env, NO feature store browser.

Output: dist/preview/mlops/index.html
Serve:  py holter/preview/serve_mlops.py  (port 8506)
"""

from __future__ import annotations

import datetime as _dt
import sys
from dataclasses import dataclass
from html import escape as _e
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "dist" / "preview" / "mlops"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# HOL-35: import primitives from _shared, not from render_holter — so a
# broken Workspace import doesn't cascade to MLOps Console (Cannon's
# hand-carry concern). render_holter is no longer in the import path.
from holter.preview._shared import (  # noqa: E402
    discover_packs,
    get_pack_cell,
    get_pack_analytics,
    short_hash,
    sparkline_svg,
    box_header,
    box_footer,
    render_box,
    body_lines,
    body_kpi_tiles,
    body_chip_strip,
    body_bars,
    body_action_primary,
    body_disclosure,
    body_quality_strip,
    body_primary_kpi,
    headline_tier_badge,
    headline_stat_card,
    headline_chip_strip,
    tooltip_token,
    render_glossary_panel,
    _ACTION_COLORS,
    _RISK_COLORS,
    _VALUE_COLORS,
    friction_volume_headline,
    commercial_scaffold,
)

NOW = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ─────────────────────────────────────────────────────────────────────────────
# Stub data — engine returns these via pulse.frictionbench/convergence/lineage
# once those contracts are wired. Deterministic per pack-name hash.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CohortSeries:
    """HOL-54 — bundles label + colour + values for a single cohort line.
    Replaces the parallel-list signature of multi_sparkline_svg, eliminating
    silent length-mismatch risk."""
    label: str
    color: str
    values: list[float]


def multi_sparkline_svg(cohorts: list[CohortSeries],
                        width: int = 200, height: int = 36,
                        baseline: float | None = None,
                        baseline_color: str = "rgba(180,200,210,0.4)") -> str:
    """Multi-series sparkline — N overlaid trend lines + optional baseline.

    HOL-41: replaces the single-series sparkline_svg in DRIFT pane to surface
    cohort-level drift. Each CohortSeries carries its own label/color/values
    bundled. Baseline renders as a dashed horizontal line (cell-aggregated
    30-day mean).

    HOL-54: signature reshaped from parallel `series_list / colors / labels`
    lists to `list[CohortSeries]` (Hettinger PR-panel: silent length-mismatch
    risk eliminated).
    """
    if not cohorts or not cohorts[0].values:
        return ""
    # Y-axis range = union of all cohort series + baseline
    all_y: list[float] = []
    for c in cohorts:
        all_y.extend(c.values)
    if baseline is not None:
        all_y.append(baseline)
    vmin, vmax = min(all_y), max(all_y)
    span = (vmax - vmin) or 1.0
    n = len(cohorts[0].values)
    step = width / max(n - 1, 1)

    polylines = []
    # HOL-43 — tag each polyline with data-cohort so the legend can solo on
    # hover (CSS-only dim of other lines)
    for c in cohorts:
        pts = " ".join(
            f"{i*step:.1f},{height - ((v - vmin) / span) * height:.1f}"
            for i, v in enumerate(c.values)
        )
        # HOL-52 fix-first (van Rossum) — escape label for the data-cohort attr.
        polylines.append(
            f'<polyline class="ms-line" data-cohort="{_e(c.label)}" '
            f'points="{pts}" fill="none" '
            f'stroke="{c.color}" stroke-width="1.4" opacity="0.85"/>'
        )

    baseline_svg = ""
    if baseline is not None:
        by = height - ((baseline - vmin) / span) * height
        baseline_svg = (
            f'<line x1="0" y1="{by:.1f}" x2="{width}" y2="{by:.1f}" '
            f'stroke="{baseline_color}" stroke-width="1" stroke-dasharray="2,3"/>'
        )

    # HOL-43 — invisible day-overlay rectangles carry <title> tooltips
    # showing per-day per-cohort values. Native browser tooltip; zero JS.
    day_rects = []
    if cohorts and cohorts[0].label:
        for i in range(n):
            x = max(0, i * step - step / 2)
            w = step
            tooltip_lines = [f"day -{n - 1 - i} (D{n - i})"]
            for c in cohorts:
                if i < len(c.values):
                    tooltip_lines.append(f"{c.label}: {c.values[i]:.0f}")
            tooltip = " · ".join(tooltip_lines)
            day_rects.append(
                f'<rect class="ms-day" x="{x:.1f}" y="0" '
                f'width="{w:.1f}" height="{height}" '
                f'fill="transparent">'
                f'<title>{tooltip}</title>'
                f'</rect>'
            )

    return (
        f'<svg class="body-sparkline" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" preserveAspectRatio="none">'
        f'{baseline_svg}'
        f'{"".join(polylines)}'
        f'{"".join(day_rects)}'
        f'</svg>'
    )


def synthesis_governance(pack: dict) -> dict:
    """REAL synthesis-mode (from pack metadata) + honest v1 attestation state.

    PULSE-93 wiring. `synthesis_mode` is read from the pack's own metadata.yaml —
    NOT fabricated. The v1 runtime is deterministic-locked (only
    TemplateSynthesisProvider ships; see pulse/synthesis/SYNTHESIS_DESIGN.md), so
    every v1 pack reads DETERMINISTIC and the LLM_AUGMENTED gate count is 0.

    Attestation reflects the honest pre-production state: nothing has been through
    an independent model-risk review, so deterministic packs are
    `attestation_pending` (awaiting MRM sign-off) and reviewer/date read as
    not-yet-assessed. A procurement gate must NOT assert governance that hasn't
    happened — so the previously-fabricated `certified` / `independently_assessed`
    rows and the invented MRM reviewer names ("J. Patel" / "S. Khan") are gone."""
    mode_raw = str(pack.get("meta", {}).get("synthesis_mode", "deterministic")).lower()
    is_llm = mode_raw == "llm_augmented"
    # self_declared for LLM (author-declared, unassessed); attestation_pending for
    # deterministic (awaiting independent MRM sign-off). Both are honest
    # "needs governance action" states — never a fabricated 'certified'.
    attestation = "self_declared" if is_llm else "attestation_pending"
    return {
        "synthesis_mode":  "LLM_AUGMENTED" if is_llm else "DETERMINISTIC",
        "mode_color":      "var(--red)" if is_llm else "var(--green)",
        "attestation":     attestation,
        "att_color":       "var(--amber)",
        "reviewer":        "—",            # no independent review has occurred (POC)
        "reviewed_date":   "—",
        # Every v1 pack is awaiting independent assessment → all actionable.
        "is_actionable":   True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic narrative layer — "What changed, for whom, with what evidence,
# what's the recommended response." Engine returns these via
# pulse.synthesis.base.TemplateSynthesisProvider; stubbed for design preview.
# ─────────────────────────────────────────────────────────────────────────────

def drift_narrative(pack_name: str, series: list[int]) -> str:
    """One-paragraph drift narrative over the REAL per-cell detection-rate series
    (pp) from run_history. Robust to short series."""
    if not series:
        return "<strong>What changed:</strong> no recorded runs for this cell."
    today = series[-1]
    week_ago = series[-8] if len(series) >= 8 else series[0]
    delta = today - week_ago
    direction = "rose" if delta > 0 else ("fell" if delta < 0 else "held")
    return (
        f"<strong>What changed:</strong> detection rate (recall) {direction} "
        f"{abs(delta)}pp over the window (now {today}%). "
        f"<strong>For whom:</strong> the {_e(pack_name)[:40]} cell's detection model. "
        f"<strong>Evidence:</strong> pulse.serving.run_history per-run series vs the "
        f"run-window mean. <strong>Response:</strong> "
        f"{'recalibrate threshold; investigate the missed-detection cohort' if abs(delta) > 5 else 'continue monitoring — within bounds'}."
    )


# HOL-40 — severity gradient: 4 tiers control narrative rendering.
# Materiality thresholds per pane keep narratives information-rich when present.

def render_severity_narrative(severity: str, body_html: str) -> str:
    """Render a narrative at the right visual weight for its severity.

    NOMINAL  → single status token (no narrative)
    WATCH    → compact muted summary
    ESCALATE → full 4-clause block (default; current behaviour)
    ACUTE    → full block + red rail + ACUTE prefix, non-suppressible

    Raskin's R1 rule: if every state transition generates the same paragraph
    shape, the medium trains people to ignore it.
    """
    sev = severity.lower()
    if sev == "nominal":
        return (
            f'<div class="mlops-narrative mlops-narrative--nominal">'
            f'▬ NOMINAL · no action required'
            f'</div>'
        )
    cls = {
        "watch":    "mlops-narrative mlops-narrative--watch",
        "escalate": "mlops-narrative mlops-narrative--escalate",
        "acute":    "mlops-narrative mlops-narrative--acute",
    }.get(sev, "mlops-narrative")
    return f'<div class="{cls}">{body_html}</div>'


def classify_drift_severity(worst_delta: int) -> str:
    """Materiality thresholds per ticket: |delta| < 2 NOMINAL / 2-5 WATCH /
    5-10 ESCALATE / >10 ACUTE."""
    a = abs(worst_delta)
    if a < 2:   return "NOMINAL"
    if a <= 5:  return "WATCH"
    if a <= 10: return "ESCALATE"
    return "ACUTE"


def classify_fairness_severity(n_deviations: int) -> str:
    if n_deviations == 0: return "NOMINAL"
    if n_deviations == 1: return "WATCH"
    if n_deviations <= 3: return "ESCALATE"
    return "ACUTE"


def classify_lineage_severity(n_broken: int) -> str:
    if n_broken == 0: return "NOMINAL"
    if n_broken == 1: return "ESCALATE"
    return "ACUTE"


def classify_synthesis_severity(n_llm: int) -> str:
    """LLM_AUGMENTED in prod is the v1 immutability gate violation —
    ESCALATE/ACUTE depending on count."""
    if n_llm == 0: return "NOMINAL"
    if n_llm == 1: return "ESCALATE"
    return "ACUTE"


def attestation_severity(attestation: str) -> str:
    """HOL-45 — per-row severity for SYNTHESIS filter. PENDING covers both
    self_declared and attestation_pending; everything else is NOMINAL."""
    if attestation in ("self_declared", "attestation_pending"):
        return "PENDING"
    return "NOMINAL"


# HOL-54 (Hettinger PR-panel) — split monolith into 4 domain-scoped dicts.
# Each call site reaches for the right one; misses are clear instead of silent.
# Plain-language so a non-statistician can decode (Gigerenzer R1 + R2 ask).

DRIFT_RULES: dict[str, str] = {
    "DRIFT_NOMINAL":  "Drift NOMINAL = |delta| < 2pp (no material change)",
    "DRIFT_WATCH":    "Drift WATCH = 2-5pp delta (observe; no action required)",
    "DRIFT_ESCALATE": "Drift ESCALATE = 5-10pp delta (review baseline; flag for next cycle)",
    "DRIFT_ACUTE":    "Drift ACUTE = |delta| >= 10pp (recalibrate threshold; hold deployment)",
}

LINEAGE_RULES: dict[str, str] = {
    "LINEAGE_NOMINAL":  "Lineage NOMINAL = 0 broken chains (all hashes verified)",
    "LINEAGE_ESCALATE": "Lineage ESCALATE = 1 broken chain (re-seal; review anchor source)",
    "LINEAGE_ACUTE":    "Lineage ACUTE = 2+ broken chains (halt promotions; trace propagation)",
}

SYNTHESIS_RULES: dict[str, str] = {
    "SYNTHESIS_NOMINAL":  "Synthesis NOMINAL = 0 LLM_AUGMENTED in prod path",
    "SYNTHESIS_ESCALATE": "Synthesis ESCALATE = 1 LLM_AUGMENTED pack flagged (v1 gate violation)",
    "SYNTHESIS_ACUTE":    "Synthesis ACUTE = 2+ LLM_AUGMENTED packs (governance backlog)",
}

STATUS_RULES: dict[str, str] = {
    "VERIFIED": "VERIFIED = chain hash matches anchor; no tampering detected",
    "BROKEN":   "BROKEN = chain hash mismatch; lineage integrity compromised",
    "STABLE":   "STABLE = chain depth and parents unchanged over last 24h",
}

ATTESTATION_RULES: dict[str, str] = {
    "self_declared":          "self_declared = pack author asserted compliance; independent assessment required",
    "attestation_pending":    "attestation_pending = newly-onboarded pack awaiting MRM sign-off",
    "independently_assessed": "independently_assessed = second reviewer confirmed; not yet certified",
    "certified":              "certified = sealed for prod; quarterly recertification due",
}

FAIRNESS_METRIC_RULES: dict[str, str] = {
    "demographic_parity":  ("demographic_parity ∈ [0,1]; 1 = perfectly equal selection rates across cohorts. "
                            "Floor 0.85 = 15pp tolerance. Below floor = ACUTE."),
    "equalised_odds":      ("equalised_odds ∈ [0,1]; 1 = equal TPR and FPR across cohorts. "
                            "Floor 0.80 = 20pp tolerance. Below floor = ACUTE."),
    "calibration_by_cohort": ("calibration_by_cohort ∈ [0,1]; 1 = predicted probability matches observed rate "
                              "per cohort. Floor 0.90."),
}

# Aggregated map for the test-suite completeness check + legacy call sites.
# New code should reach for the domain-scoped dict directly.
THRESHOLD_RULES: dict[str, str] = {
    **DRIFT_RULES,
    **LINEAGE_RULES,
    **SYNTHESIS_RULES,
    **STATUS_RULES,
    **ATTESTATION_RULES,
    **FAIRNESS_METRIC_RULES,
}


def render_filter_strip(scope: str, options: list[tuple[str, str]],
                        default: str = "all") -> str:
    """HOL-45 — pane-scoped severity filter strip. Each button has
    data-filter-scope=<pane> + data-filter-value=<severity>. JS handler
    hides rows in the same scope whose data-severity doesn't match."""
    # NB: active attr computed out-of-string — backslashes inside f-string
    # expressions are a SyntaxError before Python 3.12 (bank env is 3.11-locked).
    parts = []
    for val, label in options:
        active = 'data-active="true"' if val == default else ""
        parts.append(
            f'<button class="pane-filter-btn" data-filter-scope="{scope}" '
            f'data-filter-value="{val}" '
            f'{active} '
            f'type="button">{_e(label)}</button>'
        )
    btns = "".join(parts)
    return (
        f'<div class="pane-filter-strip" data-filter-scope="{scope}">'
        f'<span class="pane-filter-label">filter</span>{btns}'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSS — MIL briefing aesthetic + a small MLOps-specific addition for the
# governance table
# ─────────────────────────────────────────────────────────────────────────────

CSS_EXTRA = (Path(__file__).parent / "mlops.css").read_text(encoding="utf-8")
# CSS body lives in holter/preview/mlops.css (HOL-53 — van Rossum PR-panel).
# Inlined at render time; same f-string compatibility as the prior triple-quoted string.


# ─────────────────────────────────────────────────────────────────────────────
# Pane renderers — each pane is one box obeying the 4-layer discipline
# ─────────────────────────────────────────────────────────────────────────────

# HOL-50 (Metz PR-panel): helper functions extracted from the pane renderers
# so each pane is orchestration-only. Pure refactor; byte-stable output.

def _render_drift_legend_strip() -> str:
    """DRIFT-pane strip: what the sparkline shows + the baseline marker. The
    per-cohort overlay + window scrubber are retired — run-history is per-cell
    (PULSE-133), not per-cohort, and each line is a real detection-rate series."""
    return (
        '<div class="drift-legend">'
        '<span class="drift-legend-label">detection rate %</span>'
        '<span class="drift-legend-baseline">'
        '<span class="drift-legend-baseline-line"></span>'
        '<span>run-window mean</span>'
        '</span>'
        '<span class="drift-legend-label" style="margin-left:auto;">'
        'per-cell recall over recorded runs</span>'
        '</div>'
    )


def _drift_history() -> list[dict]:
    """Real per-cell detection-metric history (run_history), fail-soft → []."""
    try:
        from pulse.serving.run_history import read_cell_metrics_history
        return read_cell_metrics_history()
    except Exception:
        import logging
        logging.exception("read_cell_metrics_history failed — DRIFT pane renders NO HISTORY")
        return []


def _drift_series_by_cell() -> dict[int, list[int]]:
    """{cell_id: detection-rate series (pp, chronological)} from run_history."""
    by_cell: dict[int, list[int]] = {}
    for r in _drift_history():  # read_cell_metrics_history returns chronological
        by_cell.setdefault(r["cell_id"], []).append(round(r["detection_rate"] * 100))
    return by_cell


def _build_drift_row(p: dict, series_pp: list[int]) -> tuple[str, int]:
    """One DRIFT row from the REAL per-cell detection-rate series (pp). Returns
    (row_html, 7-day delta in pp) so the orchestrator can pick the worst cell."""
    today = series_pp[-1]
    week_ago = series_pp[-8] if len(series_pp) >= 8 else series_pp[0]
    delta = today - week_ago
    color = "var(--red)" if abs(delta) > 5 else (
             "var(--amber)" if abs(delta) > 2 else "var(--green)")
    h = p["hypothesis"] or {}
    cell = _e(str(h.get("cell_id", "?")))
    sig = _e(h.get("signature_id", "—").replace("_", " "))
    baseline = sum(series_pp) / len(series_pp)
    spark = sparkline_svg(
        series_pp, color if abs(delta) > 2 else "var(--blue)",
        width=240, height=28, reference_value=baseline,
    )
    # HOL-39 + HOL-45: cell-id link, per-row severity, threshold tooltip
    row_sev = classify_drift_severity(delta)
    delta_tooltip = DRIFT_RULES.get(f"DRIFT_{row_sev}", "")
    return (
        f'<div class="drift-cell cell-row pane-filterable" '
        f'data-cell-id="{cell}" data-severity="{row_sev}" '
        f'data-filter-scope="drift">'
        f'<span class="drift-cell-label">'
        f'<a class="cell-link" href="#cell-{cell}" data-cell-id="{cell}">cell {cell}</a>'
        f' · {sig}</span>'
        f'<span class="drift-cell-spark">{spark}</span>'
        f'<span class="drift-cell-val threshold-token" '
        f'style="color:{color};" title="{_e(delta_tooltip)}">'
        f'{delta:+d}pp</span>'
        f'</div>'
    ), delta


def render_drift_pane(packs: list[dict]) -> str:
    """Pane 1 — DRIFT MONITORS. REAL per-cell detection-rate history
    (run_history.read_cell_metrics_history) — one recall series per cell, not the
    fabricated cohort overlay (run-history is per-cell, PULSE-133). Honest
    NO-HISTORY state when nothing has been recorded."""
    by_cell = _drift_series_by_cell()

    if not by_cell:
        return render_box(
            header=box_header("DRIFT MONITORS", "detection-rate history"),
            accent_color="var(--text-3)",
            headline=headline_stat_card(
                label="WORST-CELL DELTA · 7-DAY", value="N/A",
                delta="no run history recorded", traj="→ awaiting runs",
                meta_left=f"{len(packs)} cells · 0 runs", meta_right=NOW, progress_pct=0,
            ),
            body=render_severity_narrative(
                "WATCH",
                "<strong>What changed:</strong> no detection-metric history has been "
                "recorded yet. <strong>For whom:</strong> the drift monitor has no "
                "time-series to evaluate. <strong>Evidence:</strong> "
                "marts/cell_metrics_history.jsonl is empty. <strong>Response:</strong> "
                "run <code>py -m pulse.serving.run_history --backfill 14</code> (synthetic "
                "scenario), or let the pipeline record runs in production.",
            ),
            footer=box_footer("run-history v0.1", NOW, live=True,
                              note="pulse.serving.run_history · no runs recorded yet"),
        )

    drift_rows: list[str] = []
    worst_delta = 0
    worst_pack: dict | None = None
    worst_series: list[int] = []
    for p in packs[:5]:
        series_pp = by_cell.get((p["hypothesis"] or {}).get("cell_id"))
        if not series_pp:
            continue
        row_html, delta = _build_drift_row(p, series_pp)
        drift_rows.append(row_html)
        if abs(delta) > abs(worst_delta):
            worst_delta, worst_pack, worst_series = delta, p, series_pp

    n_runs = max((len(v) for v in by_cell.values()), default=0)
    narrative = render_severity_narrative(
        classify_drift_severity(worst_delta),
        drift_narrative(worst_pack["meta"]["pack_name"], worst_series) if worst_pack
        else "<strong>What changed:</strong> no significant drift across recorded runs.",
    )
    drift_filter = render_filter_strip(
        scope="drift",
        options=[("all", "ALL"), ("ACUTE", "ACUTE only"),
                 ("ESCALATE", "≥ESCALATE"), ("WATCH", "≥WATCH")],
    )
    return render_box(
        header=box_header("DRIFT MONITORS", f"detection-rate · {n_runs} runs"),
        accent_color="var(--blue)",
        headline=headline_stat_card(
            label="WORST-CELL DELTA · 7-DAY",
            value=f"{worst_delta:+d}pp",
            delta=f"on cell {(worst_pack['hypothesis'] or {}).get('cell_id','?') if worst_pack else '—'}",
            traj="↘ DRIFTING" if abs(worst_delta) > 5 else "→ STABLE",
            meta_left=f"{len(by_cell)} cells · {n_runs} runs recorded",
            meta_right=NOW,
            progress_pct=min(100, abs(worst_delta) * 10),
        ),
        body=drift_filter + _render_drift_legend_strip() + "".join(drift_rows) + narrative,
        footer=box_footer(
            "run-history v0.1", NOW, live=True,
            note="real per-cell detection-rate history · pulse.serving.run_history",
        ),
    )


def _fairness_history_by_cell() -> dict[int, list[dict]]:
    """{cell_id: [fairness verdict rows], chronological} from run_history
    (PULSE-134). Fail-soft → {} so the pane renders the honest NO-HISTORY state."""
    by_cell: dict[int, list[dict]] = {}
    try:
        from pulse.serving.run_history import read_fairness_history
        rows = read_fairness_history()
    except Exception:
        import logging
        logging.exception("read_fairness_history failed — FAIRNESS pane renders NO HISTORY")
        rows = []
    for r in rows:
        by_cell.setdefault(r["cell_id"], []).append(r)
    return by_cell


def render_fairness_pane(packs: list[dict]) -> str:
    """Pane 2 — FAIRNESS RE-CHECK. REAL per-run demographic-parity history
    (PULSE-134 run_history.read_fairness_history): worst-cell ratio vs the 4/5ths
    floor + disparate-impact count + an over-time trend sparkline. equalised_odds +
    calibration declared-not-run. Honest NO-HISTORY state when nothing recorded."""
    FLOOR = 0.8  # 4/5ths (adverse-impact) rule on the demographic-parity ratio
    _not_run_tiles = [
        ("—", "EQ ODDS", "declared · not run", "var(--text-3)"),
        ("—", "CALIBRATION", "declared · not run", "var(--text-3)"),
    ]
    by_cell = _fairness_history_by_cell()
    latest = {cid: rows[-1] for cid, rows in by_cell.items() if rows and rows[-1].get("assessed")}

    if not latest:
        return render_box(
            header=box_header("FAIRNESS RE-CHECK", "demographic-parity over time"),
            accent_color="var(--text-3)",
            headline=headline_stat_card(
                label="WORST DEMOGRAPHIC-PARITY", value="N/A",
                delta="no fairness history recorded", traj="→ awaiting runs",
                meta_left=f"0 of {len(packs)} cells assessed", meta_right=NOW, progress_pct=0,
            ),
            body=body_kpi_tiles(
                [("N/A", "DEM PARITY", "needs mixed-cohort runs", "var(--text-3)")] + _not_run_tiles
            ) + render_severity_narrative(
                "WATCH",
                "<strong>What changed:</strong> no fairness history recorded yet. "
                "<strong>For whom:</strong> the over_50 protected split. "
                "<strong>Evidence:</strong> marts/fairness_history.jsonl is empty. "
                "<strong>Response:</strong> run <code>py -m pulse.serving.run_history "
                "--backfill 14</code> (synthetic scenario), or production records per-run "
                "fairness. equalised_odds + calibration need labels (not run at v1).",
            ),
            footer=box_footer("convergence v0.1", NOW, live=True,
                              note="pulse.serving.run_history fairness · no runs recorded yet"),
        )

    worst_cid = min(latest, key=lambda c: latest[c]["demographic_parity_ratio"] or 1.0)
    worst = latest[worst_cid]
    worst_ratio = worst["demographic_parity_ratio"] or 0.0
    n_assessed = len(latest)
    n_flagged = sum(1 for v in latest.values() if v.get("disparate_impact"))
    n_runs = max((len(v) for v in by_cell.values()), default=0)
    ratio_series = [round((r.get("demographic_parity_ratio") or 0.0) * 100)
                    for r in by_cell[worst_cid] if r.get("assessed")]
    dp_color = "var(--red)" if worst_ratio < FLOOR else "var(--green)"
    spark = (sparkline_svg(ratio_series, dp_color, width=240, height=28,
                           reference_value=FLOOR * 100)
             if len(ratio_series) >= 2 else "")
    p = worst.get("chi2_p_value")
    p_str = f"{p:.4f}" if p is not None else "n/a"
    sig = "significant" if (p is not None and p < 0.05) else "not significant"
    narrative = render_severity_narrative(
        classify_fairness_severity(n_flagged),
        (f"<strong>What changed:</strong> worst demographic-parity ratio is "
         f"{worst_ratio:.2f} on cell {worst_cid} (over_50 vs reference)"
         f"{' — outside the 4/5ths band (disparate impact)' if worst_ratio < FLOOR else ' — within the 4/5ths band'}, "
         f"across {len(ratio_series)} recorded runs. "
         f"<strong>For whom:</strong> the over_50 protected cohort. "
         f"<strong>Evidence:</strong> convergence.assess_fairness — chi² p={p_str} ({sig}). "
         f"<strong>Response:</strong> "
         f"{'hold deployment; MRM fairness re-review' if worst_ratio < FLOOR else 'no action — within tolerance'}."),
    )
    delta_str = (
        f'<span style="color:{dp_color};" class="threshold-token" '
        f'title="{_e(FAIRNESS_METRIC_RULES["demographic_parity"])}">'
        f'{"↓ disparate impact" if worst_ratio < FLOOR else "↑ within 4/5ths"} '
        f'({worst_ratio:.2f} vs {FLOOR:.2f})</span>'
    )
    return render_box(
        header=box_header("FAIRNESS RE-CHECK", f"demographic-parity · {n_runs} runs"),
        accent_color="var(--amber)" if n_flagged else "var(--green)",
        headline=headline_stat_card(
            label="WORST DEMOGRAPHIC-PARITY",
            value=f"{worst_ratio:.2f}",
            delta=delta_str,
            traj="↘ DISPARATE IMPACT" if worst_ratio < FLOOR else "→ WITHIN 4/5THS",
            meta_left=f"{n_assessed} assessed · {n_flagged} flagged · {n_runs} runs",
            meta_right=NOW,
            progress_pct=int(min(100, worst_ratio * 100)),
        ),
        body=(f'<div class="drift-cell-spark">{spark}</div>' if spark else "")
        + body_kpi_tiles(
            [(f"{n_flagged}/{n_assessed}", "DEM PARITY", "disparate impact",
              "var(--red)" if n_flagged else "var(--green)")] + _not_run_tiles
        ) + narrative + body_lines([
            ("Method: pulse.convergence.assess_fairness over per-run history (PULSE-134); "
             "equalised_odds + calibration declared, not run at v1", "var(--text-3)"),
        ]),
        footer=box_footer(
            "convergence v0.1", NOW, live=True,
            note="real per-run fairness history · demographic-parity ratio + chi² · "
                 "pulse.serving.run_history",
        ),
    )


def _lineage_report() -> dict:
    """REAL global decision-run lineage verdict (fail-soft).

    pulse.decision.lineage seals ONE hash-chain per pipeline run — there are no
    per-pack chains — so this pane verifies that global chain via
    verify_decision_lineage() over marts/decisions_lineage.jsonl. Fail-soft: an
    import/IO error yields an honest 'verify_error' verdict, never fabricated
    health. The previous per-pack VERIFIED/BROKEN table (with a fabricated ~10%
    breakage rate) is gone — there were never per-pack chains to break."""
    try:
        from pulse.decision.lineage import verify_decision_lineage
        return verify_decision_lineage()
    except Exception:
        import logging
        logging.exception("verify_decision_lineage failed — LINEAGE pane renders UNAVAILABLE")
        return {"ok": False, "reason": "verify_error", "total_rows": 0, "violations": 0}


def render_lineage_pane(packs: list[dict]) -> str:
    """Pane 3 — LINEAGE VERIFIER. The REAL global decision-run hash-chain
    (pulse.decision.lineage.verify_decision_lineage), not a fabricated per-pack
    table. Honest states: VERIFIED (clean run) / BROKEN (violations) / NO RUN
    (no chain sealed yet) / UNAVAILABLE (verify error)."""
    report = _lineage_report()
    total_rows = int(report.get("total_rows", 0) or 0)
    viols = report.get("violations")
    n_viol = len(viols) if isinstance(viols, list) else int(viols or 0)
    reason = report.get("reason")
    head = report.get("head_row_hash")
    head_short = short_hash(head) if head else "—"

    if reason == "no_lineage_log":
        status, color, sev, pct = "NO RUN", "var(--text-3)", "WATCH", 0
        head_delta = "no decision-lineage chain sealed yet"
        traj = "→ awaiting run"
        narrative_body = (
            "<strong>What changed:</strong> no pipeline run has sealed a decision-"
            "lineage chain yet. <strong>For whom:</strong> a reviewer or regulator "
            "querying provenance has no chain to verify. <strong>Evidence:</strong> "
            "marts/decisions_lineage.jsonl is absent. <strong>Response:</strong> run "
            "pulse.pipeline.run to generate + seal the chain, then re-verify."
        )
    elif report.get("ok"):
        status, color, sev, pct = "VERIFIED", "var(--green)", "NOMINAL", 100
        head_delta = f"{total_rows} rows · head {head_short}"
        traj = "→ INTACT"
        narrative_body = (
            f"<strong>What changed:</strong> the decision-run lineage chain verified "
            f"clean across {total_rows} hash-linked rows. <strong>For whom:</strong> any "
            f"reviewer or regulator can re-derive every Action tier from the inputs it "
            f"claims. <strong>Evidence:</strong> pulse.lineage.verify_chain — 0 "
            f"violations, head {head_short}. <strong>Response:</strong> none; promotion-safe."
        )
    else:
        status, color, sev, pct = "BROKEN", "var(--red)", "ACUTE", 50
        head_delta = f"{n_viol} violation{'s' if n_viol != 1 else ''} · {total_rows} rows"
        traj = "↘ INTEGRITY FAILURE"
        narrative_body = (
            f"<strong>What changed:</strong> the decision-run lineage chain reported "
            f"{n_viol} integrity violation{'s' if n_viol != 1 else ''}. <strong>For whom:"
            f"</strong> any reviewer or regulator querying these decisions gets a chain-"
            f"integrity failure. <strong>Evidence:</strong> pulse.lineage.verify_chain "
            f"violations. <strong>Response:</strong> trace + reseal anchors before promotion."
        )

    violation_detail = ""
    if isinstance(viols, list) and viols:
        violation_detail = body_lines([
            (f'{_e(str(v.get("kind", "?")))} · {_e(str(v.get("lineage_id", "?"))[:12])}',
             "var(--red)")
            for v in viols[:6]
        ])

    return render_box(
        header=box_header("LINEAGE VERIFIER", "global decision-run chain"),
        accent_color=color,
        headline=headline_stat_card(
            label="DECISION-CHAIN INTEGRITY",
            value=status,
            delta=head_delta,
            traj=traj,
            meta_left="hash-anchored · regulator-defensible · one chain per run",
            meta_right=NOW,
            progress_pct=pct,
        ),
        body=violation_detail + render_severity_narrative(sev, narrative_body),
        footer=box_footer(
            "lineage v0.1", NOW, live=True,
            note="pulse.decision.lineage.verify_decision_lineage · global decision-run "
                 "chain (not per-pack)",
        ),
    )


def _render_synthesis_action_cluster(cell: str) -> str:
    """HOL-50: extracted from render_synthesis_pane. PENDING-row 3-button
    cluster [Attest][Challenge][Defer]. HOL-42 governance affordance."""
    return (
        f'<td><span class="govern-actions" data-cell-id="{cell}">'
        f'<button class="govern-action-btn govern-action-btn--attest" '
        f'data-action="attest" data-cell-id="{cell}" type="button">Attest</button>'
        f'<button class="govern-action-btn govern-action-btn--challenge" '
        f'data-action="challenge" data-cell-id="{cell}" type="button">Challenge</button>'
        f'<button class="govern-action-btn govern-action-btn--defer" '
        f'data-action="defer" data-cell-id="{cell}" type="button">Defer</button>'
        f'</span></td>'
    )


def _build_synthesis_row(p: dict, g: dict) -> str:
    """HOL-50: extracted from render_synthesis_pane. One SYNTHESIS table
    <tr> with cell link, value tier + mode + attestation badges
    (threshold-tooltip'd), reviewer + date columns, and the actionable
    PENDING action cluster (or "—" placeholder for resolved rows).
    HOL-57: Value tier column added so the reviewer can prioritise
    high-value packs in the pending queue."""
    h = p["hypothesis"] or {}
    cell = _e(str(h.get("cell_id", "?")))
    # HOL-42: PENDING rows get inline action cluster; resolved rows show "—"
    if g["is_actionable"]:
        actions_cell = _render_synthesis_action_cluster(cell)
    else:
        actions_cell = '<td><span class="govern-actions-none">—</span></td>'
    # HOL-39 + HOL-45 row attrs: drill-through + filter + sort + tooltips
    row_sev = attestation_severity(g["attestation"])
    att_tip = ATTESTATION_RULES.get(g["attestation"], "")
    mode_tip = SYNTHESIS_RULES.get(g["synthesis_mode"], "")  # may be empty
    # HOL-57: pull commercial signal off the engine PlacementCell
    signal = _commercial_signal_for_pack(p)
    value_color = _VALUE_COLORS.get(signal["value_tier"], "#5A6E7A")
    # HOL-57 + no-pound-pandora: friction-volume is the primary unit on the
    # row; £ scaffold (if any) goes in a tooltip, never as the cell text.
    volume_text = signal["volume_label"] or '<span class="govern-lift-pending">—</span>'
    scaffold_tip = signal.get("scaffold") or ""
    return (
        f'<tr class="cell-row pane-filterable" data-cell-id="{cell}" '
        f'data-row-state="pending" data-severity="{row_sev}" '
        f'data-filter-scope="synthesis" '
        f'data-sort-cell="{cell}" '
        f'data-sort-value="{_e(signal["value_tier"])}" '
        f'data-sort-mode="{_e(g["synthesis_mode"])}" '
        f'data-sort-attestation="{_e(g["attestation"])}" '
        f'data-sort-reviewed="{_e(g["reviewed_date"])}">'
        f'<td><a class="cell-link" href="#cell-{cell}" data-cell-id="{cell}">cell {cell}</a></td>'
        f'<td><span class="govern-badge govern-badge--value" '
        f'style="color:{value_color};">{_e(signal["value_tier"])}</span> '
        f'<span class="govern-lift" title="{_e(scaffold_tip)}">{volume_text}</span></td>'
        f'<td><span class="govern-badge threshold-token" '
        f'style="color:{g["mode_color"]};" title="{_e(mode_tip)}">'
        f'{g["synthesis_mode"]}</span></td>'
        f'<td><span class="govern-badge threshold-token" '
        f'style="color:{g["att_color"]};" title="{_e(att_tip)}">'
        f'{g["attestation"]}</span></td>'
        f'<td>{_e(g["reviewer"])}</td>'
        f'<td>{_e(g["reviewed_date"])}</td>'
        f'{actions_cell}'
        f'</tr>'
    )


def render_synthesis_pane(packs: list[dict]) -> str:
    """Pane 4 — SYNTHESIS-MODE GOVERNANCE. Per-pack table of synthesis-mode +
    attestation status. Critical before any LLM_AUGMENTED prod enable.
    HOL-50: row + action-cluster construction extracted to helpers."""
    rows = [(p, synthesis_governance(p)) for p in packs]
    n_llm = sum(1 for _, g in rows if g["synthesis_mode"] == "LLM_AUGMENTED")
    n_det = len(packs) - n_llm
    n_certified = sum(1 for _, g in rows if g["attestation"] == "certified")

    n_actionable = sum(1 for _, g in rows[:6] if g["is_actionable"])
    table_rows = [_build_synthesis_row(p, g) for p, g in rows[:6]]
    # HOL-45 — sortable column headers; data-sort-key matches the
    # data-sort-* attrs on rows, JS handler reorders tbody children.
    table_html = (
        '<table class="govern-table" data-sortable-table="synthesis">'
        '<thead><tr>'
        '<th class="sortable" data-sort-key="cell">cell</th>'
        '<th class="sortable" data-sort-key="value">value · sessions/wk</th>'
        '<th class="sortable" data-sort-key="mode">mode</th>'
        '<th class="sortable" data-sort-key="attestation">attestation</th>'
        '<th>reviewer</th>'
        '<th class="sortable" data-sort-key="reviewed">reviewed</th>'
        '<th>actions</th>'
        '</tr></thead>'
        f'<tbody>{"".join(table_rows)}</tbody>'
        '</table>'
        # HOL-42: session log tray — JS updates count + last action
        f'<div class="govern-session-log" id="govern-session-log" '
        f'data-pending="{n_actionable}">'
        f'session log · 0 decisions recorded · '
        f'<span class="govern-session-log-count">{n_actionable}</span> pending'
        f'</div>'
    )

    # HOL-40 — severity driven by LLM_AUGMENTED count
    gate_note = render_severity_narrative(
        classify_synthesis_severity(n_llm),
        (f'<strong>v1 immutability gate:</strong> {n_llm} LLM_AUGMENTED pack'
         f'{"s" if n_llm != 1 else ""} flagged. Per pulse/synthesis/SYNTHESIS_DESIGN.md '
         f'the v1 gate refuses synthesis_mode: llm_augmented in decision packs. '
         f'<strong>Response:</strong> '
         f'hold packs out of prod; route through governance review before enabling.')
    )

    # HOL-45 — pane filter strip for SYNTHESIS
    synth_filter = render_filter_strip(
        scope="synthesis",
        options=[("all", "ALL"), ("PENDING", "PENDING only")],
    )

    return render_box(
        header=box_header("SYNTHESIS GOVERNANCE", "per-pack attestation"),
        accent_color="var(--green)" if n_llm == 0 else "var(--amber)",
        headline=headline_chip_strip([
            (str(n_det),       "DETERMINISTIC", "var(--green)"),
            (str(n_llm),       "LLM_AUGMENTED", "var(--red)"),
            (str(n_certified), "CERTIFIED",     "var(--teal)"),
        ]),
        body=synth_filter + table_html + gate_note,
        footer=box_footer(
            "synthesis v0.1", NOW, live=True,
            note="synthesis_mode read from pack metadata · v1 deterministic-locked · "
                 "no independent MRM assessment yet",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Top nav + masthead (same identity strip as Workspace + Home)
# ─────────────────────────────────────────────────────────────────────────────

def render_topnav() -> str:
    return f"""
<header class="holter-topnav">
  <span class="brand-logo">Cerno</span>
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


# ─────────────────────────────────────────────────────────────────────────────
# HOL-57 — Commercial signal-back on the decision frame.
#
# Surfaces what the MRM reviewer's decision actually clears commercially.
# Pulls Value tier + sized monthly lift from the engine's PlacementCell
# (which carries ValueScore per PULSE-107). Renders an "Unblocks:" affordance
# under the trigger sentence + an enriched APPROVE-FOR-PROD confirmation.
# ─────────────────────────────────────────────────────────────────────────────


def _commercial_signal_for_pack(p: dict) -> dict:
    """Pull the commercial signal off the engine's PlacementCell for this pack.

    Returns a dict with `value_tier`, `journey_id`, friction-volume signal
    (`volume_label` — the PRIMARY unit, sessions/wk recoverable) +
    `sessions_per_week` for sorting, and `scaffold` (the optional SECONDARY
    £ framing that names its own per-session ARPU assumption). Falls back to
    defaults when the engine bridge can't resolve the pack (renders PENDING).

    No bare £: per no-pound-pandora, surfaces lead with friction volume."""
    cell = get_pack_cell(p["meta"]["pack_name"])
    if cell is None:
        return {
            "value_tier": "PENDING",
            "volume_label": None,
            "sessions_per_week": 0,
            "scaffold": None,
            "journey_id": "—",
        }
    return {
        "value_tier": cell.value.tier,
        "volume_label": friction_volume_headline(cell.value, period="week"),
        "sessions_per_week": getattr(
            cell.value, "recoverable_sessions_per_week", 0) or 0,
        "scaffold": commercial_scaffold(cell.value),
        "journey_id": cell.journey_id,
    }


_COMMERCIAL_TIERS = {"COMMERCIAL-OPPORTUNITY", "SIGNIFICANT"}


def render_unblocks_strip(packs: list[dict]) -> str:
    """List the COMMERCIAL-OPPORTUNITY / SIGNIFICANT packs gated by the
    reviewer's pending workflow, sized lift descending.

    Audit framing: an MRM reviewer can't see the commercial cost of holding
    a model in committee without this affordance. HOL-57 makes the gate
    transparent to the reviewer.
    """
    signals: list[tuple[dict, dict]] = []
    for p in packs:
        sig = _commercial_signal_for_pack(p)
        if sig["value_tier"] in _COMMERCIAL_TIERS:
            signals.append((p, sig))

    if not signals:
        return (
            '<div class="mlops-unblocks-strip mlops-unblocks-strip--empty">'
            '<span class="mlops-unblocks-label">UNBLOCKS</span>'
            '<span class="mlops-unblocks-empty">'
            'no commercial-tier packs currently gated by this workflow'
            '</span>'
            '</div>'
        )

    # Sort: friction volume (sessions/wk) desc — the primary commercial unit.
    # No £ in the sort key (no-pound-pandora).
    signals.sort(
        key=lambda ps: (
            -(ps[1]["sessions_per_week"] or 0),
            ps[0]["meta"]["pack_name"],
        )
    )

    # Aggregate friction volume held by the workflow — the headline unit is
    # sessions/week, NOT £. This is what the reviewer is actually holding
    # when they route a model to committee.
    total_sessions = sum(s["sessions_per_week"] for _, s in signals)

    items_html: list[str] = []
    for p, s in signals[:4]:  # cap at 4 to keep the strip readable
        tier = s["value_tier"]
        tier_color = _VALUE_COLORS.get(tier, "#5A6E7A")
        volume_text = s["volume_label"] or '<span class="mlops-unblocks-pending">vol. pending</span>'
        # £ scaffold (if any) lives in the title attr — secondary, on hover.
        scaffold_tip = s.get("scaffold") or ""
        items_html.append(
            f'<li class="mlops-unblocks-item" title="{_e(scaffold_tip)}">'
            f'<span class="mlops-unblocks-tier" style="color:{tier_color};">{tier}</span>'
            f'<span class="mlops-unblocks-journey">{_e(s["journey_id"])}</span>'
            f'<span class="mlops-unblocks-lift">{volume_text}</span>'
            f'</li>'
        )

    n_more = max(0, len(signals) - 4)
    more_html = (
        f'<li class="mlops-unblocks-more">+ {n_more} more</li>' if n_more else ''
    )

    headline = (
        f' · <span class="mlops-unblocks-total">~{total_sessions:,} sessions/wk '
        f'held by this workflow</span>'
        if total_sessions else ''
    )

    return (
        f'<div class="mlops-unblocks-strip">'
        f'<span class="mlops-unblocks-label">UNBLOCKS</span>'
        f'<span class="mlops-unblocks-context">{len(signals)} commercial-tier pack'
        f'{"s" if len(signals) != 1 else ""} gated{headline}</span>'
        f'<ul class="mlops-unblocks-list">{"".join(items_html)}{more_html}</ul>'
        f'</div>'
    )


def render_decision_frame(packs: list[dict]) -> str:
    """HOL-44 — Top-of-page decision frame. Replaces the bare procurement-gate
    masthead with a Young/Burt/Rock-aligned "why you are here today" framing.

    Composition (matches ticket acceptance):
      - Trigger sentence — computed from worst-cell drift + flagged count
      - Unblocks strip (HOL-57) — commercial signal-back; shows what packs
        are gated by this workflow and total sessions/week held (friction
        volume, NOT £ — see no-pound-pandora)
      - Decision frame — 3-button cluster [Approve 14d / Committee / Retrain]
      - Session badge — reviewer + session start + decisions logged
    """
    # Compute trigger from REAL per-cell drift history (worst-cell pack)
    worst_delta = 0
    worst_pack = None
    _drift_by_cell = _drift_series_by_cell()
    for p in packs[:5]:
        series_pp = _drift_by_cell.get((p["hypothesis"] or {}).get("cell_id"))
        if not series_pp:
            continue
        delta = series_pp[-1] - (series_pp[-8] if len(series_pp) >= 8 else series_pp[0])
        if abs(delta) > abs(worst_delta):
            worst_delta = delta
            worst_pack = p

    sev = classify_drift_severity(worst_delta)  # NOMINAL/WATCH/ESCALATE/ACUTE
    sev_color = {
        "ACUTE":    "var(--red)",
        "ESCALATE": "var(--amber)",
        "WATCH":    "var(--amber)",
        "NOMINAL":  "var(--green)",
    }[sev]
    frame_mod = f"mlops-decision-frame--{sev.lower()}" if sev in ("ACUTE", "ESCALATE") else ""

    pack_name = worst_pack["meta"]["pack_name"] if worst_pack else "—"
    cell_id = (worst_pack["hypothesis"] or {}).get("cell_id", "?") if worst_pack else "?"

    # Count cells the latest fairness-history verdict flags for disparate impact
    # (matches the FAIRNESS pane; sourced from real per-run history, PULSE-134).
    _fair_latest = _fairness_history_by_cell()
    cohorts_below = sum(
        1 for rows in _fair_latest.values()
        if rows and rows[-1].get("disparate_impact")
    )

    trigger = (
        f'<span class="mlops-decision-trigger-tag" style="color:{sev_color};">{sev}</span>'
        f'Model <span class="mlops-decision-trigger-pack">{_e(pack_name)}</span> '
        f'manual re-check flagged <strong>{sev}</strong> — '
        f'drift {worst_delta:+d}pp on cell {_e(str(cell_id))} · '
        f'{cohorts_below} cell{"s" if cohorts_below != 1 else ""} flagged for '
        f'demographic-parity disparate impact.'
    )

    today = _dt.date.today().strftime("%a · %d %b")
    session_start = NOW

    # HOL-57 — what this model gates commercially. Surfaced under the trigger
    # so the reviewer sees the cost-of-hold before pressing a workflow button.
    unblocks_html = render_unblocks_strip(packs)

    # HOL-57 + no-pound-pandora — APPROVE FOR PROD 14D carries the worst-pack's
    # friction-volume signal (sessions/wk), NOT £. Christensen's hard-gate:
    # the regulated-approval audit confirmation must record customer-exposure
    # units, never a raw £ figure (which would make money the unit-of-record
    # for a customer-protection decision).
    worst_pack_signal = (
        _commercial_signal_for_pack(worst_pack)
        if worst_pack
        else {"value_tier": "—", "volume_label": None, "journey_id": "—"}
    )
    # Strip the trailing "recoverable" word for the compact button attr.
    _vol = worst_pack_signal.get("volume_label") or ""
    approve_volume_attr = _e(_vol.replace(" recoverable", ""), quote=True)
    approve_journey_attr = _e(worst_pack_signal["journey_id"], quote=True)
    approve_tier_attr = _e(worst_pack_signal["value_tier"], quote=True)

    return f'''
<div class="mlops-decision-frame {frame_mod}">
  <div class="mlops-decision-trigger">{trigger}</div>
  {unblocks_html}
  <div class="mlops-decision-actions">
    <button class="mlops-decision-btn mlops-decision-btn--approve"
            data-decision="approve_14d"
            data-pack-journey="{approve_journey_attr}"
            data-pack-tier="{approve_tier_attr}"
            data-pack-volume="{approve_volume_attr}"
            type="button">Approve for prod · 14d</button>
    <button class="mlops-decision-btn mlops-decision-btn--committee"
            data-decision="route_committee" type="button">Route to committee</button>
    <button class="mlops-decision-btn mlops-decision-btn--retrain"
            data-decision="request_retrain" type="button">Request retraining</button>
  </div>
  <div class="mlops-decision-session">
    <span>reviewer · <span class="mlops-decision-session-reviewer">HA · Hussain Ahmed</span></span>
    <span>session · {today} · started {session_start}</span>
    <span>decisions · <span class="mlops-decision-session-count" id="mlops-decision-count">0</span></span>
    <span class="mlops-decision-session-confirm" id="mlops-decision-confirm"></span>
  </div>
</div>
<div class="mlops-dateline">MLOps Console · {today} · {session_start}</div>'''


# ─────────────────────────────────────────────────────────────────────────────
# Page composition
# ─────────────────────────────────────────────────────────────────────────────

def render_page() -> str:
    packs = discover_packs()

    panes = (
        render_drift_pane(packs)
        + render_fairness_pane(packs)
        + render_lineage_pane(packs)
        + render_synthesis_pane(packs)
    )

    # HOL-35: CSS now lives in _shared (was in render_holter). MLOps no
    # longer imports anything from render_holter — Cannon's condition met.
    from holter.preview._shared import CSS as WORKSPACE_CSS

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MLOps Console — procurement gate</title>
<style>{WORKSPACE_CSS}{CSS_EXTRA}</style>
</head>
<body>
{render_topnav()}
<main class="mlops-page" data-window="14d">
{render_decision_frame(packs)}
<div class="mlops-grid">{panes}</div>
</main>
<script>
// HOL-39 — drill-through coupling: clicking a cell-id link toggles
// .cell-row-highlighted on EVERY .cell-row[data-cell-id="N"] across all
// 4 panes simultaneously. Vanilla JS, no library, ~15 lines.
(function () {{
  function clearAll() {{
    document.querySelectorAll('.cell-row-highlighted')
      .forEach(el => el.classList.remove('cell-row-highlighted'));
  }}
  function highlight(cellId) {{
    document.querySelectorAll('.cell-row[data-cell-id="' + cellId + '"]')
      .forEach(el => el.classList.add('cell-row-highlighted'));
  }}
  document.querySelectorAll('.cell-link').forEach(link => {{
    link.addEventListener('click', function (ev) {{
      ev.preventDefault();
      const cellId = this.getAttribute('data-cell-id');
      const wasHighlighted = document.querySelector(
        '.cell-row.cell-row-highlighted[data-cell-id="' + cellId + '"]'
      );
      clearAll();
      if (!wasHighlighted) highlight(cellId);
    }});
  }});
  // Click anywhere else clears highlight
  document.addEventListener('click', function (ev) {{
    if (!ev.target.closest('.cell-link') && !ev.target.closest('.cell-row')) {{
      clearAll();
    }}
  }});
}})();

// HOL-42 + HOL-44 — In-session event log. HOL-51 (Hickey): both
// cell-scope (Attest/Challenge/Defer) and model-scope (Approve/Committee/
// Retrain) writers share a single envelope so the eventual engine
// consumer doesn't have to demux on scope.
//
//   {{ scope: 'cell' | 'model',
//     target: cell_id | model_name,
//     action: string,
//     reason: string | null,
//     reviewer: string,
//     timestamp: ISO-8601 }}
window.holterEventLog = window.holterEventLog || [];
window.holterRecordEvent = function (scope, target, action, reason) {{
  const event = {{
    scope: scope,
    target: target,
    action: action,
    reason: reason || null,
    reviewer: 'HA',
    timestamp: new Date().toISOString(),
  }};
  window.holterEventLog.push(event);
  console.log('[holter-event]', event);
  return event;
}};

(function () {{
  function recordAction(cellId, action, reason) {{
    return window.holterRecordEvent('cell', cellId, action, reason);
  }}

  function resolveRow(cellId, action) {{
    const row = document.querySelector(
      '.govern-table tr.cell-row[data-cell-id="' + cellId + '"]'
    );
    if (!row) return;
    row.setAttribute('data-row-state', action);
    row.classList.add('govern-row--resolved');
    const actionsCell = row.querySelector('td:last-child');
    if (actionsCell) {{
      actionsCell.innerHTML = '<span class="govern-resolved-badge ' +
        'govern-resolved-badge--' + action + 'ed">' +
        action.toUpperCase() + 'ED</span>';
    }}
  }}

  function updateSessionLog() {{
    const log = document.getElementById('govern-session-log');
    if (!log) return;
    // HOL-51: count only cell-scope events for the cell-scope tray;
    // model-scope events are tracked separately by the decision frame.
    const cellEvents = window.holterEventLog.filter(e => e.scope === 'cell');
    const n = cellEvents.length;
    const initialPending = parseInt(log.getAttribute('data-pending'), 10);
    const stillPending = Math.max(0, initialPending - n);
    const last = n ? cellEvents[n - 1] : null;
    if (n === 0) {{
      log.innerHTML = 'session log · 0 decisions recorded · ' +
        '<span class="govern-session-log-count">' + initialPending +
        '</span> pending';
    }} else {{
      log.classList.add('govern-session-log--active');
      log.innerHTML = 'session log · ' +
        '<span class="govern-session-log-count">' + n + '</span> recorded · ' +
        stillPending + ' pending · last: cell ' + last.target + ' ' +
        last.action.toUpperCase() +
        (last.reason ? ' (' + last.reason.slice(0, 30) + ')' : '');
    }}
  }}

  document.querySelectorAll('.govern-action-btn').forEach(btn => {{
    btn.addEventListener('click', function (ev) {{
      ev.preventDefault();
      ev.stopPropagation();
      const cellId = this.getAttribute('data-cell-id');
      const action = this.getAttribute('data-action');
      let reason = null;
      if (action === 'challenge') {{
        reason = window.prompt(
          'Challenge cell ' + cellId + ' — reason (cohort scope + concern):'
        );
        if (reason === null) return;  // user cancelled
      }}
      recordAction(cellId, action, reason);
      resolveRow(cellId, action);
      updateSessionLog();
    }});
  }});
}})();

// HOL-43 — Window scrubber [7d][14d][30d] + lineage hash click-to-expand
// chain ancestry. Three affordances, one gesture (reach into the data).
(function () {{
  // (b) Window scrubber: sets .mlops-page[data-window]; CSS hides/shows
  // the matching sparkline SVG variant. Default 14d (server-rendered
  // as an attribute on the <main> tag — JS no longer initialises).
  // HOL-52 (Hickey) — scoped to .mlops-page not document.body so a
  // co-mounted surface doesn't inherit our window state.
  const mlopsPage = document.querySelector('.mlops-page');
  document.querySelectorAll('.window-scrubber-btn').forEach(btn => {{
    btn.addEventListener('click', function (ev) {{
      ev.preventDefault();
      const win = this.getAttribute('data-window');
      if (mlopsPage) mlopsPage.setAttribute('data-window', win);
      document.querySelectorAll('.window-scrubber-btn').forEach(b =>
        b.setAttribute('data-active', b === this ? 'true' : 'false')
      );
    }});
  }});

  // (c) Hash click-to-expand: toggles .hash-chain--open on the matching
  // chain block. Cell-id key avoids opening the wrong chain in cases
  // where two rows somehow share a cell.
  document.querySelectorAll('a.hash-link[data-chain-toggle]').forEach(link => {{
    link.addEventListener('click', function (ev) {{
      ev.preventDefault();
      ev.stopPropagation();
      const cellId = this.getAttribute('data-chain-toggle');
      const chain = this.closest('.holter-box').querySelector(
        '.hash-chain[data-chain-for="' + cellId + '"]'
      );
      if (chain) chain.classList.toggle('hash-chain--open');
    }});
  }});
}})();

// HOL-44 — Top-of-page decision frame. Three model-scope decisions:
// Approve 14d / Route to committee / Request retraining.
// HOL-51: routes through the unified window.holterRecordEvent writer
// with scope='model' + target=<model_name>; same envelope as cell-scope.
(function () {{
  const countEl = document.getElementById('mlops-decision-count');
  const confirmEl = document.getElementById('mlops-decision-confirm');
  const frameEl = document.querySelector('.mlops-decision-frame');
  const modelName = frameEl
    ? (frameEl.querySelector('.mlops-decision-trigger-pack')
        ?.textContent.trim() || 'unknown_model')
    : 'unknown_model';
  let modelDecisions = 0;

  function flashConfirm(text) {{
    if (!confirmEl) return;
    confirmEl.textContent = '✓ ' + text;
    confirmEl.classList.add('mlops-decision-session-confirm--shown');
    setTimeout(() => {{
      confirmEl.classList.remove('mlops-decision-session-confirm--shown');
    }}, 2400);
  }}

  document.querySelectorAll('.mlops-decision-btn').forEach(btn => {{
    btn.addEventListener('click', function (ev) {{
      ev.preventDefault();
      // Torvalds PR-panel: double-click guard. Rapid-tap on "Route to
      // committee" was pushing two events to the log; unacceptable for
      // a sign-off workbench. data-locked latches on first click.
      if (this.getAttribute('data-locked') === 'true') return;
      this.setAttribute('data-locked', 'true');
      this.disabled = true;
      const decision = this.getAttribute('data-decision');
      window.holterRecordEvent('model', modelName, decision, null);
      modelDecisions += 1;
      if (countEl) countEl.textContent = modelDecisions;
      // HOL-57 + no-pound-pandora — APPROVE FOR PROD 14D records the
      // customer-exposure unit it clears (sessions/wk), NOT £. The audit
      // confirmation must speak in friction-volume — money is never the
      // unit-of-record for a customer-protection approval.
      if (decision === 'approve_14d') {{
        const journey = this.getAttribute('data-pack-journey') || '';
        const tier = this.getAttribute('data-pack-tier') || '';
        const volume = this.getAttribute('data-pack-volume') || '';
        if (journey && volume) {{
          flashConfirm('cleared ' + journey + ' for 14d prod · ' + volume + ' (' + tier + ')');
        }} else if (journey) {{
          flashConfirm('cleared ' + journey + ' for 14d prod · volume pending');
        }} else {{
          flashConfirm('approve 14d');
        }}
      }} else {{
        flashConfirm(decision.replace(/_/g, ' '));
      }}
    }});
  }});
}})();

// HOL-45 — pane-scoped severity filter + sortable SYNTHESIS columns.
// Filter: pane-filter-btn click sets active filter for that scope; hides
//   .pane-filterable[data-filter-scope=X] rows whose data-severity doesn't
//   pass the rule (ALL passes everything; ESCALATE passes ESCALATE+ACUTE).
// Sort: click a th.sortable to toggle asc/desc on data-sort-(key) attrs.
(function () {{
  const severityRank = {{ NOMINAL: 0, WATCH: 1, ESCALATE: 2, ACUTE: 3, PENDING: 1 }};

  function passesFilter(rowSev, filterVal) {{
    if (filterVal === 'all') return true;
    if (filterVal === 'PENDING') return rowSev === 'PENDING';
    // For severity filters: row passes if its severity is >= filter level
    const rs = severityRank[rowSev]; const fs = severityRank[filterVal];
    if (rs === undefined || fs === undefined) return rowSev === filterVal;
    return rs >= fs;
  }}

  function applyFilter(scope, filterVal) {{
    document.querySelectorAll(
      '.pane-filterable[data-filter-scope="' + scope + '"]'
    ).forEach(row => {{
      const rowSev = row.getAttribute('data-severity') || 'NOMINAL';
      row.classList.toggle('pane-row-hidden', !passesFilter(rowSev, filterVal));
    }});
  }}

  document.querySelectorAll('.pane-filter-btn').forEach(btn => {{
    btn.addEventListener('click', function (ev) {{
      ev.preventDefault();
      const scope = this.getAttribute('data-filter-scope');
      const val = this.getAttribute('data-filter-value');
      // Toggle active state for the scope's button group
      document.querySelectorAll(
        '.pane-filter-btn[data-filter-scope="' + scope + '"]'
      ).forEach(b => b.setAttribute(
        'data-active', b === this ? 'true' : 'false'
      ));
      applyFilter(scope, val);
    }});
  }});

  // Sort: synthesis table columns
  document.querySelectorAll('th.sortable[data-sort-key]').forEach(th => {{
    th.addEventListener('click', function (ev) {{
      ev.preventDefault();
      const table = this.closest('table');
      const key = this.getAttribute('data-sort-key');
      const current = this.getAttribute('data-sort');
      const next = current === 'asc' ? 'desc' : 'asc';
      // Reset other headers
      table.querySelectorAll('th.sortable').forEach(t =>
        t.removeAttribute('data-sort')
      );
      this.setAttribute('data-sort', next);
      // Reorder tbody
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {{
        const va = a.getAttribute('data-sort-' + key) || '';
        const vb = b.getAttribute('data-sort-' + key) || '';
        // Numeric if both parse as numbers
        const na = parseFloat(va); const nb = parseFloat(vb);
        const numeric = !isNaN(na) && !isNaN(nb);
        const cmp = numeric ? (na - nb) : va.localeCompare(vb);
        return next === 'asc' ? cmp : -cmp;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
}})();
</script>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Seed a synthetic drift scenario for the preview if no run-history exists yet
    # (production records real runs; this only fires on an empty store).
    try:
        from pulse.serving.run_history import (
            CELL_METRICS_HISTORY_LOG,
            FAIRNESS_HISTORY_LOG,
            backfill_demo_history,
        )
        if not CELL_METRICS_HISTORY_LOG.exists() or not FAIRNESS_HISTORY_LOG.exists():
            backfill_demo_history(14)  # seeds both drift + fairness scenarios (fresh)
    except Exception:
        import logging
        logging.exception("drift-history backfill skipped — DRIFT pane will show NO HISTORY")
    out = OUT_DIR / "index.html"
    html = render_page()
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
