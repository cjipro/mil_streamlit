"""FrictionBench submission manifest validator.

Small standalone validator that submitters can run locally before submitting.
Not the full harness — that's a separate ticket per ticket out-of-scope.

Filed under PULSE-88.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class SubmissionManifestError(ValueError):
    """Raised when a submission manifest does not conform to the schema."""


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
_TRACK_VALUES = {"deterministic", "llm_augmented"}
_REAL_SET_STATUSES = {"reported", "unavailable"}

_REQUIRED_TOP_LEVEL = {
    "system_name",
    "system_version",
    "track",
    "benchmark_version",
    "runtime_architecture_summary",
    "pipeline_versions",
    "license",
    "contact",
    "docker_image",
    "real_set_reporting",
}

_LLM_TRACK_REQUIRED = {
    "llm_provider",
    "llm_model",
    "llm_model_version",
    "cost_per_investigation_usd",
    "latency_per_investigation_ms_median",
    "latency_per_investigation_ms_p95",
}

_RUNTIME_SUMMARY_MAX = 2000


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Load + validate a manifest YAML. Returns the parsed dict on success."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate a submission manifest. Raises SubmissionManifestError on any violation."""
    if not isinstance(manifest, dict):
        raise SubmissionManifestError(
            f"manifest must be a mapping, got {type(manifest).__name__}"
        )

    missing = _REQUIRED_TOP_LEVEL - set(manifest.keys())
    if missing:
        raise SubmissionManifestError(f"missing required fields: {sorted(missing)}")

    if not isinstance(manifest["system_name"], str) or not manifest["system_name"]:
        raise SubmissionManifestError("system_name must be a non-empty string")

    if not _SEMVER_RE.match(manifest.get("system_version", "") or ""):
        raise SubmissionManifestError(
            f"system_version must be semver, got {manifest.get('system_version')!r}"
        )

    track = manifest["track"]
    if track not in _TRACK_VALUES:
        raise SubmissionManifestError(
            f"track must be one of {sorted(_TRACK_VALUES)}, got {track!r}"
        )

    if not _SEMVER_RE.match(manifest.get("benchmark_version", "") or ""):
        raise SubmissionManifestError(
            f"benchmark_version must be semver, got {manifest.get('benchmark_version')!r}"
        )

    summary = manifest["runtime_architecture_summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise SubmissionManifestError("runtime_architecture_summary must be a non-empty string")
    if len(summary) > _RUNTIME_SUMMARY_MAX:
        raise SubmissionManifestError(
            f"runtime_architecture_summary exceeds {_RUNTIME_SUMMARY_MAX} chars "
            f"(got {len(summary)})"
        )

    pipeline_versions = manifest["pipeline_versions"]
    if not isinstance(pipeline_versions, dict) or not pipeline_versions:
        raise SubmissionManifestError(
            "pipeline_versions must be a non-empty mapping of stage -> semver"
        )
    for stage, ver in pipeline_versions.items():
        if not isinstance(stage, str) or not stage:
            raise SubmissionManifestError(
                f"pipeline_versions has non-string stage key: {stage!r}"
            )
        if not isinstance(ver, str) or not _SEMVER_RE.match(ver):
            raise SubmissionManifestError(
                f"pipeline_versions[{stage!r}] must be semver, got {ver!r}"
            )

    if not isinstance(manifest["license"], str) or not manifest["license"]:
        raise SubmissionManifestError("license must be a non-empty SPDX identifier string")

    contact = manifest["contact"]
    if not isinstance(contact, dict):
        raise SubmissionManifestError("contact must be a mapping")
    for field in ("name", "email"):
        if not isinstance(contact.get(field), str) or not contact[field]:
            raise SubmissionManifestError(f"contact.{field} must be a non-empty string")

    docker = manifest["docker_image"]
    if not isinstance(docker, str) or not docker:
        raise SubmissionManifestError("docker_image must be a non-empty registry reference")

    _validate_real_set_reporting(manifest["real_set_reporting"])

    if track == "llm_augmented":
        _validate_llm_track(manifest)


def _validate_real_set_reporting(rsr: Any) -> None:
    if not isinstance(rsr, dict):
        raise SubmissionManifestError("real_set_reporting must be a mapping")
    status = rsr.get("status")
    if status not in _REAL_SET_STATUSES:
        raise SubmissionManifestError(
            f"real_set_reporting.status must be one of {sorted(_REAL_SET_STATUSES)}, "
            f"got {status!r}"
        )
    if status == "reported":
        for required in ("real_set_accuracy", "synthetic_real_gap"):
            if required not in rsr:
                raise SubmissionManifestError(
                    f"real_set_reporting.{required} required when status=reported"
                )
            value = rsr[required]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SubmissionManifestError(
                    f"real_set_reporting.{required} must be numeric, got {value!r}"
                )


def _validate_llm_track(manifest: dict[str, Any]) -> None:
    missing = _LLM_TRACK_REQUIRED - set(manifest.keys())
    if missing:
        raise SubmissionManifestError(
            f"llm_augmented track requires additional fields, missing: {sorted(missing)}"
        )
    for field in ("llm_provider", "llm_model", "llm_model_version"):
        v = manifest[field]
        if not isinstance(v, str) or not v:
            raise SubmissionManifestError(f"{field} must be a non-empty string")
    cost = manifest["cost_per_investigation_usd"]
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        raise SubmissionManifestError(
            f"cost_per_investigation_usd must be a non-negative number, got {cost!r}"
        )
    for latency_field in (
        "latency_per_investigation_ms_median",
        "latency_per_investigation_ms_p95",
    ):
        v = manifest[latency_field]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise SubmissionManifestError(
                f"{latency_field} must be a non-negative integer, got {v!r}"
            )
