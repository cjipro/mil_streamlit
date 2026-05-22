"""Tests for FrictionBench v0.1 scoring (per-axis + aggregation + FP penalty)."""

from __future__ import annotations

import pytest

from pulse.frictionbench.scoring.score import (
    aggregate_cell,
    apply_false_positive_penalty,
    macro_average,
    score_detection,
)


def _ground_truth(**overrides) -> dict:
    base = {
        "session_id": "sess-1",
        "cell_id": "1",
        "screen_id": "loans.apply.step3",
        "signature_id": "dwell_after_error",
        "should_fire": True,
        "root_cause": "template",
        "cohort_tags": ["premier", "over_50"],
        "confidence_target": 0.85,
    }
    base.update(overrides)
    return base


def _detection(**overrides) -> dict:
    base = {
        "screen_id": "loans.apply.step3",
        "signature_id": "dwell_after_error",
        "cohort_tags": ["premier", "over_50"],
        "root_cause": "template",
        "confidence": 0.85,
        "time_to_detect_seconds": 4.2,
    }
    base.update(overrides)
    return base


# ── Perfect-detection example from RUBRIC.md ─────────────────────────────────


def test_perfect_detection_matches_rubric_example_1() -> None:
    score = score_detection(_detection(), _ground_truth())
    assert score.screen == 1.0
    assert score.signature == 1.0
    assert score.cohort == 1.0
    assert score.cause == 1.0
    # Brier = (0.85-1)^2 = 0.0225 → 1 - 0.0225 = 0.9775
    assert score.calibration == pytest.approx(0.9775)
    # Aggregate = mean of 5 axes (equal weights = 0.2 each)
    assert score.aggregate == pytest.approx(0.9955)
    assert score.time_to_detect_seconds == 4.2


# ── Screen axis ──────────────────────────────────────────────────────────────


def test_screen_exact_match() -> None:
    s = score_detection(_detection(), _ground_truth())
    assert s.screen == 1.0


def test_screen_same_journey_wrong_step_partial_credit() -> None:
    journey_map = {
        "loans.apply.step2": "loans",
        "loans.apply.step3": "loans",
    }
    s = score_detection(
        _detection(screen_id="loans.apply.step2"),
        _ground_truth(),
        journey_for_screen=journey_map,
    )
    assert s.screen == 0.5


def test_screen_different_journey_zero() -> None:
    journey_map = {
        "loans.apply.step3": "loans",
        "cards.credit.apply.eligibility": "cards",
    }
    s = score_detection(
        _detection(screen_id="cards.credit.apply.eligibility"),
        _ground_truth(),
        journey_for_screen=journey_map,
    )
    assert s.screen == 0.0


def test_screen_missing_zero() -> None:
    s = score_detection(_detection(screen_id=None), _ground_truth())
    assert s.screen == 0.0


# ── Signature axis ───────────────────────────────────────────────────────────


def test_signature_exact_match() -> None:
    s = score_detection(_detection(), _ground_truth())
    assert s.signature == 1.0


def test_signature_same_family_partial_credit() -> None:
    families = {"multi_back_press": {"back_loop"}}
    s = score_detection(
        _detection(signature_id="back_loop"),
        _ground_truth(signature_id="multi_back_press"),
        signature_families=families,
    )
    assert s.signature == 0.5


def test_signature_unrelated_zero() -> None:
    s = score_detection(
        _detection(signature_id="abandon_before_submit"),
        _ground_truth(signature_id="dwell_after_error"),
    )
    assert s.signature == 0.0


def test_signature_negative_truth_correct_abstention() -> None:
    """Cell 10 case: truth=none, detector=none → correct, scored 1.0."""
    s = score_detection(
        _detection(signature_id="none"),
        _ground_truth(signature_id="none", should_fire=False, root_cause="none", cohort_tags=[]),
    )
    assert s.signature == 1.0


def test_signature_negative_truth_false_fire_zero() -> None:
    """Cell 10 case: truth=none, detector fired → wrong, scored 0.0."""
    s = score_detection(
        _detection(signature_id="dwell_after_error"),
        _ground_truth(signature_id="none", should_fire=False),
    )
    assert s.signature == 0.0


# ── Cohort axis (multi-label F1) ─────────────────────────────────────────────


def test_cohort_perfect_match_is_one() -> None:
    s = score_detection(_detection(), _ground_truth())
    assert s.cohort == 1.0


def test_cohort_both_empty_is_one() -> None:
    s = score_detection(
        _detection(cohort_tags=[]),
        _ground_truth(cohort_tags=[]),
    )
    assert s.cohort == 1.0


def test_cohort_no_overlap_is_zero() -> None:
    s = score_detection(
        _detection(cohort_tags=["premier"]),
        _ground_truth(cohort_tags=["over_50"]),
    )
    assert s.cohort == 0.0


def test_cohort_partial_overlap_f1() -> None:
    # detector: {a, b}, truth: {a, c}. TP=1, precision=1/2, recall=1/2, F1=0.5
    s = score_detection(
        _detection(cohort_tags=["a", "b"]),
        _ground_truth(cohort_tags=["a", "c"]),
    )
    assert s.cohort == pytest.approx(0.5)


