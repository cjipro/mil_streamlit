"""Pulse detection runtime — core (PULSE-126).

Executes a decision pack's declarative `analytic` spec over a canonical-event
session and emits a FrictionBench-shaped detection. **Interpreter, not
inventor:** the detection logic lives in each pack's `hypothesis.yaml`
(`analytic` + `negative_class_discriminator`); this module runs it. Classical,
deterministic, explainable — per the non-LLM runtime lock.

The emitted `Detection.to_scoring_dict()` matches exactly what
`pulse.frictionbench.scoring.score_detection` consumes (screen_id,
signature_id, cohort_tags, root_cause, confidence, time_to_detect_seconds), so
every detection is directly benchmarkable.

Reproducibility: same (hypothesis + session + baseline) → identical Detection,
incl. `inputs_hash`. The `runtime_version` here + the pack's `analytic` version
together pin a detection for audit.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Callable

DETECTION_RUNTIME_VERSION = "0.1.0"

# When the negative-class discriminator suppresses a candidate, the engine's
# belief that this session exhibits friction collapses. We cap the emitted
# confidence at this ceiling so a suppressed cell-10-style session reports a
# correctly LOW probability-of-friction (good Brier calibration on negatives).
_SUPPRESSED_CONFIDENCE_CEILING = 0.10


# ── inputs ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Session:
    """One canonical-event session — the unit of detection.

    `events` are canonical events (PULSE-87 shape); the runtime orders them by
    `context.sequence_no` (NOT event_ts — network may reorder). `features` are
    session-level aggregates the sessionisation layer (MA_S) derives, used by
    the discriminator's session-level suppression signals (scroll_depth_pct,
    chart_drilldowns_in_session, return_within_7_days, …)."""

    session_id: str
    screen_id: str
    cohort_tags: tuple[str, ...]
    events: tuple[dict, ...]
    features: dict


@dataclass(frozen=True)
class ScreenBaseline:
    """Rolling per-screen baseline a method scores against (e.g.
    rolling_28d_same_screen). `mean`/`std` are over the metric (dwell_seconds)."""

    screen_id: str
    metric: str
    mean: float
    std: float
    n_sessions: int


# ── output ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Detection:
    """A friction detection, FrictionBench-shaped + audit footprint.

    `signature_id` is None when the detector did not fire (the FrictionBench
    "abstain" — correct response on a negative cell). `confidence` is the
    calibrated P(this session exhibits the signature) and is reported whether
    or not it fired (a correct non-fire reports LOW confidence). `evidence`
    carries the `evidence_required` fields the pack declared, for the audit
    bundle."""

    fired: bool
    screen_id: str
    signature_id: str | None
    cohort_tags: tuple[str, ...]
    root_cause: str | None
    confidence: float | None
    time_to_detect_seconds: float | None
    evidence: dict
    suppressed_by: tuple[str, ...]
    method: str
    runtime_version: str
    inputs_hash: str

    def to_scoring_dict(self) -> dict[str, Any]:
        """The exact shape pulse.frictionbench.scoring.score_detection expects."""
        return {
            "screen_id": self.screen_id,
            "signature_id": self.signature_id,
            "cohort_tags": list(self.cohort_tags),
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "time_to_detect_seconds": self.time_to_detect_seconds,
        }


@dataclass(frozen=True)
class MethodResult:
    """What a detection method returns before the discriminator is applied."""

    fire_candidate: bool
    confidence: float        # P(friction) from the statistic, 0..1
    root_cause: str | None
    time_to_detect_seconds: float | None
    evidence: dict


# ── method registry ────────────────────────────────────────────────────────────

MethodFn = Callable[[Session, dict, ScreenBaseline], MethodResult]
_REGISTRY: dict[str, MethodFn] = {}


def register_method(name: str) -> Callable[[MethodFn], MethodFn]:
    def deco(fn: MethodFn) -> MethodFn:
        _REGISTRY[name] = fn
        return fn
    return deco


def get_method(name: str) -> MethodFn:
    if name not in _REGISTRY:
        raise ValueError(
            f"unknown analytic.method {name!r}; registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def registered_methods() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


# ── orchestration ──────────────────────────────────────────────────────────────


def run_detection(
    *, hypothesis: dict, session: Session, baseline: ScreenBaseline
) -> Detection:
    """Execute a pack's analytic spec over one session. Pure function."""
    analytic = hypothesis.get("analytic", {})
    method_name = analytic.get("method")
    if not method_name:
        raise ValueError("hypothesis.analytic.method is required")
    method = get_method(method_name)

    screen_id = hypothesis.get("screen_id") or session.screen_id
    signature_id = hypothesis.get("signature_id")
    discriminator = hypothesis.get("negative_class_discriminator")

    # Screen-scoping: a pack only evaluates sessions on its own screen. This is
    # the FrictionBench "~zero false positives on the 754 non-target screens"
    # property — a pack cannot fire on a screen it doesn't own. Abstain cleanly.
    hyp_screen = hypothesis.get("screen_id")
    if hyp_screen and session.screen_id != hyp_screen:
        return Detection(
            fired=False,
            screen_id=hyp_screen,
            signature_id=None,
            cohort_tags=(),
            root_cause=None,
            confidence=0.0,
            time_to_detect_seconds=None,
            evidence={"reason": "screen_mismatch", "session_screen": session.screen_id},
            suppressed_by=(),
            method=method_name,
            runtime_version=DETECTION_RUNTIME_VERSION,
            inputs_hash=_hash_inputs(hypothesis, session, baseline),
        )

    result = method(session, analytic, baseline)
    suppress, signals_hit = _apply_discriminator(discriminator, session)
    fired = result.fire_candidate and not suppress

    # Suppression is decisive negative evidence — collapse P(friction).
    if suppress:
        confidence = round(min(result.confidence, _SUPPRESSED_CONFIDENCE_CEILING), 4)
    else:
        confidence = round(result.confidence, 4)

    evidence = dict(result.evidence)
    evidence["discriminator_signals_hit"] = list(signals_hit)

    return Detection(
        fired=fired,
        screen_id=screen_id,
        signature_id=signature_id if fired else None,
        cohort_tags=session.cohort_tags if fired else (),
        root_cause=result.root_cause if fired else None,
        confidence=confidence,
        time_to_detect_seconds=result.time_to_detect_seconds if fired else None,
        evidence=evidence,
        suppressed_by=signals_hit,
        method=method_name,
        runtime_version=DETECTION_RUNTIME_VERSION,
        inputs_hash=_hash_inputs(hypothesis, session, baseline),
    )


