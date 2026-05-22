"""Tests for the Pulse detection runtime (PULSE-126).

Proves the first vertical slice end-to-end:
- the `dwell_z_score_vs_screen_baseline` method fires on a cell-1-style positive
- the negative-class discriminator suppresses a cell-10-style session (the
  load-bearing negative: long dwell = interest, not friction)
- a below-threshold dwell does not fire
- detections are reproducible (incl. inputs_hash)
- the emitted detection scores well via the FrictionBench reference scorer
"""

from __future__ import annotations

import pytest

from pulse.detection import (
    DETECTION_RUNTIME_VERSION,
    Detection,
    ScreenBaseline,
    Session,
    get_method,
    registered_methods,
    run_detection,
)
from pulse.frictionbench.scoring.score import score_detection


# ── fixtures ────────────────────────────────────────────────────────────────


def _event(seq: int, etype: str, screen: str, ts: str, payload: dict | None = None) -> dict:
    return {
        "context": {"sequence_no": seq, "screen_id": screen},
        "event": {"event_type": etype, "event_ts": ts, "payload": payload or {}},
    }


def _cell1_hypothesis() -> dict:
    """loans.apply.step3 × dwell_after_error — engineered POSITIVE."""
    return {
        "screen_id": "loans.apply.step3",
        "signature_id": "dwell_after_error",
        "analytic": {
            "method": "dwell_z_score_vs_screen_baseline",
            "trigger": {
                "requires_prior_event": "validation_error",
                "dwell_window_seconds": 60,
                "p_value_threshold": 0.01,
            },
            "baseline_source": "rolling_28d_same_screen",
        },
        "cohort_axes": ["age_band"],
        "negative_class_discriminator": None,
    }


def _cell10_hypothesis() -> dict:
    """investments.premier.portfolio.overview × dwell_after_error — engineered
    NEGATIVE. Long dwell after an error, BUT engagement signals mark it as
    deliberate review, not friction. The discriminator must suppress."""
    return {
        "screen_id": "investments.premier.portfolio.overview",
        "signature_id": "dwell_after_error",
        "analytic": {
            "method": "dwell_z_score_vs_screen_baseline",
            "trigger": {
                "requires_prior_event": "validation_error",
                "dwell_window_seconds": 60,
                "p_value_threshold": 0.01,
            },
            "baseline_source": "rolling_28d_same_screen",
        },
        "cohort_axes": ["client_tier"],
        "negative_class_discriminator": {
            "suppression_signals": [
                {"signal": "scroll_depth_pct", "threshold": 60, "direction": "above"},
                {"signal": "chart_drilldowns_in_session", "threshold": 2, "direction": "above_or_equal"},
                {"signal": "return_within_7_days", "threshold": True, "direction": "equals"},
            ],
        },
    }


def _loans_baseline() -> ScreenBaseline:
    return ScreenBaseline("loans.apply.step3", "dwell_seconds", mean=20.0, std=5.0, n_sessions=300)


def _investments_baseline() -> ScreenBaseline:
    return ScreenBaseline(
        "investments.premier.portfolio.overview", "dwell_seconds",
        mean=25.0, std=8.0, n_sessions=300,
    )


def _positive_session() -> Session:
    """Validation error then a 60s dwell — z = 8 vs the loans baseline."""
    return Session(
        session_id="sess-pos-1",
        screen_id="loans.apply.step3",
        cohort_tags=("over_50",),
        events=(
            _event(1, "screen_view", "loans.apply.step3", "2026-05-21T10:00:00Z"),
            _event(2, "error", "loans.apply.step3", "2026-05-21T10:00:05Z",
                   {"error_type": "validation_error"}),
            _event(3, "dwell", "loans.apply.step3", "2026-05-21T10:00:13Z",
                   {"duration_seconds": 60.0}),
        ),
        features={},
    )


