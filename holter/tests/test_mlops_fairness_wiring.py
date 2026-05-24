"""HOL-74 — MLOps FAIRNESS pane wired to the real PULSE-132 verdict
(convergence.assess_fairness: demographic-parity ratio + chi² + 4/5ths
disparate-impact), replacing the fabricated 3-score stub.

Two states are covered:
- NOT ASSESSABLE — the current synthetic single-cohort corpus (real verdict None).
- PRODUCTION (assessed) — monkeypatched so the demographic-parity path is tested
  without depending on a mixed-cohort corpus.

equalised_odds + calibration_by_cohort are declared in convergence/methods.yaml
but NOT run at v1 (need ground-truth labels) — the pane shows "declared, not run",
never a fabricated score.

Run:  python -m pytest holter/tests/test_mlops_fairness_wiring.py -q
"""

from __future__ import annotations

from holter.preview import render_mlops as M
from holter.preview._shared import discover_packs

_RUNNABLE = "loans_apply_step3__dwell_after_error"


class _StubOut:
    def __init__(self, payload: dict):
        self.payload = payload


_ASSESSED_VERDICT = {
    "assessed": True,
    "protected_group": "over_50",
    "protected_rate": 0.7,
    "reference_rate": 0.5,
    "disparity_ratio": 1.4,          # → parity score min(1.4, 0.714) = 0.7143 < 0.8 → disparate
    "parity_difference": 0.2,
    "chi2_statistic": 9.1,
    "chi2_p_value": 0.0025,
    "statistically_significant": True,
    "disparate_impact": True,
    "methods": ["demographic_parity", "chi_squared"],
    "reason": "ok",
}


# ── fairness_record reads the real verdict (no fabricated floats) ─────────────

def test_fairness_record_not_assessable_on_synthetic_corpus():
    f = M.fairness_record(_RUNNABLE)
    assert f["assessed"] is False                 # single-cohort cells → not assessable
    assert f["demographic_parity"] is None
    assert f["equalised_odds"] is None            # declared, not run at v1
    assert f["calibration_by_cohort"] is None
    assert f["deviation_alert"] is False


def test_fairness_record_assessed_shape(monkeypatch):
    monkeypatch.setattr(M, "get_pack_analytics",
                        lambda name: _StubOut({"fairness": _ASSESSED_VERDICT}))
    f = M.fairness_record("any")
    assert f["assessed"] is True
    # demographic_parity is the [0,1] parity SCORE derived from disparity_ratio
    assert f["demographic_parity"] == 0.7143
    assert f["demographic_parity"] < 0.8          # outside 4/5ths band
    assert f["disparate_impact"] is True
    assert f["deviation_alert"] is True           # = disparate_impact
    assert f["equalised_odds"] is None            # still not run
    assert f["chi2_p_value"] == 0.0025


# ── rendered pane: both states ────────────────────────────────────────────────

def test_fairness_pane_not_assessable_state():
    html = M.render_fairness_pane(discover_packs())
    assert "not assessable" in html
    assert "declared · not run" in html           # EO + calibration honest
    assert "DEMOGRAPHIC PARITY" in html
    # fabricated stub artefacts gone
    assert "WORST EQUALISED-ODDS" not in html
    assert "age_band · gender · ethnicity_band" not in html


def test_fairness_pane_production_path(monkeypatch):
    monkeypatch.setattr(M, "fairness_record", lambda name: dict(
        _ASSESSED_VERDICT,
        demographic_parity=0.71, equalised_odds=None, calibration_by_cohort=None,
        deviation_alert=True, cohort_dims=["over_50"],
    ))
    html = M.render_fairness_pane(discover_packs())
    assert "WORST DEMOGRAPHIC-PARITY" in html
    assert "0.71" in html
    assert "DISPARATE IMPACT" in html
    assert "declared · not run" in html            # EO/calibration still honest


def test_mlops_page_still_renders():
    html = M.render_page()
    assert "FAIRNESS RE-CHECK" in html
    assert "WORST EQUALISED-ODDS" not in html       # fabricated KPI gone everywhere
