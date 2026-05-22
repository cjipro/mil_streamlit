"""Pulse Diagnosis methodology v0 — problem-locus disambiguation.

Pure function. Same inputs always produce the same DiagnosisResult; the
methodology_version is pinned in every output for audit.

Runs BEFORE Value/Risk tier scoring in the decision flow. Answers:
"is this a SUPPORT problem (fix the help layer / deploy AI assistance),
a JOURNEY problem (fix the journey itself), BOTH, or INCONCLUSIVE
(insufficient control-arm data)?"

Compares the assistance-using arm against the no-assistance (control)
arm on the same journey. The gap in success rates between the two arms
is the diagnostic signal. Thresholds live in rubric.yaml.

Filed under PULSE-105.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_RUBRIC_PATH = Path(__file__).parent / "rubric.yaml"


@dataclass(frozen=True)
class JourneyIdentity:
    """The journey being diagnosed."""

    journey_id: str
    screen_class: str


@dataclass(frozen=True)
class JourneyArmObservation:
    """Observed sessions for one arm of a journey (assistance-using OR
    no-assistance control)."""

    n_sessions: int
    success_rate: float  # 0..1, share that completed the journey successfully


@dataclass(frozen=True)
class DiagnosisResult:
    """Computed Diagnosis tier + audit footprint.

    `diagnosis` is one of the rubric's closed enum:
    SUPPORT_PROBLEM / JOURNEY_PROBLEM / BOTH / INCONCLUSIVE.

    `gap` = success_rate(no_assistance) − success_rate(assistance).

    Both arms' n_sessions + success_rate are echoed back for audit
    transparency. `methodology_version` + `inputs_hash` together let
    any consumer reproduce or contest the diagnosis later."""

    diagnosis: str
    gap: float
    assistance_arm_n: int
    assistance_arm_success_rate: float
    no_assistance_arm_n: int
    no_assistance_arm_success_rate: float
    methodology_version: str
    inputs_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "diagnosis": self.diagnosis,
            "gap": self.gap,
            "assistance_arm_n": self.assistance_arm_n,
            "assistance_arm_success_rate": self.assistance_arm_success_rate,
            "no_assistance_arm_n": self.no_assistance_arm_n,
            "no_assistance_arm_success_rate": self.no_assistance_arm_success_rate,
            "methodology_version": self.methodology_version,
            "inputs_hash": self.inputs_hash,
        }


@functools.lru_cache(maxsize=1)
def load_rubric() -> dict[str, Any]:
    with _RUBRIC_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def diagnose_problem_locus(
    *,
    journey: JourneyIdentity,
    assistance_arm: JourneyArmObservation,
    no_assistance_arm: JourneyArmObservation,
) -> DiagnosisResult:
    """Compute problem-locus diagnosis. Pure function — same inputs →
    identical DiagnosisResult."""
    rubric = load_rubric()
    _validate_arm("assistance_arm", assistance_arm)
    _validate_arm("no_assistance_arm", no_assistance_arm)

    # Round gap to 4dp so binary float artefacts (e.g. 0.70 - 0.50 returning
    # 0.19999...) don't cause inputs that "look" at the threshold to fall on
    # the wrong side. Keeps audit output clean too.
    gap = round(no_assistance_arm.success_rate - assistance_arm.success_rate, 4)

    min_control = int(rubric["min_control_sessions"])
    support_gap = float(rubric["thresholds"]["support_problem_gap"]["value"])
    journey_gap = float(rubric["thresholds"]["journey_problem_gap"]["value"])
    journey_assistance_max = float(
        rubric["thresholds"]["journey_problem_assistance_success_max"]["value"]
    )

    if no_assistance_arm.n_sessions < min_control:
        diagnosis = "INCONCLUSIVE"
    elif gap >= support_gap:
        diagnosis = "SUPPORT_PROBLEM"
    elif (
        gap <= journey_gap
        and assistance_arm.success_rate < journey_assistance_max
    ):
        diagnosis = "JOURNEY_PROBLEM"
    else:
        diagnosis = "BOTH"

    inputs_hash = _hash_inputs(journey, assistance_arm, no_assistance_arm)

    return DiagnosisResult(
        diagnosis=diagnosis,
        gap=gap,
        assistance_arm_n=assistance_arm.n_sessions,
        assistance_arm_success_rate=assistance_arm.success_rate,
        no_assistance_arm_n=no_assistance_arm.n_sessions,
        no_assistance_arm_success_rate=no_assistance_arm.success_rate,
        methodology_version=str(rubric["methodology_version"]),
        inputs_hash=inputs_hash,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _validate_arm(name: str, arm: JourneyArmObservation) -> None:
    if isinstance(arm.n_sessions, bool) or not isinstance(arm.n_sessions, int):
        raise ValueError(f"{name}.n_sessions must be a non-negative integer")
    if arm.n_sessions < 0:
        raise ValueError(f"{name}.n_sessions must be a non-negative integer")
    if not isinstance(arm.success_rate, (int, float)) or isinstance(
        arm.success_rate, bool
    ):
        raise ValueError(f"{name}.success_rate must be a number in [0, 1]")
    if not (0.0 <= arm.success_rate <= 1.0):
        raise ValueError(
            f"{name}.success_rate must be in [0, 1], got {arm.success_rate}"
        )


def _hash_inputs(
    journey: JourneyIdentity,
    assistance_arm: JourneyArmObservation,
    no_assistance_arm: JourneyArmObservation,
) -> str:
    payload = {
        "journey": {
            "journey_id": journey.journey_id,
            "screen_class": journey.screen_class,
        },
        "assistance_arm": {
            "n_sessions": assistance_arm.n_sessions,
            "success_rate": assistance_arm.success_rate,
        },
        "no_assistance_arm": {
            "n_sessions": no_assistance_arm.n_sessions,
            "success_rate": no_assistance_arm.success_rate,
        },
    }
    serialised = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()
