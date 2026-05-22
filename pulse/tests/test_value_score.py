"""Tests for the Pulse Value methodology v0 (PULSE-101).

Key invariants (parallel to Risk's test_risk_score.py):
- tier-words enum is a closed set
- score_value() is pure: same inputs → identical ValueScore (incl. hash)
- methodology_version is stamped in every output
- adjustments are monotonic (only push tier up, never down)
- Value methodology + bank_policy integrate end-to-end
"""

from __future__ import annotations

import pytest

from pulse.contracts import validate_bank_policy
from pulse.value import (
    ValueMetrics,
    ValueScore,
    ValueShape,
    load_methodology,
    score_value,
)


def _good_bank_policy() -> dict:
    cfg = {
        "version": "0.1.0",
        "deployment_id": "deploy-test-001",
        "escalation_thresholds": {
            "affected_customers_7d_window": 500,
            "vulnerable_cohort_overrep_floor": 1.25,
        },
        "policy_areas": [],
        "vulnerable_cohort_extensions": [],
    }
    validate_bank_policy(cfg)
    return cfg


def _nominal_shape() -> ValueShape:
    return ValueShape(
        signature_id="lazy_scroll",
        journey_category="behavioural_noise",
        screen_class="marketing_page",
        severity="P2",
    )


def _quiet_metrics() -> ValueMetrics:
    return ValueMetrics(
        affected_customers_7d=15,
        avg_events_per_affected_user=1.1,
        vulnerable_cohort_share=0.05,
        counterfactual_baseline_pct=0.05,
    )


# --- tier-words closure ------------------------------------------------------


def test_tier_words_is_closed_enum_of_four() -> None:
    methodology = load_methodology()
    assert methodology["tier_words"] == [
        "NOMINAL",
        "WATCH",
        "SIGNIFICANT",
        "COMMERCIAL-OPPORTUNITY",
    ]


def test_max_tier_matches_tier_words_length() -> None:
    methodology = load_methodology()
    assert methodology["max_tier"] == len(methodology["tier_words"]) - 1


def test_every_returned_tier_is_in_the_enum() -> None:
    """Sweep: every reachable combination returns a tier-word from the enum."""
    methodology = load_methodology()
    valid_words = set(methodology["tier_words"])
    for severity in ("P0", "P1", "P2"):
        shape = ValueShape("any", "behavioural_noise", "any", severity)
        for affected in (0, 9999):
            for freq in (1.0, 10.0):
                for share in (0.0, 0.9):
                    for baseline in (0.0, 0.9):
                        metrics = ValueMetrics(
                            affected_customers_7d=affected,
                            avg_events_per_affected_user=freq,
                            vulnerable_cohort_share=share,
                            counterfactual_baseline_pct=baseline,
                        )
                        score = score_value(
                            shape=shape, metrics=metrics, bank_policy=_good_bank_policy()
                        )
                        assert score.tier in valid_words


# --- base tier from severity -------------------------------------------------


@pytest.mark.parametrize(
    "severity,expected_tier",
    [
        ("P0", "SIGNIFICANT"),
        ("P1", "WATCH"),
        ("P2", "NOMINAL"),
    ],
)
def test_base_tier_from_severity_alone(severity: str, expected_tier: str) -> None:
    shape = ValueShape("any", "behavioural_noise", "any", severity)
    metrics = ValueMetrics(0, 1.0, 0.0, 0.0)
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert score.tier == expected_tier
    assert score.adjustments_applied == ()


def test_unknown_severity_raises() -> None:
    shape = ValueShape("any", "behavioural_noise", "any", "P9")
    with pytest.raises(ValueError, match="severity"):
        score_value(shape=shape, metrics=_quiet_metrics(), bank_policy=_good_bank_policy())


# --- individual adjustments fire correctly -----------------------------------


def test_large_affected_population_fires_at_threshold() -> None:
    """Inclusive at the threshold."""
    shape = _nominal_shape()
    metrics = ValueMetrics(
        affected_customers_7d=500,  # equals threshold
        avg_events_per_affected_user=1.0,
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.0,
    )
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert "large_affected_population" in score.adjustments_applied
    assert score.tier == "WATCH"  # P2 base (0) + 1 = WATCH (1)


