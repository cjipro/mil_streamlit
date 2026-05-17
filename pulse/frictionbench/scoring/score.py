"""FrictionBench v0.1 — open-source scoring script.

Per ticket AC3: this is the reference per-detection scoring function.
NOT the full harness (Docker streaming runner, leaderboard updater, etc.) —
that's a separate ticket per out-of-scope.

Any submitter can import this module, feed in their detection + the ground
truth row, and get back the same DetectionScore the leaderboard would compute.

Filed under PULSE-88.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_RUBRIC_PATH = Path(__file__).parent / "rubric.yaml"


@dataclass(frozen=True)
class DetectionScore:
    """Per-detection score breakdown."""

    screen: float
    signature: float
    cohort: float
    cause: float
    calibration: float
    time_to_detect_seconds: float | None
    aggregate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "screen": self.screen,
            "signature": self.signature,
            "cohort": self.cohort,
            "cause": self.cause,
            "calibration": self.calibration,
            "time_to_detect_seconds": self.time_to_detect_seconds,
            "aggregate": self.aggregate,
        }


@functools.lru_cache(maxsize=1)
def load_rubric() -> dict[str, Any]:
    with _RUBRIC_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def score_detection(
    detection: dict[str, Any],
    ground_truth: dict[str, Any],
    journey_for_screen: dict[str, str] | None = None,
    signature_families: dict[str, set[str]] | None = None,
) -> DetectionScore:
    """Score one detection against one ground-truth row. Pure function.

    Args:
        detection: detector output. Expected keys:
            - screen_id (str)
            - signature_id (str)
            - cohort_tags (list[str])
            - root_cause (str)
            - confidence (float in [0, 1])
            - time_to_detect_seconds (float | None)
        ground_truth: ground-truth row matching ground_truth_schema.yaml.
        journey_for_screen: screen_id -> journey_id map, for same-journey-wrong-step
            partial credit on the screen axis. If omitted, no partial credit.
        signature_families: signature_id -> set of related signature_ids, for
            same-family partial credit on the signature axis. Defaults to rubric.

    Returns:
        DetectionScore with all axes filled.
    """
    rubric = load_rubric()
    families = signature_families or {
        k: set(v) for k, v in rubric.get("signature_families", {}).items()
    }
    journey_for_screen = journey_for_screen or {}

    screen = _score_screen(
        detection.get("screen_id"),
        ground_truth["screen_id"],
        journey_for_screen,
    )
    signature = _score_signature(
        detection.get("signature_id"),
        ground_truth["signature_id"],
        families,
    )
    cohort = _score_cohort(
        detection.get("cohort_tags", []),
        ground_truth.get("cohort_tags", []),
    )
    cause = _score_cause(
        detection.get("root_cause"),
        ground_truth.get("root_cause"),
    )
    calibration = _score_calibration(
        detection.get("confidence"),
        ground_truth.get("should_fire", False),
    )

    weights = rubric["aggregate_weights"]
    aggregate = (
        screen * weights["screen"]
        + signature * weights["signature"]
        + cohort * weights["cohort"]
        + cause * weights["cause"]
        + calibration * weights["calibration"]
    )

    return DetectionScore(
        screen=screen,
        signature=signature,
        cohort=cohort,
        cause=cause,
        calibration=calibration,
        time_to_detect_seconds=detection.get("time_to_detect_seconds"),
        aggregate=aggregate,
    )


def aggregate_cell(scores: list[DetectionScore]) -> float:
    """Mean aggregate across all detections in a cell."""
    if not scores:
        return 0.0
    return sum(s.aggregate for s in scores) / len(scores)


def macro_average(cell_aggregates: list[float]) -> float:
    """Macro-average across cells. Each cell contributes equally regardless of session count."""
    if not cell_aggregates:
        return 0.0
    return sum(cell_aggregates) / len(cell_aggregates)


def apply_false_positive_penalty(
    macro_score: float,
    false_positive_count: int,
    rubric: dict[str, Any] | None = None,
) -> float:
    """Subtract the per-FP penalty, floored at the rubric's floor (0.0 at v0.1)."""
    r = rubric or load_rubric()
    cfg = r["false_positive_penalty"]
    penalised = macro_score - cfg["amount_per_fp"] * false_positive_count
    return max(cfg["floor"], penalised)


# ── per-axis scorers ──────────────────────────────────────────────────────────


def _score_screen(
    detected: str | None,
    truth: str,
    journey_for_screen: dict[str, str],
) -> float:
    if detected is None:
        return 0.0
    if detected == truth:
        return 1.0
    detected_journey = journey_for_screen.get(detected)
    truth_journey = journey_for_screen.get(truth)
    if detected_journey and detected_journey == truth_journey:
        return 0.5
    return 0.0


def _score_signature(
    detected: str | None,
    truth: str,
    families: dict[str, set[str]],
) -> float:
    # Truth 'none' is the negative-cell case — correct detection is "did not fire."
    # Detector that fires anyway is scored 0; detector that abstained scored 1.
    if truth == "none":
        return 1.0 if detected in (None, "none") else 0.0

    if detected is None:
        return 0.0
    if detected == truth:
        return 1.0
    # Same-family partial credit.
    truth_family = families.get(truth, set())
    if detected in truth_family:
        return 0.5
    return 0.0


def _score_cohort(
    detected_tags: list[str],
    truth_tags: list[str],
) -> float:
    """Multi-label F1. Treats each tag independently."""
    if not detected_tags and not truth_tags:
        return 1.0  # both empty — perfect agreement
    if not detected_tags or not truth_tags:
        return 0.0
    detected_set = set(detected_tags)
    truth_set = set(truth_tags)
    tp = len(detected_set & truth_set)
    if tp == 0:
        return 0.0
    precision = tp / len(detected_set)
    recall = tp / len(truth_set)
    return 2 * precision * recall / (precision + recall)


def _score_cause(detected: str | None, truth: str | None) -> float:
    # Truth 'none' (or absent) means there's no cause to identify — correct
    # detection is silence; detector that names a cause is scored 0.
    if truth in (None, "none"):
        return 1.0 if detected in (None, "none") else 0.0

    if detected is None or detected == "none":
        return 0.0
    if detected == truth:
        return 1.0

    # Plausible-component: same cause-family (template/release/timing/cohort)
    # but different specific cause. v0.1 doesn't ship a cause-family registry,
    # so this branch returns 0.5 only when the rubric's plausibility metadata
    # populates a family. Hook left here for downstream extension.
    plausible_components = {
        "template": {"copy", "field", "validation"},
        "release": {"deployment", "rollout"},
        "timing": {"latency", "load"},
        "cohort": {"segment", "audience"},
    }
    truth_components = plausible_components.get(truth, set())
    if detected in truth_components:
        return 0.5

    # Plausible-but-wrong: detected a known cause category that isn't this truth.
    if detected in plausible_components:
        return 0.2

    return 0.0


def _score_calibration(
    confidence: float | None,
    actual_outcome: bool,
) -> float:
    """1 - Brier score. Returns 0.0 if confidence missing or out of [0, 1]."""
    if confidence is None:
        return 0.0
    if not (0.0 <= confidence <= 1.0):
        return 0.0
    o = 1.0 if actual_outcome else 0.0
    brier = (confidence - o) ** 2
    return 1.0 - brier