def _cell10_session() -> Session:
    """70s dwell after a validation error (would fire) BUT engagement signals
    present → discriminator suppresses."""
    return Session(
        session_id="sess-neg-10",
        screen_id="investments.premier.portfolio.overview",
        cohort_tags=("premier",),
        events=(
            _event(1, "screen_view", "investments.premier.portfolio.overview", "2026-05-21T11:00:00Z"),
            _event(2, "error", "investments.premier.portfolio.overview", "2026-05-21T11:00:04Z",
                   {"error_type": "validation_error"}),
            _event(3, "dwell", "investments.premier.portfolio.overview", "2026-05-21T11:00:10Z",
                   {"duration_seconds": 70.0}),
        ),
        features={
            "scroll_depth_pct": 75,
            "chart_drilldowns_in_session": 3,
            "return_within_7_days": True,
        },
    )


def _short_dwell_session() -> Session:
    """8s dwell — below baseline, must not fire."""
    return Session(
        session_id="sess-short",
        screen_id="loans.apply.step3",
        cohort_tags=("under_30",),
        events=(
            _event(1, "error", "loans.apply.step3", "2026-05-21T10:00:00Z",
                   {"error_type": "validation_error"}),
            _event(2, "dwell", "loans.apply.step3", "2026-05-21T10:00:03Z",
                   {"duration_seconds": 8.0}),
        ),
        features={},
    )


# ── registry ──────────────────────────────────────────────────────────────────


def test_method_registered() -> None:
    assert "dwell_z_score_vs_screen_baseline" in registered_methods()
    assert callable(get_method("dwell_z_score_vs_screen_baseline"))


def test_unknown_method_raises() -> None:
    with pytest.raises(ValueError, match="unknown analytic.method"):
        get_method("does_not_exist")


# ── positive cell fires ─────────────────────────────────────────────────────


def test_positive_cell_fires() -> None:
    d = run_detection(
        hypothesis=_cell1_hypothesis(), session=_positive_session(), baseline=_loans_baseline()
    )
    assert d.fired is True
    assert d.signature_id == "dwell_after_error"
    assert d.screen_id == "loans.apply.step3"
    assert d.root_cause == "template"               # validation_error → template
    assert d.confidence is not None and d.confidence > 0.99   # z=8 → ~1.0
    assert d.cohort_tags == ("over_50",)
    assert d.time_to_detect_seconds == 13.0
    assert d.evidence["dwell_time_seconds"] == 60.0
    assert d.runtime_version == DETECTION_RUNTIME_VERSION
    assert d.suppressed_by == ()


def test_positive_detection_scores_well_on_frictionbench() -> None:
    d = run_detection(
        hypothesis=_cell1_hypothesis(), session=_positive_session(), baseline=_loans_baseline()
    )
    ground_truth = {
        "screen_id": "loans.apply.step3",
        "signature_id": "dwell_after_error",
        "should_fire": True,
        "root_cause": "template",
        "cohort_tags": ["over_50"],
        "confidence_target": 0.9,
    }
    score = score_detection(d.to_scoring_dict(), ground_truth)
    assert score.screen == 1.0
    assert score.signature == 1.0
    assert score.cohort == 1.0
    assert score.cause == 1.0
    assert score.aggregate > 0.95


# ── cell-10 negative is suppressed ──────────────────────────────────────────


def test_cell10_negative_is_suppressed() -> None:
    d = run_detection(
        hypothesis=_cell10_hypothesis(), session=_cell10_session(), baseline=_investments_baseline()
    )
    assert d.fired is False
    assert d.signature_id is None             # abstain
    assert d.root_cause is None
    assert d.confidence is not None and d.confidence <= 0.10   # collapsed
    assert set(d.suppressed_by) == {
        "scroll_depth_pct", "chart_drilldowns_in_session", "return_within_7_days"
    }


def test_cell10_abstain_scores_well_on_frictionbench() -> None:
    d = run_detection(
        hypothesis=_cell10_hypothesis(), session=_cell10_session(), baseline=_investments_baseline()
    )
    ground_truth = {
        "screen_id": "investments.premier.portfolio.overview",
        "signature_id": "none",
        "should_fire": False,
        "root_cause": "none",
        "cohort_tags": [],
    }
    score = score_detection(d.to_scoring_dict(), ground_truth)
    assert score.signature == 1.0    # correctly abstained
    assert score.cause == 1.0
    assert score.cohort == 1.0
    assert score.calibration > 0.95  # low confidence on a true negative
    assert score.aggregate > 0.95


# ── below-threshold does not fire ───────────────────────────────────────────


