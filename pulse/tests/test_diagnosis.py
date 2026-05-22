"""Tests for the Pulse Diagnosis methodology v0 (PULSE-105).

Key invariants (parallel to Risk/Value test patterns):
- tier-words enum is a closed set of 4 labels
- diagnose_problem_locus() is pure: same inputs → identical DiagnosisResult
- methodology_version is stamped in every output
- INCONCLUSIVE is RETURNED, not raised, when control-arm too small
  (downstream consumers need to render a "needs more data" state cleanly,
  not catch an exception)
- input validation rejects malformed arms (out-of-range success rate,
  negative session count)
- precedence: INCONCLUSIVE > SUPPORT_PROBLEM > JOURNEY_PROBLEM > BOTH
"""

from __future__ import annotations

import copy

import pytest

from pulse.diagnosis import (
    DiagnosisResult,
    JourneyArmObservation,
    JourneyIdentity,
    diagnose_problem_locus,
    load_rubric,
)


def _journey() -> JourneyIdentity:
    return JourneyIdentity(
        journey_id="make_a_payment",
        screen_class="payment_initiation",
    )


# --- tier-words closure ------------------------------------------------------


def test_tier_words_is_closed_enum_of_four() -> None:
    rubric = load_rubric()
    assert set(rubric["tier_words"]) == {
        "SUPPORT_PROBLEM",
        "JOURNEY_PROBLEM",
        "BOTH",
        "INCONCLUSIVE",
    }
    assert len(rubric["tier_words"]) == 4


def test_every_returned_diagnosis_is_in_the_enum() -> None:
    """Sweep a broad input space and assert every returned label is from
    the closed enum."""
    rubric = load_rubric()
    valid = set(rubric["tier_words"])
    journey = _journey()
    for n_control in (50, 1000):
        for control_success in (0.1, 0.5, 0.95):
            for assistance_success in (0.1, 0.5, 0.95):
                arms = (
                    JourneyArmObservation(n_sessions=500, success_rate=assistance_success),
                    JourneyArmObservation(n_sessions=n_control, success_rate=control_success),
                )
                result = diagnose_problem_locus(
                    journey=journey,
                    assistance_arm=arms[0],
                    no_assistance_arm=arms[1],
                )
                assert result.diagnosis in valid


# --- precedence ---------------------------------------------------------------


def test_clear_support_problem() -> None:
    """Large positive gap with healthy no-assistance baseline."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=540, success_rate=0.58),
        no_assistance_arm=JourneyArmObservation(n_sessions=2400, success_rate=0.92),
    )
    assert result.diagnosis == "SUPPORT_PROBLEM"
    assert result.gap == pytest.approx(0.34)


def test_clear_journey_problem() -> None:
    """Small gap AND both arms struggling — journey is the binding constraint."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=820, success_rate=0.31),
        no_assistance_arm=JourneyArmObservation(n_sessions=1100, success_rate=0.35),
    )
    assert result.diagnosis == "JOURNEY_PROBLEM"


def test_both_when_gap_is_in_middle_band() -> None:
    """Moderate gap (0.05 < gap < 0.20) → BOTH."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=310, success_rate=0.65),
        no_assistance_arm=JourneyArmObservation(n_sessions=900, success_rate=0.78),
    )
    assert result.diagnosis == "BOTH"


def test_small_control_arm_returns_inconclusive_not_raises() -> None:
    """Even with an apparent SUPPORT_PROBLEM gap, n < 100 returns INCONCLUSIVE.
    Critically: this RETURNS — downstream code should not have to catch
    an exception to render a 'needs more data' state."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=320, success_rate=0.50),
        no_assistance_arm=JourneyArmObservation(n_sessions=45, success_rate=0.71),
    )
    assert result.diagnosis == "INCONCLUSIVE"
    # the gap is still computed and returned for audit transparency
    assert result.gap == pytest.approx(0.21)


def test_inconclusive_takes_precedence_over_support_problem() -> None:
    """Even a huge gap fails over to INCONCLUSIVE if control arm too small."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.20),
        no_assistance_arm=JourneyArmObservation(n_sessions=99, success_rate=0.95),
    )
    assert result.diagnosis == "INCONCLUSIVE"


def test_two_clause_journey_problem_rule_prevents_false_positive() -> None:
    """Both arms succeeding at high rates with small gap → BOTH (not
    JOURNEY_PROBLEM). The two-clause rule (gap small AND assistance
    success below 0.5) prevents labelling a healthy journey as broken."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=410, success_rate=0.94),
        no_assistance_arm=JourneyArmObservation(n_sessions=8000, success_rate=0.95),
    )
    # gap (0.01) is below journey_problem_gap (0.05) BUT assistance success
    # (0.94) is above journey_problem_assistance_success_max (0.5)
    assert result.diagnosis == "BOTH"


def test_negative_gap_does_not_fire_support_problem() -> None:
    """Negative gap means assistance arm OUTPERFORMS no-assistance — support
    is working better than baseline. Should not be SUPPORT_PROBLEM."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.75),
        no_assistance_arm=JourneyArmObservation(n_sessions=2000, success_rate=0.60),
    )
    assert result.diagnosis != "SUPPORT_PROBLEM"


# --- thresholds at the boundary ---------------------------------------------


def test_gap_exactly_at_support_threshold_fires_support_problem() -> None:
    """Inclusive at 0.20."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.50),
        no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.70),
    )
    assert result.diagnosis == "SUPPORT_PROBLEM"


