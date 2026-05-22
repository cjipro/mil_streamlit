"""Pulse detection methods (PULSE-126).

One classical, deterministic, evidence-emitting detector per `analytic.method`
declared in decision packs. v0.1 ships `dwell_z_score_vs_screen_baseline`
(the cell-1/cell-10 method); `multi_back_press` and `abandon_before_submit`
follow.

Each method reads the ordered canonical event sequence, computes a statistic
against the rolling per-screen baseline, and returns a MethodResult. The
discriminator (cell-10 suppression) is applied downstream in detect.py.
"""

from __future__ import annotations

from pulse.detection.detect import (
    MethodResult,
    ScreenBaseline,
    Session,
    elapsed_seconds,
    inv_normal_cdf,
    normal_cdf,
    ordered_events,
    register_method,
)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0

# error_type → FrictionBench root_cause enum (template / release / timing /
# cohort / none). v0.1 heuristic mapping — refined when cause-attribution is
# calibrated against the FrictionBench cause axis.
_ERROR_TYPE_TO_CAUSE = {
    "validation_error": "template",
    "data_load_failed": "timing",
    "account_authorization_lost": "release",
}


def _infer_cause(error_type: str | None) -> str | None:
    if error_type is None:
        return None
    return _ERROR_TYPE_TO_CAUSE.get(error_type, "template")


@register_method("dwell_z_score_vs_screen_baseline")
def dwell_z_score_vs_screen_baseline(
    session: Session, analytic: dict, baseline: ScreenBaseline
) -> MethodResult:
    """Fire when post-error dwell is anomalously long vs the screen baseline.

    Trigger (from the pack's `analytic.trigger`):
      - `requires_prior_event`: an error of this error_type must precede the dwell
      - `p_value_threshold`: fire when the one-sided upper-tail p-value < threshold

    Reads the ordered event sequence: finds the required prior error, then the
    next `dwell` event, z-scores its duration against the rolling baseline.
    Confidence = P(friction) = Φ(z) (upper tail). No qualifying dwell-after-error,
    or a degenerate baseline → no fire, low confidence.
    """
    trigger = analytic.get("trigger", {})
    required_prior = trigger.get("requires_prior_event")
    p_threshold = float(trigger.get("p_value_threshold", 0.01))

    events = ordered_events(session)
    t0 = events[0].get("event", {}).get("event_ts") if events else None

    seen_required_error = False
    matched_error_type: str | None = None
    error_count = 0
    dwell_seconds: float | None = None
    dwell_ts: str | None = None

    for e in events:
        ev = e.get("event", {})
        etype = ev.get("event_type")
        payload = ev.get("payload", {}) or {}
        if etype == "error":
            error_count += 1
            err = payload.get("error_type")
            # required_prior None → any error qualifies; else exact match
            if required_prior is None or err == required_prior:
                seen_required_error = True
                matched_error_type = err
        elif etype == "dwell" and seen_required_error and dwell_seconds is None:
            dwell_seconds = float(payload.get("duration_seconds", 0.0))
            dwell_ts = ev.get("event_ts")

    base_evidence = {
        "dwell_time_seconds": dwell_seconds,
        "error_event_count": error_count,
        "error_type": matched_error_type,
        "baseline_mean": baseline.mean,
        "baseline_std": baseline.std,
        "baseline_n_sessions": baseline.n_sessions,
    }

    # No qualifying dwell-after-error, or unusable baseline → abstain.
    if dwell_seconds is None or baseline.std <= 0.0:
        return MethodResult(
            fire_candidate=False,
            confidence=0.0,
            root_cause=None,
            time_to_detect_seconds=None,
            evidence={**base_evidence, "reason": "no_qualifying_dwell_or_baseline"},
        )

    z = (dwell_seconds - baseline.mean) / baseline.std
    p_value = 1.0 - normal_cdf(z)          # upper tail: long dwell = friction
    confidence = normal_cdf(z)             # P(friction)
    fire = p_value < p_threshold

    return MethodResult(
        fire_candidate=fire,
        confidence=confidence,
        root_cause=_infer_cause(matched_error_type),
        time_to_detect_seconds=elapsed_seconds(t0, dwell_ts),
        evidence={**base_evidence, "z_score": round(z, 4), "p_value": round(p_value, 6)},
    )