def test_cohort_one_empty_other_not_is_zero() -> None:
    s = score_detection(
        _detection(cohort_tags=["a"]),
        _ground_truth(cohort_tags=[]),
    )
    assert s.cohort == 0.0


# ── Cause axis ───────────────────────────────────────────────────────────────


def test_cause_exact_match() -> None:
    s = score_detection(_detection(), _ground_truth())
    assert s.cause == 1.0


def test_cause_plausible_component_partial_credit() -> None:
    # 'copy' is a component of 'template' per the v0.1 hard-coded map.
    s = score_detection(
        _detection(root_cause="copy"),
        _ground_truth(root_cause="template"),
    )
    assert s.cause == 0.5


def test_cause_plausible_wrong_low_credit() -> None:
    # 'release' is a known cause category but isn't 'template' — 0.2.
    s = score_detection(
        _detection(root_cause="release"),
        _ground_truth(root_cause="template"),
    )
    assert s.cause == 0.2


def test_cause_implausible_zero() -> None:
    s = score_detection(
        _detection(root_cause="aliens"),
        _ground_truth(root_cause="template"),
    )
    assert s.cause == 0.0


def test_cause_truth_none_correct_abstention() -> None:
    s = score_detection(
        _detection(root_cause="none"),
        _ground_truth(root_cause="none"),
    )
    assert s.cause == 1.0


def test_cause_truth_none_detector_named_cause_zero() -> None:
    s = score_detection(
        _detection(root_cause="template"),
        _ground_truth(root_cause="none"),
    )
    assert s.cause == 0.0


# ── Calibration axis (1 - Brier) ─────────────────────────────────────────────


def test_calibration_perfect_high_confidence_fire() -> None:
    s = score_detection(
        _detection(confidence=1.0),
        _ground_truth(should_fire=True),
    )
    assert s.calibration == 1.0


def test_calibration_perfect_low_confidence_no_fire() -> None:
    s = score_detection(
        _detection(confidence=0.0),
        _ground_truth(should_fire=False),
    )
    assert s.calibration == 1.0


def test_calibration_worst_case_confident_wrong() -> None:
    s = score_detection(
        _detection(confidence=1.0),
        _ground_truth(should_fire=False),
    )
    assert s.calibration == 0.0


def test_calibration_missing_confidence_zero() -> None:
    s = score_detection(_detection(confidence=None), _ground_truth())
    assert s.calibration == 0.0


def test_calibration_out_of_range_zero() -> None:
    s = score_detection(_detection(confidence=1.5), _ground_truth())
    assert s.calibration == 0.0


# ── Aggregate + cell aggregation + macro average ─────────────────────────────


def test_aggregate_cell_mean() -> None:
    s1 = score_detection(_detection(), _ground_truth())
    s2 = score_detection(_detection(), _ground_truth())
    cell_score = aggregate_cell([s1, s2])
    assert cell_score == pytest.approx(0.9955)


def test_aggregate_cell_empty_is_zero() -> None:
    assert aggregate_cell([]) == 0.0


def test_macro_average_evens() -> None:
    assert macro_average([0.5, 0.7, 0.9]) == pytest.approx(0.7)


def test_macro_average_empty_is_zero() -> None:
    assert macro_average([]) == 0.0


# ── False-positive penalty ───────────────────────────────────────────────────


def test_fp_penalty_subtracts_correctly() -> None:
    assert apply_false_positive_penalty(0.9, 5) == pytest.approx(0.65)


def test_fp_penalty_floors_at_zero() -> None:
    assert apply_false_positive_penalty(0.1, 100) == 0.0


def test_fp_penalty_no_fps_unchanged() -> None:
    assert apply_false_positive_penalty(0.85, 0) == pytest.approx(0.85)


# ── End-to-end worked example from RUBRIC.md (Example 2) ─────────────────────


def test_example_2_wrong_screen_same_journey() -> None:
    journey_map = {
        "loans.apply.step2": "loans",
        "loans.apply.step3": "loans",
    }
    score = score_detection(
        _detection(screen_id="loans.apply.step2"),
        _ground_truth(),
        journey_for_screen=journey_map,
    )
    # Per RUBRIC.md Example 2: aggregate = 0.8955
    assert score.aggregate == pytest.approx(0.8955)


# ── Example 3 (cell 10 negative correctly NOT fired) ─────────────────────────


def test_example_3_cell_10_correct_abstention() -> None:
    gt = _ground_truth(
        cell_id="10",
        screen_id="investments.premier.portfolio.overview",
        signature_id="none",
        should_fire=False,
        root_cause="none",
        cohort_tags=[],
        confidence_target=0.05,
    )
    det = {
        "screen_id": "investments.premier.portfolio.overview",
        "signature_id": "none",
        "cohort_tags": [],
        "root_cause": "none",
        "confidence": 0.05,
        "time_to_detect_seconds": None,
    }
    score = score_detection(det, gt)
    # Per RUBRIC.md Example 3: aggregate = 0.9995
    assert score.aggregate == pytest.approx(0.9995)
