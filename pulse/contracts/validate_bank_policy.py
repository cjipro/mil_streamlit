"""Per-deployment bank policy validator.

The engine calls validate_bank_policy(cfg) at startup before any decision
pack runs. Rejection here means the engine does not start — silent
fallbacks would let a misconfigured bank operate without committing to a
stance, which is exactly the failure mode this file exists to prevent.

The shipped pulse/contracts/bank_policy.yaml is a PLACEHOLDER template.
It intentionally fails strict validation (its scalar slots carry `<TBD>`
markers) so that any deployment lifting it verbatim cannot start the
engine. A test asserts this failure mode to keep the template honest.

Filed under PULSE-102.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class BankPolicyError(ValueError):
    """Raised when bank_policy.yaml does not conform to the schema or
    carries unresolved placeholder values."""


_PLACEHOLDER_PREFIX = "<TBD"

_KNOWN_REGULATORY_TAXONOMIES = {
    "fca_consumer_duty_2.0",
}

_REQUIRED_TOP_LEVEL = {
    "version",
    "deployment_id",
    "escalation_thresholds",
    "policy_areas",
    "vulnerable_cohort_extensions",
}

_REQUIRED_THRESHOLDS = {
    "affected_customers_7d_window",
    "vulnerable_cohort_overrep_floor",
}


def load_bank_policy(path: Path | str) -> dict[str, Any]:
    """Load and strictly validate a bank policy YAML. Returns the parsed
    dict on success. Raises BankPolicyError on any violation."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    validate_bank_policy(cfg)
    return cfg


def validate_bank_policy(cfg: Any) -> None:
    """Strictly validate a parsed bank_policy dict. Raises BankPolicyError
    on any missing field, type mismatch, or unresolved `<TBD>` placeholder."""
    if not isinstance(cfg, dict):
        raise BankPolicyError(
            f"bank_policy must be a mapping, got {type(cfg).__name__}"
        )

    missing = _REQUIRED_TOP_LEVEL - set(cfg.keys())
    if missing:
        raise BankPolicyError(f"missing required fields: {sorted(missing)}")

    _validate_version(cfg["version"])
    _validate_deployment_id(cfg["deployment_id"])
    _validate_escalation_thresholds(cfg["escalation_thresholds"])
    _validate_policy_areas(cfg["policy_areas"])
    _validate_vulnerable_cohort_extensions(cfg["vulnerable_cohort_extensions"])
    # arpu_per_journey is optional (introduced in v0.2 commercial-estimate
    # framework — PULSE-107). Older deployments without the block stay valid;
    # the Value methodology's sized lift surfaces as None on every pack.
    if "arpu_per_journey" in cfg:
        _validate_arpu_per_journey(cfg["arpu_per_journey"])


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_PLACEHOLDER_PREFIX)


def _validate_version(version: Any) -> None:
    if not isinstance(version, str) or not version:
        raise BankPolicyError(
            f"version must be a non-empty string, got {version!r}"
        )
    if _is_placeholder(version):
        raise BankPolicyError("version is an unresolved placeholder")


def _validate_deployment_id(deployment_id: Any) -> None:
    if not isinstance(deployment_id, str) or not deployment_id:
        raise BankPolicyError(
            f"deployment_id must be a non-empty string, got {deployment_id!r}"
        )
    if _is_placeholder(deployment_id):
        raise BankPolicyError(
            "deployment_id is an unresolved placeholder — set on deployment "
            "(opaque token, never the bank's name)"
        )