def test_high_frequency_per_user_fires() -> None:
    shape = _nominal_shape()
    metrics = ValueMetrics(
        affected_customers_7d=0,
        avg_events_per_affected_user=3.0,  # equals threshold
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.0,
    )
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert "high_frequency_per_user" in score.adjustments_applied


def test_vulnerable_cohort_concentrated_fires() -> None:
    shape = _nominal_shape()
    metrics = ValueMetrics(
        affected_customers_7d=0,
        avg_events_per_affected_user=1.0,
        vulnerable_cohort_share=0.4,  # equals threshold
        counterfactual_baseline_pct=0.0,
    )
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert "vulnerable_cohort_concentrated" in score.adjustments_applied


def test_large_counterfactual_baseline_fires() -> None:
    shape = _nominal_shape()
    metrics = ValueMetrics(
        affected_customers_7d=0,
        avg_events_per_affected_user=1.0,
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.25,  # equals threshold
    )
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert "large_counterfactual_baseline" in score.adjustments_applied


def test_adjustments_just_below_threshold_do_not_fire() -> None:
    shape = _nominal_shape()
    metrics = ValueMetrics(
        affected_customers_7d=499,
        avg_events_per_affected_user=2.999,
        vulnerable_cohort_share=0.399,
        counterfactual_baseline_pct=0.249,
    )
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert score.adjustments_applied == ()
    assert score.tier == "NOMINAL"


# --- monotonicity + clamping -------------------------------------------------


def test_p0_with_all_adjustments_clamps_at_top_tier() -> None:
    """The COMMERCIAL-OPPORTUNITY cell — P0 + every adjustment fires."""
    shape = ValueShape(
        signature_id="dwell_after_error",
        journey_category="choke_point",
        screen_class="credit_application",
        severity="P0",
    )
    metrics = ValueMetrics(
        affected_customers_7d=12500,
        avg_events_per_affected_user=3.5,
        vulnerable_cohort_share=0.55,
        counterfactual_baseline_pct=0.40,
    )
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    # P0 base (2) + 4 adjustments = 6, clamped to max_tier (3).
    assert score.tier == "COMMERCIAL-OPPORTUNITY"
    assert score.numeric_tier == 3
    assert set(score.adjustments_applied) == {
        "large_affected_population",
        "high_frequency_per_user",
        "vulnerable_cohort_concentrated",
        "large_counterfactual_baseline",
    }


def test_adjustments_are_monotonic() -> None:
    """Adding signal can only push the tier up, never down."""
    shape = ValueShape("sig", "context_loss", "credit_application", "P1")
    weak = ValueMetrics(0, 1.0, 0.0, 0.0)
    strong = ValueMetrics(99999, 10.0, 0.9, 0.9)
    weak_score = score_value(shape=shape, metrics=weak, bank_policy=_good_bank_policy())
    strong_score = score_value(shape=shape, metrics=strong, bank_policy=_good_bank_policy())
    assert strong_score.numeric_tier >= weak_score.numeric_tier


def test_p0_with_no_adjustments_stays_at_significant() -> None:
    """A P0 with quiet metrics is SIGNIFICANT, not COMMERCIAL-OPPORTUNITY —
    severity alone is not enough."""
    shape = ValueShape(
        signature_id="dwell_after_error",
        journey_category="choke_point",
        screen_class="credit_application",
        severity="P0",
    )
    metrics = ValueMetrics(20, 1.0, 0.1, 0.05)
    score = score_value(shape=shape, metrics=metrics, bank_policy=_good_bank_policy())
    assert score.tier == "SIGNIFICANT"
    assert score.adjustments_applied == ()


# --- determinism + audit footprint -------------------------------------------


def test_same_inputs_produce_identical_value_score() -> None:
    shape = ValueShape("sig", "context_loss", "credit_application", "P1")
    metrics = ValueMetrics(600, 3.1, 0.4, 0.3)
    policy = _good_bank_policy()
    a = score_value(shape=shape, metrics=metrics, bank_policy=policy)
    b = score_value(shape=shape, metrics=metrics, bank_policy=policy)
    assert a == b
    assert a.inputs_hash == b.inputs_hash