def test_short_dwell_does_not_fire() -> None:
    d = run_detection(
        hypothesis=_cell1_hypothesis(), session=_short_dwell_session(), baseline=_loans_baseline()
    )
    assert d.fired is False
    assert d.signature_id is None
    assert d.confidence is not None and d.confidence < 0.05   # 8s vs mean 20 → low


def test_no_qualifying_dwell_does_not_fire() -> None:
    """A session with no error-then-dwell sequence abstains cleanly."""
    session = Session(
        session_id="sess-nodwell",
        screen_id="loans.apply.step3",
        cohort_tags=(),
        events=(_event(1, "screen_view", "loans.apply.step3", "2026-05-21T10:00:00Z"),),
        features={},
    )
    d = run_detection(hypothesis=_cell1_hypothesis(), session=session, baseline=_loans_baseline())
    assert d.fired is False
    assert d.confidence == 0.0


# ── reproducibility ─────────────────────────────────────────────────────────


def test_same_inputs_produce_identical_detection() -> None:
    a = run_detection(hypothesis=_cell1_hypothesis(), session=_positive_session(), baseline=_loans_baseline())
    b = run_detection(hypothesis=_cell1_hypothesis(), session=_positive_session(), baseline=_loans_baseline())
    assert a == b
    assert a.inputs_hash == b.inputs_hash


def test_changing_dwell_changes_hash() -> None:
    a = run_detection(hypothesis=_cell1_hypothesis(), session=_positive_session(), baseline=_loans_baseline())
    b = run_detection(hypothesis=_cell1_hypothesis(), session=_short_dwell_session(), baseline=_loans_baseline())
    assert a.inputs_hash != b.inputs_hash


# ── multi_back_press (cell 2) ───────────────────────────────────────────────


def _cell2_hypothesis() -> dict:
    """loans.apply.step3 × multi_back_press."""
    return {
        "screen_id": "loans.apply.step3",
        "signature_id": "multi_back_press",
        "analytic": {
            "method": "back_press_burst_detection",
            "trigger": {"min_back_press_events": 3, "window_seconds": 300, "same_screen_required": True},
            "discriminator": {"rule": "inter_press_interval_under_seconds", "value": 20},
        },
        "cohort_axes": ["device_class"],
        "negative_class_discriminator": None,
    }


def _back_press_session(intervals_s: int, n: int, cohort: tuple[str, ...]) -> Session:
    events = [_event(1, "screen_view", "loans.apply.step3", "2026-05-21T10:00:00Z")]
    for i in range(n):
        ts = f"2026-05-21T10:0{(i * intervals_s) // 60}:{(i * intervals_s) % 60:02d}Z"
        events.append(_event(2 + i, "back_press", "loans.apply.step3", ts))
    return Session("sess-bp", "loans.apply.step3", cohort, tuple(events), {})


def test_back_press_tight_burst_fires() -> None:
    d = run_detection(
        hypothesis=_cell2_hypothesis(),
        session=_back_press_session(intervals_s=10, n=4, cohort=("mobile",)),
        baseline=_loans_baseline(),
    )
    assert d.fired is True
    assert d.signature_id == "multi_back_press"
    assert d.confidence is not None and d.confidence >= 0.80
    assert d.evidence["back_press_event_count"] == 4
    gt = {"screen_id": "loans.apply.step3", "signature_id": "multi_back_press",
          "should_fire": True, "root_cause": "template", "cohort_tags": ["mobile"]}
    score = score_detection(d.to_scoring_dict(), gt)
    assert score.signature == 1.0 and score.cohort == 1.0
    assert score.aggregate > 0.9


def test_back_press_long_intervals_do_not_fire() -> None:
    """Enough presses, but spaced out → deliberate review, not confusion."""
    d = run_detection(
        hypothesis=_cell2_hypothesis(),
        session=_back_press_session(intervals_s=60, n=4, cohort=("desktop",)),
        baseline=_loans_baseline(),
    )
    assert d.fired is False
    assert d.signature_id is None
    assert d.evidence["reason"] == "long_intervals_deliberate_review"


def test_back_press_below_threshold_does_not_fire() -> None:
    d = run_detection(
        hypothesis=_cell2_hypothesis(),
        session=_back_press_session(intervals_s=10, n=2, cohort=("mobile",)),
        baseline=_loans_baseline(),
    )
    assert d.fired is False
    assert d.confidence is not None and d.confidence < 0.5