@register_method("back_press_burst_detection")
def back_press_burst_detection(
    session: Session, analytic: dict, baseline: ScreenBaseline
) -> MethodResult:
    """Fire on a burst of back-presses (navigation confusion).

    Trigger: `min_back_press_events`, `window_seconds`, `same_screen_required`.
    Inline discriminator (`analytic.discriminator`): `inter_press_interval_under_seconds`
    — a tight burst is confusion; long intervals are deliberate review and must
    NOT fire. Reads back_press events from the ordered sequence, measures the
    inter-press intervals, fires only when the burst is both big enough and tight.
    `baseline` is unused here (count/interval-driven, not a screen-dwell z-score).
    """
    trigger = analytic.get("trigger", {})
    min_events = int(trigger.get("min_back_press_events", 3))
    window_s = float(trigger.get("window_seconds", 300))
    same_screen_required = bool(trigger.get("same_screen_required", True))

    disc = analytic.get("discriminator", {}) or {}
    max_interval = (
        float(disc["value"])
        if disc.get("rule") == "inter_press_interval_under_seconds" and "value" in disc
        else None
    )

    events = ordered_events(session)
    t0 = events[0].get("event", {}).get("event_ts") if events else None

    bp = [e for e in events if e.get("event", {}).get("event_type") == "back_press"]
    if same_screen_required:
        bp = [e for e in bp if e.get("context", {}).get("screen_id") == session.screen_id]

    count = len(bp)
    ts = [e.get("event", {}).get("event_ts") for e in bp]
    intervals = [
        d for d in (elapsed_seconds(a, b) for a, b in zip(ts, ts[1:])) if d is not None
    ]
    median_interval = _median(intervals)
    span = elapsed_seconds(ts[0], ts[-1]) if len(ts) >= 2 else 0.0
    within_window = span is None or span <= window_s

    base_evidence = {
        "back_press_event_count": count,
        "inter_press_intervals_seconds": [round(i, 2) for i in intervals],
        "median_inter_press_interval_seconds": (
            round(median_interval, 2) if median_interval is not None else None
        ),
        "burst_span_seconds": round(span, 2) if span is not None else None,
    }

    meets_count = count >= min_events and within_window
    tight = max_interval is None or (median_interval is not None and median_interval < max_interval)

    if meets_count and tight:
        excess = count - min_events
        tightness = (
            max(0.0, (max_interval - median_interval) / max_interval)
            if (max_interval and median_interval is not None) else 0.0
        )
        confidence = round(min(0.80 + 0.04 * excess + 0.15 * tightness, 0.99), 4)
        ttd = elapsed_seconds(t0, ts[min_events - 1]) if len(ts) >= min_events else None
        return MethodResult(True, confidence, "template", ttd, base_evidence)

    if meets_count and not tight:
        # Enough presses but long intervals → deliberate review, not confusion.
        return MethodResult(
            False, 0.25, None, None,
            {**base_evidence, "reason": "long_intervals_deliberate_review"},
        )
    return MethodResult(
        False, round(min(count / max(min_events, 1), 1.0) * 0.20, 4), None, None,
        {**base_evidence, "reason": "below_burst_threshold"},
    )


@register_method("terminal_abandonment_detection")
def terminal_abandonment_detection(
    session: Session, analytic: dict, baseline: ScreenBaseline
) -> MethodResult:
    """Fire on high-intent terminal abandonment.

    Trigger: `requires_prior_step_completion`, `requires_dwell_above_percentile`,
    `requires_exit_without_event` (e.g. submit_clicked). Exclusion:
    `session_returned_within_seconds` (short-window return = tab-park, not
    abandonment). Structural gates first (prior steps done, not submitted, not a
    quick return); then dwell above the required percentile of the screen baseline.
    Session-level signals come from `session.features` (the sessionisation layer)."""
    trigger = analytic.get("trigger", {})
    required_steps = list(trigger.get("requires_prior_step_completion", []))
    pct = float(trigger.get("requires_dwell_above_percentile", 90))
    exit_without = trigger.get("requires_exit_without_event", "submit_clicked")

    return_window = None
    for ex in analytic.get("exclusions", []) or []:
        if isinstance(ex, dict) and "session_returned_within_seconds" in ex:
            return_window = float(ex["session_returned_within_seconds"])

    feats = session.features
    completed = set(feats.get("prior_steps_completed", []))
    prior_done = all(s in completed for s in required_steps)
    submitted = bool(feats.get(exit_without, False)) or any(
        (e.get("event", {}).get("payload", {}) or {}).get("action") == exit_without
        for e in session.events
    )
    returned_s = feats.get("session_returned_within_seconds")
    excluded = return_window is not None and returned_s is not None and returned_s < return_window

    dwell = feats.get("time_on_step_seconds")
    if dwell is None:
        for e in ordered_events(session):
            if e.get("event", {}).get("event_type") == "dwell":
                dwell = float(e.get("event", {}).get("payload", {}).get("duration_seconds", 0.0))
                break
    prior_error_count = sum(
        1 for e in session.events if e.get("event", {}).get("event_type") == "error"
    )

    base_evidence = {
        "time_on_step_seconds": dwell,
        "prior_steps_completed": sorted(completed),
        "submitted": submitted,
        "session_returned_within_seconds": returned_s,
        "prior_error_count": prior_error_count,
        "return_flag": feats.get("returned_within_24h", feats.get("return_within_7_days")),
    }

    if not prior_done or submitted or excluded or dwell is None or baseline.std <= 0.0:
        reason = (
            "submitted" if submitted
            else "returned_excluded" if excluded
            else "prior_steps_incomplete" if not prior_done
            else "no_dwell_or_baseline"
        )
        # Submitted / returned are decisive "not abandonment" → near-zero confidence.
        conf = 0.02 if (submitted or excluded) else 0.0
        return MethodResult(False, conf, None, None, {**base_evidence, "reason": reason})

    threshold = baseline.mean + inv_normal_cdf(pct / 100.0) * baseline.std
    z = (dwell - baseline.mean) / baseline.std
    confidence = round(normal_cdf(z), 4)
    fire = dwell > threshold

    if fire:
        events = ordered_events(session)
        ttd = elapsed_seconds(
            events[0].get("event", {}).get("event_ts"),
            events[-1].get("event", {}).get("event_ts"),
        ) if events else None
        return MethodResult(True, confidence, "template", ttd,
                            {**base_evidence, "dwell_percentile_threshold": round(threshold, 2)})
    return MethodResult(
        False, confidence, None, None,
        {**base_evidence, "dwell_percentile_threshold": round(threshold, 2),
         "reason": "dwell_below_required_percentile"},
    )
