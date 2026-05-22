"""Decision-pack hypothesis validator (PULSE-103).

The engine calls validate_hypothesis(hyp) at pack registration alongside
the existing metadata validator. Rejection here means the pack does not
run.

Two gates enforced:

1. **Canvas-completeness** — pack MUST declare `actors`, `value_inputs`,
   `risk_inputs`. Mirrors today's required-field check on metadata.yaml.

2. **Computed-slot immutability** — pack MUST NOT declare `value_output`
   or `risk_output`. Those are engine-computed at runtime, never
   author-supplied. Mirrors the synthesis_mode v1 immutability gate.

Cross-validation:
- `risk_inputs.regulatory_taxonomies` must reference taxonomy codes
  registered in pulse/risk/regulatory_taxonomy.yaml.
- `risk_inputs.chronicle_precedents` (if present) must match the
  CHR-friction-NNN naming convention.
- `risk_inputs.policy_areas` is NOT cross-validated — bank_policy is
  per-deployment, so pack-registration time has no bank_policy yet.

Filed under PULSE-103.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class DecisionPackHypothesisError(ValueError):
    """Raised when a pack's hypothesis.yaml does not conform to the schema."""


_ACTORS_ENUM = {
    "investigation_consumer",
    "ml_engineer",
    "mrm_reviewer",
    "compliance_reviewer",
}

_SEVERITY_CLASS_ENUM = {"high", "medium", "low"}

_CHR_FRICTION_RE = re.compile(r"^CHR-friction-\d{3,}$")

_REQUIRED_TOP_LEVEL = {"actors", "value_inputs", "risk_inputs"}
_FORBIDDEN_TOP_LEVEL = {"value_output", "risk_output"}

_REQUIRED_VALUE_INPUTS = {
    "severity_class",
    "vulnerable_cohort_sensitivity",
    "population_segment_addressed",
}

_REQUIRED_RISK_INPUTS = {"regulatory_taxonomies", "policy_areas"}

# Path to the regulatory taxonomy — loaded lazily to avoid import-time
# cycles (the validator can be imported before pulse.risk loads).
_TAXONOMY_PATH = (
    Path(__file__).parent.parent / "risk" / "regulatory_taxonomy.yaml"
)


