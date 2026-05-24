"""HOL-74 — MLOps DRIFT pane wired to the real per-cell detection-rate history
(PULSE-133 run_history.read_cell_metrics_history), replacing the fabricated
cohort-overlay sparklines + hashed drift series.

The pane renders one real recall series per cell (run-history is per-cell, not
per-cohort). Two states: NO HISTORY (nothing recorded) and a real trend.

Run:  python -m pytest holter/tests/test_mlops_drift_wiring.py -q
"""

from __future__ import annotations

from holter.preview import render_mlops as M
from holter.preview._shared import discover_packs

_LOANS = "loans_apply_step3__dwell_after_error"  # cell 1


def _loans_pack() -> dict:
    return next(p for p in discover_packs() if p["meta"]["pack_name"] == _LOANS)


# ── _build_drift_row over a real series ───────────────────────────────────────

def test_build_drift_row_reports_decline():
    # declining recall 100 → 30 over 8 points → -70pp delta
    series_pp = [100, 90, 80, 70, 60, 50, 40, 30]
    html, delta = M._build_drift_row(_loans_pack(), series_pp)
    assert delta == -70
    assert "-70pp" in html
    assert "<svg" in html  # real sparkline rendered


def test_build_drift_row_short_series_ok():
    html, delta = M._build_drift_row(_loans_pack(), [88, 80])
    assert delta == -8           # today vs series[0] when < 8 points
    assert "drift-cell" in html


# ── pane: NO HISTORY vs real trend ────────────────────────────────────────────

def test_drift_pane_no_history_state(monkeypatch):
    monkeypatch.setattr(M, "_drift_series_by_cell", lambda: {})
    html = M.render_drift_pane(discover_packs())
    assert "no run history recorded" in html
    assert "pulse.serving.run_history --backfill" in html  # honest remediation
    # fabricated cohort overlay must not be emitted
    assert "30-day baseline" not in html


def test_drift_pane_renders_real_declining_trend(monkeypatch):
    # All cells declining 100 → 62 (discover_packs sorts alphabetically, so key
    # every cell to guarantee the first-5 packs have a series).
    series = {c: [100, 96, 92, 86, 80, 74, 68, 62] for c in range(1, 13)}
    monkeypatch.setattr(M, "_drift_series_by_cell", lambda: series)
    html = M.render_drift_pane(discover_packs())
    assert "-38pp" in html              # 62 - 100
    assert "runs recorded" in html
    assert "detection rate %" in html   # honest legend
    assert "<svg" in html


def test_mlops_page_renders_with_drift(monkeypatch):
    series = {1: [90, 85, 80, 75, 70, 65, 60, 55]}
    monkeypatch.setattr(M, "_drift_series_by_cell", lambda: series)
    html = M.render_page()
    assert "FINDING RELIABILITY" in html
    assert "WORST-CELL DELTA" in html
