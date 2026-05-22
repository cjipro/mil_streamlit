"""Tests for FrictionBench submission manifest validator."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pulse.frictionbench.submission import (
    SubmissionManifestError,
    load_manifest,
    validate_manifest,
)

_EXAMPLE_MANIFEST = (
    Path(__file__).parent.parent
    / "frictionbench"
    / "submission"
    / "example_submission_manifest.yaml"
)


def _det_manifest() -> dict:
    return {
        "system_name": "test-system",
        "system_version": "1.0.0",
        "track": "deterministic",
        "benchmark_version": "0.1.0",
        "runtime_architecture_summary": "Classical ML over Pandas; no LLM in runtime path.",
        "pipeline_versions": {"ingest": "0.1.0", "analyse": "0.2.0"},
        "license": "Apache-2.0",
        "contact": {"name": "Test Author", "email": "test@example.com"},
        "docker_image": "ghcr.io/example/test:1.0.0",
        "real_set_reporting": {"status": "unavailable"},
    }


def _llm_manifest() -> dict:
    m = _det_manifest()
    m["track"] = "llm_augmented"
    m["llm_provider"] = "anthropic"
    m["llm_model"] = "claude-opus-4-7"
    m["llm_model_version"] = "20250901"
    m["cost_per_investigation_usd"] = 0.15
    m["latency_per_investigation_ms_median"] = 1200
    m["latency_per_investigation_ms_p95"] = 4500
    return m


# ── Happy paths ──────────────────────────────────────────────────────────────


def test_valid_deterministic_manifest_passes() -> None:
    validate_manifest(_det_manifest())


def test_valid_llm_manifest_passes() -> None:
    validate_manifest(_llm_manifest())


def test_example_fixture_passes() -> None:
    """The shipped Pulse v1 reference manifest must validate."""
    manifest = load_manifest(_EXAMPLE_MANIFEST)
    assert manifest["system_name"] == "pulse"
    assert manifest["track"] == "deterministic"


# ── Missing required fields ──────────────────────────────────────────────────


def test_missing_top_level_field_rejected() -> None:
    bad = _det_manifest()
    del bad["track"]
    with pytest.raises(SubmissionManifestError, match="missing required"):
        validate_manifest(bad)


def test_missing_contact_field_rejected() -> None:
    bad = _det_manifest()
    del bad["contact"]["email"]
    with pytest.raises(SubmissionManifestError, match="contact.email"):
        validate_manifest(bad)


# ── Track validation ─────────────────────────────────────────────────────────


def test_unknown_track_rejected() -> None:
    bad = _det_manifest()
    bad["track"] = "hybrid"
    with pytest.raises(SubmissionManifestError, match="track must be one of"):
        validate_manifest(bad)


def test_llm_track_missing_extra_fields_rejected() -> None:
    bad = _det_manifest()
    bad["track"] = "llm_augmented"
    with pytest.raises(SubmissionManifestError, match="llm_augmented track requires"):
        validate_manifest(bad)


def test_deterministic_track_does_not_require_llm_fields() -> None:
    """Deterministic track passes without LLM fields — confirms the gate is track-conditional."""
    m = _det_manifest()
    # Just to be sure no LLM fields creep in:
    assert "llm_provider" not in m
    validate_manifest(m)


def test_llm_track_bad_cost_rejected() -> None:
    bad = _llm_manifest()
    bad["cost_per_investigation_usd"] = -1
    with pytest.raises(SubmissionManifestError, match="cost_per_investigation_usd"):
        validate_manifest(bad)


def test_llm_track_bool_cost_rejected() -> None:
    """bool is int subclass — must be rejected for the numeric cost field."""
    bad = _llm_manifest()
    bad["cost_per_investigation_usd"] = True
    with pytest.raises(SubmissionManifestError, match="cost_per_investigation_usd"):
        validate_manifest(bad)


def test_llm_track_string_latency_rejected() -> None:
    bad = _llm_manifest()
    bad["latency_per_investigation_ms_median"] = "1200"
    with pytest.raises(SubmissionManifestError, match="latency"):
        validate_manifest(bad)


# ── Semver validation ────────────────────────────────────────────────────────


def test_non_semver_system_version_rejected() -> None:
    bad = _det_manifest()
    bad["system_version"] = "v1"
    with pytest.raises(SubmissionManifestError, match="system_version"):
        validate_manifest(bad)


def test_non_semver_benchmark_version_rejected() -> None:
    bad = _det_manifest()
    bad["benchmark_version"] = "0.1"
    with pytest.raises(SubmissionManifestError, match="benchmark_version"):
        validate_manifest(bad)


def test_non_semver_pipeline_version_rejected() -> None:
    bad = _det_manifest()
    bad["pipeline_versions"]["analyse"] = "v0.2"
    with pytest.raises(SubmissionManifestError, match="pipeline_versions"):
        validate_manifest(bad)


def test_empty_pipeline_versions_rejected() -> None:
    bad = _det_manifest()
    bad["pipeline_versions"] = {}
    with pytest.raises(SubmissionManifestError, match="non-empty"):
        validate_manifest(bad)


# ── Real-set reporting ───────────────────────────────────────────────────────


def test_real_set_status_unavailable_does_not_require_numbers() -> None:
    m = _det_manifest()
    m["real_set_reporting"] = {"status": "unavailable"}
    validate_manifest(m)


def test_real_set_status_reported_requires_accuracy() -> None:
    bad = _det_manifest()
    bad["real_set_reporting"] = {"status": "reported", "synthetic_real_gap": 0.05}
    with pytest.raises(SubmissionManifestError, match="real_set_accuracy"):
        validate_manifest(bad)


def test_real_set_status_reported_requires_gap() -> None:
    bad = _det_manifest()
    bad["real_set_reporting"] = {"status": "reported", "real_set_accuracy": 0.85}
    with pytest.raises(SubmissionManifestError, match="synthetic_real_gap"):
        validate_manifest(bad)


def test_real_set_status_reported_complete_passes() -> None:
    good = _det_manifest()
    good["real_set_reporting"] = {
        "status": "reported",
        "real_set_accuracy": 0.85,
        "synthetic_real_gap": 0.07,
    }
    validate_manifest(good)


def test_real_set_unknown_status_rejected() -> None:
    bad = _det_manifest()
    bad["real_set_reporting"] = {"status": "in_progress"}
    with pytest.raises(SubmissionManifestError, match="real_set_reporting.status"):
        validate_manifest(bad)


# ── Runtime summary length cap ───────────────────────────────────────────────


def test_runtime_summary_over_cap_rejected() -> None:
    bad = _det_manifest()
    bad["runtime_architecture_summary"] = "x" * 2001
    with pytest.raises(SubmissionManifestError, match="exceeds"):
        validate_manifest(bad)


def test_empty_runtime_summary_rejected() -> None:
    bad = _det_manifest()
    bad["runtime_architecture_summary"] = "   "
    with pytest.raises(SubmissionManifestError, match="runtime_architecture_summary"):
        validate_manifest(bad)


# ── Non-mutation ─────────────────────────────────────────────────────────────


def test_validate_does_not_mutate_input() -> None:
    m = _det_manifest()
    snapshot = copy.deepcopy(m)
    validate_manifest(m)
    assert m == snapshot