def test_changing_severity_changes_inputs_hash() -> None:
    shape_p2 = ValueShape("any", "behavioural_noise", "x", "P2")
    shape_p0 = ValueShape("any", "behavioural_noise", "x", "P0")
    a = score_value(shape=shape_p2, metrics=_quiet_metrics(), bank_policy=_good_bank_policy())
    b = score_value(shape=shape_p0, metrics=_quiet_metrics(), bank_policy=_good_bank_policy())
    assert a.inputs_hash != b.inputs_hash


def test_changing_deployment_id_changes_inputs_hash() -> None:
    policy_a = _good_bank_policy()
    policy_b = _good_bank_policy()
    policy_b["deployment_id"] = "deploy-test-002"
    a = score_value(shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_a)
    b = score_value(shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_b)
    assert a.inputs_hash != b.inputs_hash


def test_cosmetic_bank_policy_edit_does_not_change_hash() -> None:
    policy_a = _good_bank_policy()
    policy_b = _good_bank_policy()
    policy_b["policy_areas"] = [
        {
            "internal_name": "Cosmetic",
            "regulatory_taxonomy": "fca_consumer_duty_2.0",
            "regulatory_section": "PRIN 12",
        }
    ]
    a = score_value(shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_a)
    b = score_value(shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_b)
    assert a.inputs_hash == b.inputs_hash


def test_methodology_version_pinned_in_output() -> None:
    score = score_value(
        shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=_good_bank_policy()
    )
    methodology = load_methodology()
    assert score.methodology_version == str(methodology["methodology_version"])
    assert score.methodology_version == "0.3.0"


def test_valuescore_as_dict_round_trip() -> None:
    score = score_value(
        shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=_good_bank_policy()
    )
    d = score.as_dict()
    assert d["tier"] == score.tier
    assert d["methodology_version"] == score.methodology_version
    assert d["inputs_hash"] == score.inputs_hash
    # v0.2 commercial-estimate fields surface in the dict even when None
    assert "estimated_monthly_lift_gbp" in d
    assert "conversion_rate_delta" in d
    assert "confidence_interval" in d
    assert "arpu_source" in d


# --- v0.2 commercial estimate (PULSE-107) ------------------------------------


def _bank_policy_with_arpu(arpu_per_journey: dict[str, float]) -> dict:
    cfg = _good_bank_policy()
    cfg["arpu_per_journey"] = arpu_per_journey
    return cfg


def test_estimated_lift_none_when_arpu_block_absent() -> None:
    """Bank policies that don't configure arpu_per_journey at all get
    sized-lift = None — the categorical tier is unaffected, but the
    rendering surface knows not to draw a £ figure."""
    score = score_value(
        shape=_nominal_shape(),
        metrics=_quiet_metrics(),
        bank_policy=_good_bank_policy(),  # no arpu_per_journey
    )
    assert score.estimated_monthly_lift_gbp is None
    assert score.arpu_source is None


def test_estimated_lift_none_when_journey_category_missing() -> None:
    """ARPU block present but doesn't cover this journey_category → None."""
    policy = _bank_policy_with_arpu({"choke_point": 42.0})
    score = score_value(
        shape=_nominal_shape(),  # journey_category="behavioural_noise"
        metrics=_quiet_metrics(),
        bank_policy=policy,
    )
    assert score.estimated_monthly_lift_gbp is None
    assert score.arpu_source is None


def test_estimated_lift_populated_when_arpu_matches() -> None:
    """ARPU configured for this journey_category → sized lift populated.

    Formula: affected_7d × week_to_month_multiplier × baseline_pct × ARPU."""
    policy = _bank_policy_with_arpu({"behavioural_noise": 10.0})
    metrics = ValueMetrics(
        affected_customers_7d=100,
        avg_events_per_affected_user=1.0,
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.2,
    )
    score = score_value(shape=_nominal_shape(), metrics=metrics, bank_policy=policy)
    # 100 × 4.345 × 0.2 × 10 = 869.0
    assert score.estimated_monthly_lift_gbp == pytest.approx(869.0, rel=1e-3)
    assert score.arpu_source == "bank_policy"


