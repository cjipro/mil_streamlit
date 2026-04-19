"""
taxonomy_loader.py — MIL-32

Single import point for all taxonomy constants.
Reads mil/config/domain_taxonomy.yaml and exposes typed accessors.

All pipeline files must import from here — never hardcode issue types,
customer journeys, or severity gate logic directly.

Usage:
    from mil.config.taxonomy_loader import (
        issue_types, customer_journeys, blocking_issues,
        max_severity_for, journey_map, technical_issues,
        service_issues, exclude_from_rates,
    )

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_TAXONOMY_PATH = Path(__file__).parent / "domain_taxonomy.yaml"

_SEV_ORDER = {"P0": 0, "P1": 1, "P2": 2}


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def issue_types() -> list[str]:
    """All enrichment issue type names (enrichment: true only)."""
    return [e["name"] for e in _load()["issue_types"] if e.get("enrichment", True)]


def all_issue_types() -> list[str]:
    """All issue type names including benchmark-only categories."""
    return [e["name"] for e in _load()["issue_types"]]


def customer_journeys() -> list[str]:
    return list(_load()["customer_journeys"])


def max_severity_for(issue_type: str) -> str:
    """Return max permitted severity class for an issue type. Defaults to P2."""
    for e in _load()["issue_types"]:
        if e["name"] == issue_type:
            return e.get("max_severity", "P2")
    return "P2"


def apply_severity_gate(issue_type: str, severity: str) -> str:
    """
    Cap severity at max_severity_for(issue_type).
    Returns the capped severity string.
    """
    max_sev = max_severity_for(issue_type)
    if _SEV_ORDER.get(severity, 2) < _SEV_ORDER.get(max_sev, 2):
        return max_sev
    return severity


def blocking_issues() -> set[str]:
    """Issue types where P0 severity is permitted (max_severity == P0)."""
    return {e["name"] for e in _load()["issue_types"] if e.get("max_severity") == "P0"}


def technical_issues() -> set[str]:
    """Issue types classified as technical failures."""
    return {e["name"] for e in _load()["issue_types"] if e.get("category") == "technical"}


def service_issues() -> set[str]:
    """Issue types classified as service failures."""
    return {e["name"] for e in _load()["issue_types"] if e.get("category") == "service"}


def journey_map() -> dict[str, str | None]:
    """issue_type → journey_id mapping. None values are unmappable (skipped in inference)."""
    raw = _load().get("journey_map", {})
    return {k: (None if v is None else v) for k, v in raw.items()}


def exclude_from_rates() -> set[str]:
    """Issue types excluded from complaint-rate calculations."""
    return set(_load().get("exclude_from_rates", []))


def reload() -> None:
    """Force reload of domain_taxonomy.yaml (clears lru_cache). Use in tests only."""
    _load.cache_clear()