# ── abandon_before_submit (cell 3) ──────────────────────────────────────────


def _cell3_hypothesis() -> dict:
    return {
        "screen_id": "loans.apply.step3",
        "signature_id": "abandon_before_submit",
        "analytic": {
            "method": "terminal_abandonment_detection",
            "trigger": {
                "requires_prior_step_completion": ["step1", "step2"],
                "requires_dwell_above_percentile": 90,
                "requires_exit_without_event": "submit_clicked",
            },
            "exclusions": [{"session_returned_within_seconds": 1800}],
        },
        "cohort_axes": ["age_band"],
        "negative_class_discriminator": None,
    }


def _abandon_baseline() -> ScreenBaseline:
    # p90 ≈ 30 + 1.2816*15 ≈ 49.2s
    return ScreenBaseline("loans.apply.step3", "dwell_seconds", mean=30.0, std=15.0, n_sessions=300)


def _abandon_session(features: dict, cohort: tuple[str, ...] = ("under_30",)) -> Session:
    return Session(
        "sess-aband", "loans.apply.step3", cohort,
        (
            _event(1, "screen_view", "loans.apply.step3", "2026-05-21T10:00:00Z"),
            _event(2, "nav_intent", "loans.apply.step3", "2026-05-21T10:02:00Z", {"action": "exit"}),
        ),
        features,
    )


def test_abandon_fires_on_high_intent_dropoff() -> None:
    d = run_detection(
        hypothesis=_cell3_hypothesis(),
        session=_abandon_session({"prior_steps_completed": ["step1", "step2"], "time_on_step_seconds": 120.0}),
        baseline=_abandon_baseline(),
    )
    assert d.fired is True
    assert d.signature_id == "abandon_before_submit"
    assert d.confidence is not None and d.confidence > 0.95   # z = 6
    gt = {"screen_id": "loans.apply.step3", "signature_id": "abandon_before_submit",
          "should_fire": True, "root_cause": "template", "cohort_tags": ["under_30"]}
    score = score_detection(d.to_scoring_dict(), gt)
    assert score.aggregate > 0.95


def test_abandon_does_not_fire_when_submitted() -> None:
    d = run_detection(
        hypothesis=_cell3_hypothesis(),
        session=_abandon_session({"prior_steps_completed": ["step1", "step2"],
                                  "time_on_step_seconds": 120.0, "submit_clicked": True}),
        baseline=_abandon_baseline(),
    )
    assert d.fired is False
    assert d.signature_id is None
    assert d.evidence["reason"] == "submitted"


def test_abandon_excluded_on_quick_return() -> None:
    """Returned within 1800s → tab-park, not abandonment."""
    d = run_detection(
        hypothesis=_cell3_hypothesis(),
        session=_abandon_session({"prior_steps_completed": ["step1", "step2"],
                                  "time_on_step_seconds": 120.0,
                                  "session_returned_within_seconds": 600}),
        baseline=_abandon_baseline(),
    )
    assert d.fired is False
    assert d.evidence["reason"] == "returned_excluded"


def test_abandon_does_not_fire_when_prior_steps_incomplete() -> None:
    d = run_detection(
        hypothesis=_cell3_hypothesis(),
        session=_abandon_session({"prior_steps_completed": ["step1"], "time_on_step_seconds": 120.0}),
        baseline=_abandon_baseline(),
    )
    assert d.fired is False
    assert d.evidence["reason"] == "prior_steps_incomplete"


def test_abandon_does_not_fire_below_percentile() -> None:
    d = run_detection(
        hypothesis=_cell3_hypothesis(),
        session=_abandon_session({"prior_steps_completed": ["step1", "step2"], "time_on_step_seconds": 40.0}),
        baseline=_abandon_baseline(),
    )
    assert d.fired is False
    assert d.evidence["reason"] == "dwell_below_required_percentile"


def test_all_three_signature_methods_registered() -> None:
    assert {
        "dwell_z_score_vs_screen_baseline",
        "back_press_burst_detection",
        "terminal_abandonment_detection",
    } <= set(registered_methods())