def test_conversion_rate_delta_always_populated() -> None:
    """conversion_rate_delta is aliased to counterfactual_baseline_pct in
    v0.2 — populated even when ARPU is missing (it's input-only)."""
    score = score_value(
        shape=_nominal_shape(),
        metrics=ValueMetrics(100, 1.0, 0.0, 0.3),
        bank_policy=_good_bank_policy(),
    )
    assert score.conversion_rate_delta == pytest.approx(0.3)
    assert score.estimated_monthly_lift_gbp is None  # ARPU still missing


def test_confidence_interval_is_none_in_v02() -> None:
    """v0.2 ships point estimate only; CI fills in v0.3 once HOL-48
    bootstrap fixture lands."""
    policy = _bank_policy_with_arpu({"behavioural_noise": 10.0})
    score = score_value(
        shape=_nominal_shape(),
        metrics=ValueMetrics(100, 1.0, 0.0, 0.2),
        bank_policy=policy,
    )
    assert score.confidence_interval is None


def test_arpu_change_busts_inputs_hash() -> None:
    """Material change to ARPU must bust the audit hash — the sized output
    differs, so the inputs that produced it must too."""
    policy_a = _bank_policy_with_arpu({"behavioural_noise": 10.0})
    policy_b = _bank_policy_with_arpu({"behavioural_noise": 25.0})
    a = score_value(shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_a)
    b = score_value(shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_b)
    assert a.inputs_hash != b.inputs_hash


def test_arpu_for_unrelated_journey_does_not_bust_hash() -> None:
    """Changing ARPU for a journey THIS pack doesn't use must NOT bust the
    hash — the actual sized output is unaffected, so the audit footprint
    shouldn't claim otherwise."""
    policy_a = _bank_policy_with_arpu({"choke_point": 10.0})
    policy_b = _bank_policy_with_arpu({"choke_point": 50.0})
    a = score_value(
        shape=_nominal_shape(),  # behavioural_noise — no match either way
        metrics=_quiet_metrics(),
        bank_policy=policy_a,
    )
    b = score_value(
        shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=policy_b
    )
    assert a.inputs_hash == b.inputs_hash


def test_sized_lift_reproducible() -> None:
    """Same inputs → identical sized lift output, byte-stable."""
    policy = _bank_policy_with_arpu({"behavioural_noise": 12.5})
    metrics = ValueMetrics(250, 2.0, 0.1, 0.15)
    a = score_value(shape=_nominal_shape(), metrics=metrics, bank_policy=policy)
    b = score_value(shape=_nominal_shape(), metrics=metrics, bank_policy=policy)
    assert a.estimated_monthly_lift_gbp == b.estimated_monthly_lift_gbp
    assert a == b


def test_recoverable_sessions_computed_without_arpu() -> None:
    """Friction-volume is the PRIMARY commercial unit (v0.3) — computed from
    metrics alone, no ARPU dependency. Always populated when metrics exist."""
    metrics = ValueMetrics(
        affected_customers_7d=1000,
        avg_events_per_affected_user=1.0,
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.3,
    )
    score = score_value(
        shape=_nominal_shape(), metrics=metrics, bank_policy=_good_bank_policy()
    )
    # 1000 × 0.3 = 300 recoverable sessions/week
    assert score.recoverable_sessions_per_week == 300
    # 300 × 4.345 ≈ 1304/month
    assert score.recoverable_sessions_per_month == round(300 * 4.345)
    # No ARPU configured → £ scaffold is None, but friction volume still there
    assert score.estimated_monthly_lift_gbp is None
    assert score.recoverable_sessions_per_week is not None


def test_recoverable_sessions_reproducible() -> None:
    metrics = ValueMetrics(750, 2.0, 0.1, 0.2)
    a = score_value(shape=_nominal_shape(), metrics=metrics, bank_policy=_good_bank_policy())
    b = score_value(shape=_nominal_shape(), metrics=metrics, bank_policy=_good_bank_policy())
    assert a.recoverable_sessions_per_week == b.recoverable_sessions_per_week == 150
    assert a == b


