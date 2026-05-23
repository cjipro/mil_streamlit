"""Tests for the Cause-class analytics layer (PULSE-96).

The `payload` key set is the contract with the journey-altitude template
(`decision_packs/<pack>/templates/journey.md.j2`). These tests pin that contract,
determinism, and structural sanity — NOT specific values (the synthetic corpus
drives the numbers; the hand-authored `samples/journey.md` is illustrative, not a
value oracle).
"""

from __future__ import annotations

import pytest

from pulse.analytics.cause import build_analytic_outputs

_LOANS = "loans_apply_step3__dwell_after_error"
_NEGATIVE_CELL = "investments_premier_portfolio_overview__dwell_after_error"  # cell 10 = engineered negative

# Exactly the variables the journey.md.j2 template references.
_PAYLOAD_KEYS = {
    "pack", "screen_id", "signature_id", "window",
    "affected_sessions", "total_sessions", "affected_pct",
    "dwell_seconds_p50", "dwell_uplift_pct", "baseline_window_days",
    "p_value", "baseline_n", "p_value_threshold",
    "cohort_breakdown", "fairness_flag", "error_breakdown",
    "remediation_category", "remediation_rationale",
    "confidence_band", "confidence_low", "confidence_high", "brier_score",
}


def test_question_class_is_cause_and_keys_match_template_contract():
    out = build_analytic_outputs(_LOANS, sessions_per_cell=40)
    assert out.question_class == "cause"
    assert set(out.payload) == _PAYLOAD_KEYS
    # nested item contracts the template iterates over
    assert out.payload["pack"].get("pack_name")
    assert set(out.payload["window"]) == {"label"}
    for c in out.payload["cohort_breakdown"]:
        assert set(c) == {"label", "affected", "share_pct", "recall_x"}
    for e in out.payload["error_breakdown"]:
        assert set(e) == {"code", "count", "share_pct"}
    if out.payload["fairness_flag"] is not None:
        assert set(out.payload["fairness_flag"]) == {"disparity", "threshold"}


def test_deterministic():
    a = build_analytic_outputs(_LOANS, sessions_per_cell=40)
    b = build_analytic_outputs(_LOANS, sessions_per_cell=40)
    assert a.payload == b.payload


def test_structural_sanity():
    p = build_analytic_outputs(_LOANS, sessions_per_cell=40).payload
    assert 0 <= p["affected_sessions"] <= p["total_sessions"] > 0
    assert 0.0 <= p["affected_pct"] <= 100.0
    assert p["baseline_window_days"] == 28          # from rolling_28d_same_screen
    assert p["p_value_threshold"] == 0.01           # from hypothesis.yaml
    assert 0.0 <= p["brier_score"] <= 1.0
    assert p["confidence_low"] <= p["confidence_high"]
    assert p["confidence_band"] in {"high", "medium", "low"}
    if p["cohort_breakdown"]:
        assert sum(c["share_pct"] for c in p["cohort_breakdown"]) == pytest.approx(100.0, abs=0.5)
    if p["error_breakdown"]:
        assert sum(e["share_pct"] for e in p["error_breakdown"]) == pytest.approx(100.0, abs=0.5)
    # remediation category must come from the pack's allowed list (data-grounded, not invented)
    assert p["remediation_category"] in {"template_fix", "validation_message_clarity", "cohort_specific_routing"}


def test_negative_cell_does_not_crash_and_keys_hold():
    """The engineered-negative cell (few/zero fires) must still produce a full,
    well-formed payload — guards the zero-affected division paths."""
    p = build_analytic_outputs(_NEGATIVE_CELL, sessions_per_cell=40).payload
    assert set(p) == _PAYLOAD_KEYS
    assert p["affected_sessions"] <= p["total_sessions"]
    assert p["brier_score"] is None or 0.0 <= p["brier_score"] <= 1.0
