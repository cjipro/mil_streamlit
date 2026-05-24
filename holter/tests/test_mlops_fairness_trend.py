"""HOL-75 — MLOps FAIRNESS pane wired to the per-run fairness history (PULSE-134
run_history.read_fairness_history): worst-cell demographic-parity ratio + the
over-time disparity trend, replacing the point-in-time "not assessable" state.

Run:  python -m pytest holter/tests/test_mlops_fairness_trend.py -q
"""

from __future__ import annotations

from holter.preview import render_mlops as M
from holter.preview._shared import discover_packs


def _verdict(ratio: float, disparate: bool, p: float = 0.001) -> dict:
    return {
        "cell_id": 1, "screen_id": "loans.apply.step3", "signature_id": "dwell_after_error",
        "assessed": True, "demographic_parity_ratio": ratio,
        "disparate_impact": disparate, "chi2_p_value": p,
        "protected_rate": ratio * 0.65, "reference_rate": 0.65,
    }


def test_fairness_pane_no_history(monkeypatch):
    monkeypatch.setattr(M, "_fairness_history_by_cell", lambda: {})
    html = M.render_fairness_pane(discover_packs())
    assert "no fairness history recorded" in html
    assert "declared · not run" in html              # EO + calibration honest
    assert "pulse.serving.run_history --backfill" in html


def test_fairness_pane_real_declining_trend(monkeypatch):
    series = {1: [_verdict(1.0, False, 0.9), _verdict(0.85, False, 0.2),
                  _verdict(0.70, True, 0.01), _verdict(0.60, True, 0.001)]}
    monkeypatch.setattr(M, "_fairness_history_by_cell", lambda: series)
    html = M.render_fairness_pane(discover_packs())
    assert "WORST DEMOGRAPHIC-PARITY" in html
    assert "0.60" in html                            # worst (latest) ratio
    assert "DISPARATE IMPACT" in html
    assert "<svg" in html                            # over-time trend sparkline
    assert "per-run fairness history" in html


def test_fairness_pane_within_band(monkeypatch):
    series = {1: [_verdict(1.0, False), _verdict(0.98, False)]}
    monkeypatch.setattr(M, "_fairness_history_by_cell", lambda: series)
    html = M.render_fairness_pane(discover_packs())
    assert "WITHIN 4/5THS" in html
    assert "DISPARATE IMPACT" not in html


def test_mlops_page_renders_with_fairness_trend(monkeypatch):
    series = {1: [_verdict(0.9, False), _verdict(0.7, True)]}
    monkeypatch.setattr(M, "_fairness_history_by_cell", lambda: series)
    html = M.render_page()
    assert "FAIRNESS RE-CHECK" in html
    assert "flagged for" in html                     # decision frame fairness count