def test_arpu_per_session_exposed_for_scaffold() -> None:
    """When ARPU is configured, arpu_per_session_gbp is exposed so the
    renderer can name the assumption in the £ scaffold ("at £X/session")."""
    policy = _bank_policy_with_arpu({"behavioural_noise": 12.0})
    score = score_value(
        shape=_nominal_shape(),
        metrics=ValueMetrics(100, 1.0, 0.0, 0.2),
        bank_policy=policy,
    )
    assert score.arpu_per_session_gbp == 12.0
    assert score.estimated_monthly_lift_gbp is not None


def test_friction_volume_in_as_dict() -> None:
    score = score_value(
        shape=_nominal_shape(),
        metrics=ValueMetrics(500, 1.0, 0.0, 0.4),
        bank_policy=_good_bank_policy(),
    )
    d = score.as_dict()
    assert d["recoverable_sessions_per_week"] == 200
    assert "recoverable_sessions_per_month" in d
    assert "arpu_per_session_gbp" in d


def test_arpu_zero_is_valid_yields_zero_lift() -> None:
    """ARPU of 0 is allowed (deployment may have a customer-acquisition
    journey where retained-revenue ARPU is zero). Sized output is zero,
    not None — the engine HAS an ARPU stance, it just happens to be 0."""
    policy = _bank_policy_with_arpu({"behavioural_noise": 0.0})
    score = score_value(
        shape=_nominal_shape(),
        metrics=ValueMetrics(1000, 1.0, 0.0, 0.5),
        bank_policy=policy,
    )
    assert score.estimated_monthly_lift_gbp == 0.0
    assert score.arpu_source == "bank_policy"


# --- cross-axis consistency with Risk ----------------------------------------


def test_shared_affected_population_threshold_with_risk() -> None:
    """Value and Risk both read affected_customers_7d_window from the
    bank policy — the bank commits to ONE number across both axes.
    This test asserts the cross-axis consistency at the threshold edge."""
    from pulse.risk import FrictionShape, ImpactMetrics, score_risk

    # At exactly the threshold, both axes' population-threshold
    # adjustments fire.
    affected_at_threshold = 500
    policy = _good_bank_policy()

    risk_shape = FrictionShape("sig", "behavioural_noise", "any_screen", "P2")
    risk_impact = ImpactMetrics(
        affected_customers_7d=affected_at_threshold,
        vulnerable_cohort_overrep_ratio=1.0,
    )
    risk_score = score_risk(shape=risk_shape, impact=risk_impact, bank_policy=policy)
    assert "affected_customers_threshold" in risk_score.adjustments_applied

    value_shape = ValueShape("sig", "behavioural_noise", "any_screen", "P2")
    value_metrics = ValueMetrics(
        affected_customers_7d=affected_at_threshold,
        avg_events_per_affected_user=1.0,
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.0,
    )
    value_score = score_value(shape=value_shape, metrics=value_metrics, bank_policy=policy)
    assert "large_affected_population" in value_score.adjustments_applied


# --- v0.3 friction-time signal (the recoverable=0 nuance) --------------------


def test_recoverable_friction_minutes_from_friction_seconds() -> None:
    """Value BEYOND recovered completions: 200 affected x 90s excess / 60 =
    300 friction-minutes/week, while recoverable_sessions stays 0 (they complete)."""
    metrics = ValueMetrics(
        affected_customers_7d=200,
        avg_events_per_affected_user=2.0,
        vulnerable_cohort_share=0.0,
        counterfactual_baseline_pct=0.0,            # completes despite friction
        mean_friction_seconds_per_affected=90.0,
    )
    score = score_value(shape=_nominal_shape(), metrics=metrics, bank_policy=_good_bank_policy())
    assert score.recoverable_sessions_per_week == 0
    assert score.recoverable_friction_minutes_per_week == 300
    assert score.recoverable_friction_minutes_per_month == round(300 * 4.345)


def test_friction_minutes_default_zero_when_unset() -> None:
    score = score_value(
        shape=_nominal_shape(), metrics=_quiet_metrics(), bank_policy=_good_bank_policy()
    )
    assert score.recoverable_friction_minutes_per_week == 0
