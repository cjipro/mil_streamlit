"""Decision-pack metadata validator.

The engine calls validate_metadata(meta) at pack registration. Rejection here
means the pack does not run.

v1 constraint enforced: synthesis_mode must be 'deterministic'. Any pack
declaring 'llm_augmented' is rejected — there's no LLM provider class to
resolve it against.

Filed under PULSE-89.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any

import yaml


class DecisionPackMetadataError(ValueError):
    """Raised when a pack's metadata.yaml does not conform to the schema."""


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
_SEMVER_RANGE_RE = re.compile(r"^[<>=!]=?\s*\d+\.\d+\.\d+(\s*,\s*[<>=!]=?\s*\d+\.\d+\.\d+)*$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_ATTESTATION_STATUSES = {"self_declared", "independently_assessed", "certified"}
_REQUIRED_TOP_LEVEL = {
    "pack_name",
    "pack_version",
    "required_pulse_version",
    "synthesis_mode",
    "authors",
    "license",
    "fairness_methods_required",
    "compliance_attestations",
}


def load_metadata(path: Path | str) -> dict[str, Any]:
    """Load a pack's metadata.yaml and validate it. Returns the parsed dict on success."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    validate_metadata(meta)
    return meta


def validate_metadata(meta: dict[str, Any]) -> None:
    """Validate a parsed metadata dict. Raises DecisionPackMetadataError on any violation."""
    if not isinstance(meta, dict):
        raise DecisionPackMetadataError(
            f"metadata must be a mapping, got {type(meta).__name__}"
        )

    missing = _REQUIRED_TOP_LEVEL - set(meta.keys())
    if missing:
        raise DecisionPackMetadataError(f"missing required fields: {sorted(missing)}")

    if not isinstance(meta["pack_name"], str) or not meta["pack_name"]:
        raise DecisionPackMetadataError("pack_name must be a non-empty string")

    if not isinstance(meta["pack_version"], str) or not _SEMVER_RE.match(meta["pack_version"]):
        raise DecisionPackMetadataError(
            f"pack_version must be semver (e.g. '1.0.0'), got {meta['pack_version']!r}"
        )

    if not isinstance(meta["required_pulse_version"], str) or not _SEMVER_RANGE_RE.match(
        meta["required_pulse_version"]
    ):
        raise DecisionPackMetadataError(
            "required_pulse_version must be a semver range expression "
            f"(e.g. '>=1.0.0,<2.0.0'), got {meta['required_pulse_version']!r}"
        )

    # v1 IMMUTABILITY: synthesis_mode must be 'deterministic'. 'llm_augmented' is rejected.
    mode = meta["synthesis_mode"]
    if mode == "llm_augmented":
        raise DecisionPackMetadataError(
            "synthesis_mode='llm_augmented' is not permitted in v1. "
            "Enabling LLM-augmented synthesis requires (1) a new LLMSynthesisProvider "
            "implementation, (2) a new decision-pack version, (3) FrictionBench LLM-track "
            "submission, and (4) explicit governance review. See "
            "pulse/synthesis/SYNTHESIS_DESIGN.md for the v2 enablement path."
        )
    if mode != "deterministic":
        raise DecisionPackMetadataError(
            f"synthesis_mode must be 'deterministic' in v1, got {mode!r}"
        )

    if not isinstance(meta["authors"], list) or not all(
        isinstance(a, str) for a in meta["authors"]
    ):
        raise DecisionPackMetadataError("authors must be a list of strings")

    if not isinstance(meta["license"], str) or not meta["license"]:
        raise DecisionPackMetadataError("license must be a non-empty SPDX identifier string")

    if not isinstance(meta["fairness_methods_required"], bool):
        raise DecisionPackMetadataError("fairness_methods_required must be a boolean")

    attestations = meta["compliance_attestations"]
    if not isinstance(attestations, list):
        raise DecisionPackMetadataError("compliance_attestations must be a list")
    for i, attestation in enumerate(attestations):
        _validate_attestation(i, attestation)


def _validate_attestation(index: int, attestation: Any) -> None:
    if not isinstance(attestation, dict):
        raise DecisionPackMetadataError(
            f"compliance_attestations[{index}] must be a mapping"
        )
    for required in ("name", "status", "last_reviewed"):
        if required not in attestation:
            raise DecisionPackMetadataError(
                f"compliance_attestations[{index}] missing '{required}'"
            )
    if not isinstance(attestation["name"], str) or not attestation["name"]:
        raise DecisionPackMetadataError(
            f"compliance_attestations[{index}].name must be a non-empty string"
        )
    if attestation["status"] not in _ATTESTATION_STATUSES:
        raise DecisionPackMetadataError(
            f"compliance_attestations[{index}].status must be one of "
            f"{sorted(_ATTESTATION_STATUSES)}, got {attestation['status']!r}"
        )
    last_reviewed = attestation["last_reviewed"]
    # PyYAML auto-parses unquoted YYYY-MM-DD as datetime.date. Accept both that
    # and an explicitly-quoted string in the right format.
    if isinstance(last_reviewed, _dt.date) and not isinstance(last_reviewed, _dt.datetime):
        return
    if not isinstance(last_reviewed, str) or not _ISO_DATE_RE.match(last_reviewed):
        raise DecisionPackMetadataError(
            f"compliance_attestations[{index}].last_reviewed must be ISO date "
            f"(YYYY-MM-DD), got {last_reviewed!r}"
        )
