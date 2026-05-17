"""Tests for the decision-pack metadata validator.

Key invariant: synthesis_mode='llm_augmented' is IMMUTABLY rejected in v1.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pulse.decision_packs import DecisionPackMetadataError, load_metadata, validate_metadata

_EXAMPLE_PACK = (
    Path(__file__).parent.parent / "decision_packs" / "example_pack" / "metadata.yaml"
)


def _good_meta() -> dict:
    return {
        "pack_name": "test_pack",
        "pack_version": "1.0.0",
        "required_pulse_version": ">=1.0.0,<2.0.0",
        "synthesis_mode": "deterministic",
        "authors": ["CJI"],
        "license": "Apache-2.0",
        "fairness_methods_required": True,
        "compliance_attestations": [
            {
                "name": "fca_consumer_duty_2.0",
                "status": "self_declared",
                "last_reviewed": "2026-05-17",
            }
        ],
    }


def test_good_metadata_passes() -> None:
    validate_metadata(_good_meta())


def test_example_pack_fixture_passes() -> None:
    """The shipped example pack must validate — keeps the fixture honest."""
    meta = load_metadata(_EXAMPLE_PACK)
    assert meta["pack_name"] == "journey_friction"


def test_missing_required_field_rejected() -> None:
    bad = _good_meta()
    del bad["synthesis_mode"]
    with pytest.raises(DecisionPackMetadataError, match="missing required"):
        validate_metadata(bad)


def test_synthesis_mode_llm_augmented_rejected() -> None:
    """The v1 immutability check — packs cannot opportunistically switch to LLM mode."""
    bad = _good_meta()
    bad["synthesis_mode"] = "llm_augmented"
    with pytest.raises(DecisionPackMetadataError, match="not permitted in v1"):
        validate_metadata(bad)


def test_synthesis_mode_unknown_rejected() -> None:
    bad = _good_meta()
    bad["synthesis_mode"] = "rogue_mode"
    with pytest.raises(DecisionPackMetadataError, match="must be 'deterministic'"):
        validate_metadata(bad)


def test_pack_version_non_semver_rejected() -> None:
    bad = _good_meta()
    bad["pack_version"] = "v1"
    with pytest.raises(DecisionPackMetadataError, match="semver"):
        validate_metadata(bad)


def test_required_pulse_version_non_range_rejected() -> None:
    bad = _good_meta()
    bad["required_pulse_version"] = "1.0.0"  # missing operator
    with pytest.raises(DecisionPackMetadataError, match="semver range"):
        validate_metadata(bad)


def test_required_pulse_version_range_accepted() -> None:
    for good_range in [">=1.0.0,<2.0.0", ">1.0.0", "==1.0.0", "!=1.0.0", ">=1.0.0"]:
        meta = _good_meta()
        meta["required_pulse_version"] = good_range
        validate_metadata(meta)


def test_authors_must_be_list_of_strings() -> None:
    bad = _good_meta()
    bad["authors"] = "CJI"  # not a list
    with pytest.raises(DecisionPackMetadataError, match="authors"):
        validate_metadata(bad)


def test_license_must_be_non_empty() -> None:
    bad = _good_meta()
    bad["license"] = ""
    with pytest.raises(DecisionPackMetadataError, match="license"):
        validate_metadata(bad)


def test_fairness_methods_required_must_be_bool() -> None:
    bad = _good_meta()
    bad["fairness_methods_required"] = "yes"
    with pytest.raises(DecisionPackMetadataError, match="boolean"):
        validate_metadata(bad)


def test_attestation_missing_field_rejected() -> None:
    bad = _good_meta()
    del bad["compliance_attestations"][0]["last_reviewed"]
    with pytest.raises(DecisionPackMetadataError, match="last_reviewed"):
        validate_metadata(bad)


def test_attestation_bad_status_rejected() -> None:
    bad = _good_meta()
    bad["compliance_attestations"][0]["status"] = "trust_me"
    with pytest.raises(DecisionPackMetadataError, match="status must be one of"):
        validate_metadata(bad)


def test_attestation_bad_date_rejected() -> None:
    bad = _good_meta()
    bad["compliance_attestations"][0]["last_reviewed"] = "May 2026"
    with pytest.raises(DecisionPackMetadataError, match="last_reviewed"):
        validate_metadata(bad)


def test_attestation_status_independently_assessed_accepted() -> None:
    good = _good_meta()
    good["compliance_attestations"][0]["status"] = "independently_assessed"
    validate_metadata(good)


def test_attestation_status_certified_accepted() -> None:
    good = _good_meta()
    good["compliance_attestations"][0]["status"] = "certified"
    validate_metadata(good)


def test_validate_does_not_mutate_input() -> None:
    meta = _good_meta()
    snapshot = copy.deepcopy(meta)
    validate_metadata(meta)
    assert meta == snapshot
