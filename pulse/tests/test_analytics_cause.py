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
    "cohort_breakdown", "fairness_flag", "fairness", "error_breakdown",
    "remediation_category", "remediation_rationale",
    "confidence_band", "confidence_low", "confidence_high", "brier_score",
    # bank + signal altitude keys (PULSE-96 extension — real-data 3-altitude render)
    "primary_cohort", "recommendation_summary",
    "analytic", "evidence_sample", "evidence_sample_size", "audit",
    "engine_version", "detection_emitted_at", "lineage_anchor",
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


def test_bank_and_signal_altitude_keys():
    """PULSE-96 extension: the payload also carries the bank + signal altitude vars."""
    p = build_analytic_outputs(_LOANS, sessions_per_cell=40).payload
    # pack carries version + mode (signal altitude prints them)
    assert {"pack_name", "pack_version", "synthesis_mode"} <= set(p["pack"])
    # bank
    if p["primary_cohort"] is not None:
        assert set(p["primary_cohort"]) == {"label", "share_pct", "recall_disparity_x"}
    assert isinstance(p["recommendation_summary"], str) and p["recommendation_summary"]
    # signal
    assert p["analytic"]["method"] and "trigger" in p["analytic"]
    assert p["evidence_sample_size"] == len(p["evidence_sample"])
    for e in p["evidence_sample"]:
        assert set(e) == {"session_id", "dwell_seconds", "error_code", "cohort_tags", "p_value"}
        assert isinstance(e["cohort_tags"], list)
    assert isinstance(p["audit"]["bundle_required_fields"], list)
    assert p["engine_version"] and p["detection_emitted_at"]
    assert len(p["lineage_anchor"]) == 64  # sha256 hex


def test_fairness_verdict_is_real_convergence_output():
    """PULSE-132: payload['fairness'] is the real assess_fairness verdict (or None
    when <2 eligible cohorts) — demographic_parity ratio + chi² significance."""
    f = build_analytic_outputs(_LOANS, sessions_per_cell=40).payload["fairness"]
    if f is not None:
        assert set(f) == {
            "assessed", "protected_group", "protected_rate", "reference_rate",
            "disparity_ratio", "parity_difference", "chi2_statistic", "chi2_p_value",
            "statistically_significant", "disparate_impact", "methods", "reason",
        }
        if f["assessed"]:
            assert "demographic_parity" in f["methods"]
            assert "chi_squared" in f["methods"]


def test_fairness_verdict_deterministic():
    a = build_analytic_outputs(_LOANS, sessions_per_cell=40).payload["fairness"]
    b = build_analytic_outputs(_LOANS, sessions_per_cell=40).payload["fairness"]
    assert a == b


def test_negative_cell_does_not_crash_and_keys_hold():
    """The engineered-negative cell (few/zero fires) must still produce a full,
    well-formed payload — guards the zero-affected division paths."""
    p = build_analytic_outputs(_NEGATIVE_CELL, sessions_per_cell=40).payload
    assert set(p) == _PAYLOAD_KEYS
    assert p["affected_sessions"] <= p["total_sessions"]
    assert p["brier_score"] is None or 0.0 <= p["brier_score"] <= 1.0