def load_hypothesis(path: Path | str) -> dict[str, Any]:
    """Load a pack's hypothesis.yaml and validate it. Returns the parsed
    dict on success. Raises DecisionPackHypothesisError on any violation."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        hyp = yaml.safe_load(f)
    validate_hypothesis(hyp)
    return hyp


def validate_hypothesis(hyp: Any) -> None:
    """Validate a parsed hypothesis dict. Raises
    DecisionPackHypothesisError on any violation."""
    if not isinstance(hyp, dict):
        raise DecisionPackHypothesisError(
            f"hypothesis must be a mapping, got {type(hyp).__name__}"
        )

    _check_computed_slot_immutability(hyp)
    _check_canvas_completeness(hyp)

    _validate_actors(hyp["actors"])
    _validate_value_inputs(hyp["value_inputs"])
    _validate_risk_inputs(hyp["risk_inputs"])


def _check_computed_slot_immutability(hyp: dict[str, Any]) -> None:
    """Computed slots are engine-owned. Pack-author declaration is rejected
    with a message pointing at the methodology that owns the slot."""
    if "value_output" in hyp:
        raise DecisionPackHypothesisError(
            "hypothesis must NOT declare 'value_output' — Value is a computed "
            "canvas slot owned by the Value methodology "
            "(pulse/value/VALUE_DESIGN.md). The engine derives the tier from "
            "pack-declared value_inputs + telemetry + bank_policy at runtime."
        )
    if "risk_output" in hyp:
        raise DecisionPackHypothesisError(
            "hypothesis must NOT declare 'risk_output' — Risk is a computed "
            "canvas slot owned by the Risk methodology "
            "(pulse/risk/RISK_DESIGN.md). The engine derives the tier from "
            "pack-declared risk_inputs + telemetry + regulatory_taxonomy + "
            "bank_policy + Chronicle library at runtime."
        )


def _check_canvas_completeness(hyp: dict[str, Any]) -> None:
    missing = _REQUIRED_TOP_LEVEL - set(hyp.keys())
    if missing:
        raise DecisionPackHypothesisError(
            f"hypothesis missing required canvas slots: {sorted(missing)}. "
            "Every decision pack must declare actors, value_inputs, and "
            "risk_inputs (see pulse/decision_packs/HYPOTHESIS_SCHEMA.md)."
        )


def _validate_actors(actors: Any) -> None:
    if not isinstance(actors, list) or not actors:
        raise DecisionPackHypothesisError(
            "actors must be a non-empty list of role identifiers"
        )
    for i, actor in enumerate(actors):
        if actor not in _ACTORS_ENUM:
            raise DecisionPackHypothesisError(
                f"actors[{i}] must be one of {sorted(_ACTORS_ENUM)}, "
                f"got {actor!r}"
            )


def _validate_value_inputs(value_inputs: Any) -> None:
    if not isinstance(value_inputs, dict):
        raise DecisionPackHypothesisError(
            "value_inputs must be a mapping"
        )
    missing = _REQUIRED_VALUE_INPUTS - set(value_inputs.keys())
    if missing:
        raise DecisionPackHypothesisError(
            f"value_inputs missing required keys: {sorted(missing)}"
        )

    severity_class = value_inputs["severity_class"]
    if severity_class not in _SEVERITY_CLASS_ENUM:
        raise DecisionPackHypothesisError(
            f"value_inputs.severity_class must be one of "
            f"{sorted(_SEVERITY_CLASS_ENUM)}, got {severity_class!r}"
        )

    sensitivity = value_inputs["vulnerable_cohort_sensitivity"]
    if not isinstance(sensitivity, bool):
        raise DecisionPackHypothesisError(
            "value_inputs.vulnerable_cohort_sensitivity must be a boolean, "
            f"got {sensitivity!r}"
        )

    segment = value_inputs["population_segment_addressed"]
    if not isinstance(segment, str) or not segment.strip():
        raise DecisionPackHypothesisError(
            "value_inputs.population_segment_addressed must be a non-empty string"
        )


def _validate_risk_inputs(risk_inputs: Any) -> None:
    if not isinstance(risk_inputs, dict):
        raise DecisionPackHypothesisError("risk_inputs must be a mapping")
    missing = _REQUIRED_RISK_INPUTS - set(risk_inputs.keys())
    if missing:
        raise DecisionPackHypothesisError(
            f"risk_inputs missing required keys: {sorted(missing)}"
        )

    _validate_regulatory_taxonomies(risk_inputs["regulatory_taxonomies"])
    _validate_policy_areas(risk_inputs["policy_areas"])
    # chronicle_precedents is optional
    if "chronicle_precedents" in risk_inputs:
        _validate_chronicle_precedents(risk_inputs["chronicle_precedents"])


def _validate_regulatory_taxonomies(codes: Any) -> None:
    if not isinstance(codes, list):
        raise DecisionPackHypothesisError(
            "risk_inputs.regulatory_taxonomies must be a list (empty list is allowed)"
        )
    if not codes:
        return
    known = _load_known_taxonomy_codes()
    for i, code in enumerate(codes):
        if not isinstance(code, str) or not code:
            raise DecisionPackHypothesisError(
                f"risk_inputs.regulatory_taxonomies[{i}] must be a non-empty string"
            )
        if code not in known:
            raise DecisionPackHypothesisError(
                f"risk_inputs.regulatory_taxonomies[{i}]={code!r} is not a "
                "registered taxonomy code. Add it to "
                "pulse/risk/regulatory_taxonomy.yaml first (that's a methodology-"
                "version change), or correct the typo."
            )


def _validate_policy_areas(areas: Any) -> None:
    if not isinstance(areas, list):
        raise DecisionPackHypothesisError(
            "risk_inputs.policy_areas must be a list (empty list is allowed; "
            "per-deployment bank_policy.yaml resolves these at runtime)"
        )
    for i, area in enumerate(areas):
        if not isinstance(area, str) or not area:
            raise DecisionPackHypothesisError(
                f"risk_inputs.policy_areas[{i}] must be a non-empty string"
            )


def _validate_chronicle_precedents(precedents: Any) -> None:
    if not isinstance(precedents, list):
        raise DecisionPackHypothesisError(
            "risk_inputs.chronicle_precedents must be a list (optional field)"
        )
    for i, precedent in enumerate(precedents):
        if not isinstance(precedent, str) or not _CHR_FRICTION_RE.match(precedent):
            raise DecisionPackHypothesisError(
                f"risk_inputs.chronicle_precedents[{i}]={precedent!r} must "
                "match the CHR-friction-NNN convention"
            )


def _load_known_taxonomy_codes() -> set[str]:
    """Read pulse/risk/regulatory_taxonomy.yaml directly (avoids importing
    pulse.risk, which would create an import cycle with this module's
    transitive callers in some test layouts)."""
    with _TAXONOMY_PATH.open("r", encoding="utf-8") as f:
        taxonomy = yaml.safe_load(f)
    return {entry["taxonomy_code"] for entry in taxonomy["taxonomies"]}
