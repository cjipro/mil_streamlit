"""Pulse Risk methodology v0 — scoring function.

Pure function. Same inputs always produce the same Risk score; the
methodology_version is pinned in every output for audit. Per the ticket's
canvas-as-discipline lock, Risk is a COMPUTED canvas slot — packs declare
the friction signature shape; the engine computes the tier.

Inputs:
- friction signature shape (signature_id, journey_category, screen_class, severity)
- detected impact metrics (affected_customers_7d, vulnerable_cohort_overrep_ratio)
- per-deployment bank_policy.yaml (escalation thresholds)
- regulatory_taxonomy.yaml (loaded from this package; constant)
- Chronicle library (optional — soft dependency; absent library degrades to
  base tier without precedent-match contribution)

Filed under PULSE-99.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pulse.risk.chronicle import ChronicleMatch, match_signature

_RUBRIC_PATH = Path(__file__).parent / "rubric.yaml"
_TAXONOMY_PATH = Path(__file__).parent / "regulatory_taxonomy.yaml"


@dataclass(frozen=True)
class RiskScore:
    """Computed Risk tier + audit footprint.

    `tier` is one of the rubric's closed enum (NOMINAL / WATCH / ESCALATE /
    REGULATORY-FLAG). `numeric_tier` is the underlying integer (0..3) used
    for clamping; useful for downstream sorting.

    `adjustments_applied` lists the rubric's adjustment keys that fired.
    `methodology_version` and `inputs_hash` together let any consumer
    reproduce or audit the score later."""

    tier: str
    numeric_tier: int
    base_tier: int
    adjustments_applied: tuple[str, ...]
    regulatory_matches: tuple[str, ...]
    chronicle_matches: tuple[str, ...]
    methodology_version: str
    inputs_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "numeric_tier": self.numeric_tier,
            "base_tier": self.base_tier,
            "adjustments_applied": list(self.adjustments_applied),
            "regulatory_matches": list(self.regulatory_matches),
            "chronicle_matches": list(self.chronicle_matches),
            "methodology_version": self.methodology_version,
            "inputs_hash": self.inputs_hash,
        }


@dataclass(frozen=True)
class FrictionShape:
    """The friction signature coordinates Risk scores against."""

    signature_id: str
    journey_category: str
    screen_class: str
    severity: str  # P0 / P1 / P2


@dataclass(frozen=True)
class ImpactMetrics:
    """Detected impact magnitudes the engine measured for this signature."""

    affected_customers_7d: int
    vulnerable_cohort_overrep_ratio: float


@functools.lru_cache(maxsize=1)
def load_rubric() -> dict[str, Any]:
    with _RUBRIC_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=1)
def load_taxonomy() -> dict[str, Any]:
    with _TAXONOMY_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def score_risk(
    *,
    shape: FrictionShape,
    impact: ImpactMetrics,
    bank_policy: dict[str, Any],
    chronicle_library: list[dict[str, Any]] | None = None,
) -> RiskScore:
    """Compute Risk tier. Pure function — same inputs → same RiskScore."""
    rubric = load_rubric()
    taxonomy = load_taxonomy()

    base_tier = _base_tier_from_severity(shape.severity, rubric)
    adjustments_applied: list[str] = []

    regulatory_matches = _match_regulatory(shape, taxonomy)
    if regulatory_matches:
        adjustments_applied.append("regulatory_match")

    if _crosses_affected_customers_threshold(impact, bank_policy):
        adjustments_applied.append("affected_customers_threshold")

    if _crosses_vulnerable_cohort_overrep(impact, bank_policy):
        adjustments_applied.append("vulnerable_cohort_overrep")

    chronicle_matches_ids: tuple[str, ...] = ()
    if chronicle_library:
        matches = match_signature(
            chronicle_library,
            signature_id=shape.signature_id,
            screen_class=shape.screen_class,
            severity=shape.severity,
            # Risk methodology consumes ONLY verified Chronicle entries —
            # pending-review entries are excluded. The matcher already
            # defaults to verified-only; pass include_pending=False
            # explicitly for documentation.
            include_pending=False,
        )
        if matches:
            adjustments_applied.append("chronicle_precedent_match")
            chronicle_matches_ids = tuple(m.chronicle_id for m in matches)

    numeric_tier = _apply_adjustments(base_tier, adjustments_applied, rubric)
    tier_word = rubric["tier_words"][numeric_tier]

    inputs_hash = _hash_inputs(shape, impact, bank_policy, chronicle_matches_ids)

    return RiskScore(
        tier=tier_word,
        numeric_tier=numeric_tier,
        base_tier=base_tier,
        adjustments_applied=tuple(adjustments_applied),
        regulatory_matches=tuple(regulatory_matches),
        chronicle_matches=chronicle_matches_ids,
        methodology_version=str(rubric["methodology_version"]),
        inputs_hash=inputs_hash,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _base_tier_from_severity(severity: str, rubric: dict[str, Any]) -> int:
    table = rubric["base_tier_by_severity"]
    if severity not in table:
        raise ValueError(
            f"severity must be one of {sorted(table)}, got {severity!r}"
        )
    return int(table[severity])


def _match_regulatory(shape: FrictionShape, taxonomy: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for entry in taxonomy["taxonomies"]:
        applies = entry["applies_to"]
        if (
            shape.journey_category in applies["journey_categories"]
            and shape.screen_class in applies["screen_classes"]
        ):
            codes.append(entry["taxonomy_code"])
    return codes


def _crosses_affected_customers_threshold(
    impact: ImpactMetrics, bank_policy: dict[str, Any]
) -> bool:
    threshold = bank_policy["escalation_thresholds"]["affected_customers_7d_window"]
    return impact.affected_customers_7d >= threshold


def _crosses_vulnerable_cohort_overrep(
    impact: ImpactMetrics, bank_policy: dict[str, Any]
) -> bool:
    floor = bank_policy["escalation_thresholds"]["vulnerable_cohort_overrep_floor"]
    return impact.vulnerable_cohort_overrep_ratio >= floor


def _apply_adjustments(
    base_tier: int, adjustments_applied: list[str], rubric: dict[str, Any]
) -> int:
    total = base_tier
    for key in adjustments_applied:
        total += int(rubric["adjustments"][key]["delta"])
    return min(int(rubric["max_tier"]), total)


def _hash_inputs(
    shape: FrictionShape,
    impact: ImpactMetrics,
    bank_policy: dict[str, Any],
    chronicle_matches_ids: tuple[str, ...],
) -> str:
    payload = {
        "shape": {
            "signature_id": shape.signature_id,
            "journey_category": shape.journey_category,
            "screen_class": shape.screen_class,
            "severity": shape.severity,
        },
        "impact": {
            "affected_customers_7d": impact.affected_customers_7d,
            "vulnerable_cohort_overrep_ratio": impact.vulnerable_cohort_overrep_ratio,
        },
        # Hash only the deployment-affecting fields of bank_policy, so a
        # cosmetic edit to (say) policy_areas doesn't bust the hash.
        "bank_policy_thresholds": bank_policy.get("escalation_thresholds", {}),
        "bank_policy_deployment_id": bank_policy.get("deployment_id"),
        "chronicle_matches": list(chronicle_matches_ids),
    }
    serialised = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()