# ── discriminator ──────────────────────────────────────────────────────────────


def _apply_discriminator(
    discriminator: dict | None, session: Session
) -> tuple[bool, tuple[str, ...]]:
    """Apply negative_class_discriminator suppression signals against session
    features. Returns (suppress, signals_hit). The cell-10 false-positive
    defence: long dwell on a Premier portfolio screen with engagement signals
    present is interest, not friction.

    v0.1 honours the structured `suppression_signals`. The free-text
    `fire_only_if` clause (e.g. "… AND error_type IN […]") is not yet parsed —
    tracked as a follow-up; suppression_signals carry the cell-10 negative."""
    if not discriminator:
        return (False, ())
    hits: list[str] = []
    for sig in discriminator.get("suppression_signals", []):
        name = sig.get("signal")
        threshold = sig.get("threshold")
        direction = sig.get("direction")
        val = session.features.get(name)
        if val is None or threshold is None:
            continue
        if direction == "above" and val > threshold:
            hits.append(name)
        elif direction == "above_or_equal" and val >= threshold:
            hits.append(name)
        elif direction == "below" and val < threshold:
            hits.append(name)
        elif direction == "below_or_equal" and val <= threshold:
            hits.append(name)
        elif direction == "equals" and val == threshold:
            hits.append(name)
    return (len(hits) > 0, tuple(hits))


# ── shared math/helpers (used by methods too) ──────────────────────────────────


def normal_cdf(z: float) -> float:
    """Standard normal CDF via stdlib erf (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def inv_normal_cdf(p: float) -> float:
    """Inverse standard normal CDF (probit) — Acklam's rational approximation.
    Stdlib-only (no scipy). Used to turn a percentile threshold (e.g. 90th)
    into a z multiplier. inv_normal_cdf(0.90) ≈ 1.2816."""
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)


def elapsed_seconds(start_ts: str | None, end_ts: str | None) -> float | None:
    """Seconds between two ISO-8601 timestamps; None if either is unparseable."""
    if not start_ts or not end_ts:
        return None
    try:
        a = _dt.datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        b = _dt.datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (b - a).total_seconds()


def ordered_events(session: Session) -> list[dict]:
    """Canonical events ordered by sequence_no (authoritative, not event_ts)."""
    return sorted(session.events, key=lambda e: e.get("context", {}).get("sequence_no", 0))


def _hash_inputs(hypothesis: dict, session: Session, baseline: ScreenBaseline) -> str:
    payload = {
        "analytic": hypothesis.get("analytic", {}),
        "signature_id": hypothesis.get("signature_id"),
        "screen_id": hypothesis.get("screen_id"),
        "discriminator": hypothesis.get("negative_class_discriminator"),
        "session_id": session.session_id,
        "events": [
            {
                "sequence_no": e.get("context", {}).get("sequence_no"),
                "event_type": e.get("event", {}).get("event_type"),
                "payload": e.get("event", {}).get("payload", {}),
            }
            for e in ordered_events(session)
        ],
        "features": session.features,
        "baseline": {
            "screen_id": baseline.screen_id,
            "metric": baseline.metric,
            "mean": baseline.mean,
            "std": baseline.std,
        },
        "runtime_version": DETECTION_RUNTIME_VERSION,
    }
    serialised = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()