def _validate_escalation_thresholds(thresholds: Any) -> None:
    if not isinstance(thresholds, dict):
        raise BankPolicyError(
            f"escalation_thresholds must be a mapping, got {type(thresholds).__name__}"
        )
    missing = _REQUIRED_THRESHOLDS - set(thresholds.keys())
    if missing:
        raise BankPolicyError(
            f"escalation_thresholds missing required keys: {sorted(missing)}"
        )

    affected = thresholds["affected_customers_7d_window"]
    if _is_placeholder(affected):
        raise BankPolicyError(
            "escalation_thresholds.affected_customers_7d_window is an "
            "unresolved placeholder — the bank must commit to a number"
        )
    if not isinstance(affected, int) or isinstance(affected, bool) or affected < 0:
        raise BankPolicyError(
            "escalation_thresholds.affected_customers_7d_window must be a "
            f"non-negative integer, got {affected!r}"
        )

    overrep = thresholds["vulnerable_cohort_overrep_floor"]
    if _is_placeholder(overrep):
        raise BankPolicyError(
            "escalation_thresholds.vulnerable_cohort_overrep_floor is an "
            "unresolved placeholder — the bank must commit to a ratio"
        )
    if isinstance(overrep, bool) or not isinstance(overrep, (int, float)):
        raise BankPolicyError(
            "escalation_thresholds.vulnerable_cohort_overrep_floor must be a "
            f"number, got {overrep!r}"
        )
    if overrep < 1.0:
        raise BankPolicyError(
            "escalation_thresholds.vulnerable_cohort_overrep_floor must be "
            f">= 1.0 (a ratio below 1.0 means the cohort is under-represented, "
            f"not over-represented), got {overrep!r}"
        )


def _validate_policy_areas(policy_areas: Any) -> None:
    if not isinstance(policy_areas, list):
        raise BankPolicyError(
            f"policy_areas must be a list, got {type(policy_areas).__name__}"
        )
    for i, area in enumerate(policy_areas):
        if not isinstance(area, dict):
            raise BankPolicyError(f"policy_areas[{i}] must be a mapping")
        for required in ("internal_name", "regulatory_taxonomy", "regulatory_section"):
            if required not in area:
                raise BankPolicyError(f"policy_areas[{i}] missing '{required}'")
            value = area[required]
            if not isinstance(value, str) or not value:
                raise BankPolicyError(
                    f"policy_areas[{i}].{required} must be a non-empty string"
                )
            if _is_placeholder(value):
                raise BankPolicyError(
                    f"policy_areas[{i}].{required} is an unresolved placeholder"
                )
        if area["regulatory_taxonomy"] not in _KNOWN_REGULATORY_TAXONOMIES:
            raise BankPolicyError(
                f"policy_areas[{i}].regulatory_taxonomy must be one of "
                f"{sorted(_KNOWN_REGULATORY_TAXONOMIES)}, got "
                f"{area['regulatory_taxonomy']!r}"
            )


def _validate_arpu_per_journey(arpu: Any) -> None:
    if not isinstance(arpu, dict):
        raise BankPolicyError(
            f"arpu_per_journey must be a mapping, got {type(arpu).__name__}"
        )
    for journey, value in arpu.items():
        if not isinstance(journey, str) or not journey:
            raise BankPolicyError(
                f"arpu_per_journey keys must be non-empty strings, got {journey!r}"
            )
        if _is_placeholder(value):
            raise BankPolicyError(
                f"arpu_per_journey[{journey!r}] is an unresolved placeholder"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BankPolicyError(
                f"arpu_per_journey[{journey!r}] must be a non-negative number, "
                f"got {value!r}"
            )
        if value < 0:
            raise BankPolicyError(
                f"arpu_per_journey[{journey!r}] must be non-negative, got {value!r}"
            )


def _validate_vulnerable_cohort_extensions(extensions: Any) -> None:
    if not isinstance(extensions, list):
        raise BankPolicyError(
            "vulnerable_cohort_extensions must be a list, got "
            f"{type(extensions).__name__}"
        )
    seen_ids: set[str] = set()
    for i, ext in enumerate(extensions):
        if not isinstance(ext, dict):
            raise BankPolicyError(
                f"vulnerable_cohort_extensions[{i}] must be a mapping"
            )
        for required in ("cohort_id", "description", "rationale"):
            if required not in ext:
                raise BankPolicyError(
                    f"vulnerable_cohort_extensions[{i}] missing '{required}'"
                )
            value = ext[required]
            if not isinstance(value, str) or not value:
                raise BankPolicyError(
                    f"vulnerable_cohort_extensions[{i}].{required} must be a "
                    "non-empty string"
                )
            if _is_placeholder(value):
                raise BankPolicyError(
                    f"vulnerable_cohort_extensions[{i}].{required} is an "
                    "unresolved placeholder"
                )
        cohort_id = ext["cohort_id"]
        if cohort_id in seen_ids:
            raise BankPolicyError(
                f"vulnerable_cohort_extensions: duplicate cohort_id {cohort_id!r}"
            )
        seen_ids.add(cohort_id)