def test_control_arm_exactly_at_min_sessions_proceeds() -> None:
    """min_control_sessions=100: exactly 100 is sufficient (>= comparison)."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.50),
        no_assistance_arm=JourneyArmObservation(n_sessions=100, success_rate=0.70),
    )
    assert result.diagnosis != "INCONCLUSIVE"


# --- determinism + audit footprint -------------------------------------------


def test_same_inputs_produce_identical_diagnosis() -> None:
    a_arm = JourneyArmObservation(n_sessions=540, success_rate=0.58)
    c_arm = JourneyArmObservation(n_sessions=2400, success_rate=0.92)
    a = diagnose_problem_locus(journey=_journey(), assistance_arm=a_arm, no_assistance_arm=c_arm)
    b = diagnose_problem_locus(journey=_journey(), assistance_arm=a_arm, no_assistance_arm=c_arm)
    assert a == b
    assert a.inputs_hash == b.inputs_hash


def test_different_journey_changes_inputs_hash() -> None:
    arms = dict(
        assistance_arm=JourneyArmObservation(n_sessions=540, success_rate=0.58),
        no_assistance_arm=JourneyArmObservation(n_sessions=2400, success_rate=0.92),
    )
    a = diagnose_problem_locus(journey=_journey(), **arms)
    b = diagnose_problem_locus(
        journey=JourneyIdentity("different_journey", "payment_initiation"), **arms
    )
    assert a.inputs_hash != b.inputs_hash


def test_different_arm_data_changes_inputs_hash() -> None:
    base_a = JourneyArmObservation(n_sessions=540, success_rate=0.58)
    base_c = JourneyArmObservation(n_sessions=2400, success_rate=0.92)
    a = diagnose_problem_locus(
        journey=_journey(), assistance_arm=base_a, no_assistance_arm=base_c
    )
    b = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=base_a,
        no_assistance_arm=JourneyArmObservation(n_sessions=2400, success_rate=0.93),
    )
    assert a.inputs_hash != b.inputs_hash


def test_methodology_version_pinned_in_output() -> None:
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.5),
        no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.7),
    )
    assert result.methodology_version == str(load_rubric()["methodology_version"])
    assert result.methodology_version == "0.1.0"


def test_diagnosisresult_as_dict_round_trip() -> None:
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.5),
        no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.7),
    )
    d = result.as_dict()
    assert d["diagnosis"] == result.diagnosis
    assert d["gap"] == result.gap
    assert d["methodology_version"] == result.methodology_version
    assert d["inputs_hash"] == result.inputs_hash


def test_result_echoes_input_arms_for_audit() -> None:
    """The DiagnosisResult must carry both arms' n and success_rate back
    out — auditors should be able to reconstruct the diagnosis from the
    result alone without needing the input objects."""
    a_arm = JourneyArmObservation(n_sessions=540, success_rate=0.58)
    c_arm = JourneyArmObservation(n_sessions=2400, success_rate=0.92)
    result = diagnose_problem_locus(
        journey=_journey(), assistance_arm=a_arm, no_assistance_arm=c_arm
    )
    assert result.assistance_arm_n == 540
    assert result.assistance_arm_success_rate == 0.58
    assert result.no_assistance_arm_n == 2400
    assert result.no_assistance_arm_success_rate == 0.92


# --- input validation --------------------------------------------------------


def test_negative_session_count_rejected() -> None:
    with pytest.raises(ValueError, match="n_sessions"):
        diagnose_problem_locus(
            journey=_journey(),
            assistance_arm=JourneyArmObservation(n_sessions=-1, success_rate=0.5),
            no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.7),
        )


def test_session_count_bool_rejected() -> None:
    """Python bool is a subclass of int — reject explicitly."""
    with pytest.raises(ValueError, match="n_sessions"):
        diagnose_problem_locus(
            journey=_journey(),
            assistance_arm=JourneyArmObservation(n_sessions=True, success_rate=0.5),  # type: ignore
            no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.7),
        )


def test_success_rate_out_of_range_rejected() -> None:
    with pytest.raises(ValueError, match="success_rate"):
        diagnose_problem_locus(
            journey=_journey(),
            assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=1.5),
            no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.7),
        )


def test_success_rate_negative_rejected() -> None:
    with pytest.raises(ValueError, match="success_rate"):
        diagnose_problem_locus(
            journey=_journey(),
            assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.5),
            no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=-0.1),
        )


def test_success_rate_exactly_zero_or_one_accepted() -> None:
    """Boundary values are valid success rates."""
    result = diagnose_problem_locus(
        journey=_journey(),
        assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=0.0),
        no_assistance_arm=JourneyArmObservation(n_sessions=500, success_rate=1.0),
    )
    assert result.diagnosis == "SUPPORT_PROBLEM"
    assert result.gap == pytest.approx(1.0)


# --- non-mutation ------------------------------------------------------------


def test_diagnose_does_not_mutate_inputs() -> None:
    journey = _journey()
    a_arm = JourneyArmObservation(n_sessions=540, success_rate=0.58)
    c_arm = JourneyArmObservation(n_sessions=2400, success_rate=0.92)
    snap_journey = copy.deepcopy(journey)
    snap_a = copy.deepcopy(a_arm)
    snap_c = copy.deepcopy(c_arm)
    diagnose_problem_locus(journey=journey, assistance_arm=a_arm, no_assistance_arm=c_arm)
    assert journey == snap_journey
    assert a_arm == snap_a
    assert c_arm == snap_c
