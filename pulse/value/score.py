"""Pulse Value methodology v0 — scoring function.

Pure function. Same inputs always produce the same Value score; the
methodology_version is pinned in every output for audit. Per the
canvas-as-discipline lock, Value is a COMPUTED canvas slot — packs
declare the friction signature shape and value-bearing observations;
the engine computes the tier.

Inputs:
- friction signature shape (signature_id, journey_category, screen_class, severity)
- detected value metrics (affected_customers_7d, avg_events_per_affected_user,
  vulnerable_cohort_share, counterfactual_baseline_pct)
- per-deployment bank_policy.yaml (escalation thresholds — shared with Risk
  for cross-axis consistency on the affected-population threshold)

Filed under PULSE-101.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_METHODOLOGY_PATH = Path(__file__).parent / "value_methodology.yaml"


@dataclass(frozen=True)
class ValueScore:
    """Computed Value tier + audit footprint + commercial signal.

    Categorical fields (v0.1):
      `tier` is one of the methodology's closed enum (NOMINAL / WATCH /
      SIGNIFICANT / COMMERCIAL-OPPORTUNITY). `numeric_tier` is the
      underlying integer (0..3); useful for downstream sorting.
      `adjustments_applied` lists which methodology adjustment keys fired.
      `methodology_version` and `inputs_hash` together let any consumer
      reproduce or audit the score later.

    Friction-volume signal (v0.3 — the PRIMARY commercial unit):
      `recoverable_sessions_per_week` / `_per_month` — count of affected
      sessions that would complete if the friction were removed
      (affected_customers_7d × counterfactual_baseline_pct, scaled to the
      window). This is the unit surfaces should LEAD with — it is in the
      bank's own outcome vocabulary and needs no monetisation assumption.
      Always populated (computed from metrics alone, no ARPU needed).

    Cost scaffold (v0.2 — SECONDARY, never primary):
      `estimated_monthly_lift_gbp` — recoverable_sessions_per_month × ARPU.
      A DERIVED cost framing for the friction-volume signal; renderers must
      treat it as a scaffold ("≈ £X/mo at £Y/session"), never as the lead
      stat. None when bank_policy.yaml lacks an ARPU entry for the journey.
      `arpu_per_session_gbp` — the resolved per-session ARPU used, so the
      scaffold can name its own assumption transparently. None when unset.
      `conversion_rate_delta` — counterfactual conversion lift (0..1),
      aliased to ValueMetrics.counterfactual_baseline_pct; always populated.
      `confidence_interval` — reserved; always None until HOL-48 bootstrap.
      `arpu_source` — "bank_policy" when ARPU matched, None when no match."""

    tier: str
    numeric_tier: int
    base_tier: int
    adjustments_applied: tuple[str, ...]
    methodology_version: str
    inputs_hash: str
    recoverable_sessions_per_week: int | None = None
    recoverable_sessions_per_month: int | None = None
    estimated_monthly_lift_gbp: float | None = None
    arpu_per_session_gbp: float | None = None
    conversion_rate_delta: float | None = None
    confidence_interval: tuple[float, float] | None = None
    arpu_source: str | None = None
    recoverable_friction_minutes_per_week: int | None = None
    recoverable_friction_minutes_per_month: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "numeric_tier": self.numeric_tier,
            "base_tier": self.base_tier,
            "adjustments_applied": list(self.adjustments_applied),
            "methodology_version": self.methodology_version,
            "inputs_hash": self.inputs_hash,
            "recoverable_sessions_per_week": self.recoverable_sessions_per_week,
            "recoverable_sessions_per_month": self.recoverable_sessions_per_month,
            "estimated_monthly_lift_gbp": self.estimated_monthly_lift_gbp,
            "arpu_per_session_gbp": self.arpu_per_session_gbp,
            "conversion_rate_delta": self.conversion_rate_delta,
            "confidence_interval": (
                list(self.confidence_interval)
                if self.confidence_interval is not None
                else None
            ),
            "arpu_source": self.arpu_source,
            "recoverable_friction_minutes_per_week": self.recoverable_friction_minutes_per_week,
            "recoverable_friction_minutes_per_month": self.recoverable_friction_minutes_per_month,
        }


@dataclass(frozen=True)
class ValueShape:
    """The friction signature coordinates Value scores against."""

    signature_id: str
    journey_category: str
    screen_class: str
    severity: str  # P0 / P1 / P2


@dataclass(frozen=True)
class ValueMetrics:
    """Detected value-bearing magnitudes the engine measured for this signature.

    Distinct from Risk's ImpactMetrics — Value asks a different question
    (how much would be unlocked by fixing this friction?) so the metrics
    differ even though some are derivable from the same underlying telemetry."""

    affected_customers_7d: int
    avg_events_per_affected_user: float
    vulnerable_cohort_share: float        # 0..1
    counterfactual_baseline_pct: float    # 0..1
    # Mean friction-attributable excess seconds per affected session. Drives the
    # recoverable_friction_minutes signal — value BEYOND recovered completions, for
    # signatures where customers complete despite the friction. Default 0.0.
    mean_friction_seconds_per_affected: float = 0.0


@functools.lru_cache(maxsize=1)
def load_methodology() -> dict[str, Any]:
    with _METHODOLOGY_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def score_value(
    *,
    shape: ValueShape,
    metrics: ValueMetrics,
    bank_policy: dict[str, Any],
) -> ValueScore:
    """Compute Value tier. Pure function — same inputs → same ValueScore."""
    methodology = load_methodology()

    base_tier = _base_tier_from_severity(shape.severity, methodology)
    adjustments_applied: list[str] = []

    if _crosses_affected_population(metrics, bank_policy):
        adjustments_applied.append("large_affected_population")

    if _crosses_frequency_threshold(metrics, methodology):
        adjustments_applied.append("high_frequency_per_user")

    if _crosses_cohort_concentration(metrics, methodology):
        adjustments_applied.append("vulnerable_cohort_concentrated")

    if _crosses_counterfactual_baseline(metrics, methodology):
        adjustments_applied.append("large_counterfactual_baseline")

    numeric_tier = _apply_adjustments(base_tier, adjustments_applied, methodology)
    tier_word = methodology["tier_words"][numeric_tier]

    # Friction-volume signal — the PRIMARY commercial unit. Computed from
    # metrics alone (no ARPU): recoverable sessions are affected sessions
    # that would complete if the friction were removed.
    multiplier = float(
        methodology["commercial_estimate"]["weekly_to_monthly_multiplier"]
    )
    recoverable_week = round(
        metrics.affected_customers_7d * metrics.counterfactual_baseline_pct
    )
    recoverable_month = round(recoverable_week * multiplier)

    # Friction-time signal — value BEYOND recovered completions. For signatures where
    # customers complete despite the friction (dwell-after-error, multi-back-press)
    # recoverable_sessions is ~0, but the excess time the friction costs is real and a
    # fix gives it back. Customer-minutes/week — the bank's own vocabulary, no ARPU.
    friction_min_week = round(
        metrics.affected_customers_7d * metrics.mean_friction_seconds_per_affected / 60.0
    )
    friction_min_month = round(friction_min_week * multiplier)

    # Cost scaffold — SECONDARY. £ derived from the friction-volume × ARPU.
    arpu_used, arpu_source = _resolve_arpu(shape, bank_policy)
    monthly_lift = _compute_monthly_lift(metrics, arpu_used, methodology)

    inputs_hash = _hash_inputs(shape, metrics, bank_policy, arpu_used)

    return ValueScore(
        tier=tier_word,
        numeric_tier=numeric_tier,
        base_tier=base_tier,
        adjustments_applied=tuple(adjustments_applied),
        methodology_version=str(methodology["methodology_version"]),
        inputs_hash=inputs_hash,
        recoverable_sessions_per_week=recoverable_week,
        recoverable_sessions_per_month=recoverable_month,
        estimated_monthly_lift_gbp=monthly_lift,
        arpu_per_session_gbp=arpu_used,
        conversion_rate_delta=metrics.counterfactual_baseline_pct,
        confidence_interval=None,
        arpu_source=arpu_source,
        recoverable_friction_minutes_per_week=friction_min_week,
        recoverable_friction_minutes_per_month=friction_min_month,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _base_tier_from_severity(severity: str, methodology: dict[str, Any]) -> int:
    table = methodology["base_tier_by_severity"]
    if severity not in table:
        raise ValueError(
            f"severity must be one of {sorted(table)}, got {severity!r}"
        )
    return int(table[severity])


def _crosses_affected_population(
    metrics: ValueMetrics, bank_policy: dict[str, Any]
) -> bool:
    threshold = bank_policy["escalation_thresholds"]["affected_customers_7d_window"]
    return metrics.affected_customers_7d >= threshold


def _crosses_frequency_threshold(
    metrics: ValueMetrics, methodology: dict[str, Any]
) -> bool:
    threshold = methodology["adjustments"]["high_frequency_per_user"][
        "threshold_events_per_user"
    ]
    return metrics.avg_events_per_affected_user >= threshold


def _crosses_cohort_concentration(
    metrics: ValueMetrics, methodology: dict[str, Any]
) -> bool:
    threshold = methodology["adjustments"]["vulnerable_cohort_concentrated"][
        "threshold_cohort_share"
    ]
    return metrics.vulnerable_cohort_share >= threshold


def _crosses_counterfactual_baseline(
    metrics: ValueMetrics, methodology: dict[str, Any]
) -> bool:
    threshold = methodology["adjustments"]["large_counterfactual_baseline"][
        "threshold_baseline_pct"
    ]
    return metrics.counterfactual_baseline_pct >= threshold


def _apply_adjustments(
    base_tier: int, adjustments_applied: list[str], methodology: dict[str, Any]
) -> int:
    total = base_tier
    for key in adjustments_applied:
        total += int(methodology["adjustments"][key]["delta"])
    return min(int(methodology["max_tier"]), total)


def _resolve_arpu(
    shape: ValueShape, bank_policy: dict[str, Any]
) -> tuple[float | None, str | None]:
    """Look up ARPU for this shape's journey_category in the deployment's
    bank_policy. Returns (arpu_value, source) or (None, None) when no entry
    matches. Per the v0.2 commercial-estimate framework, missing ARPU is a
    valid state — the categorical tier still computes; the sized lift just
    surfaces as None."""
    arpu_block = bank_policy.get("arpu_per_journey")
    if not isinstance(arpu_block, dict):
        return (None, None)
    value = arpu_block.get(shape.journey_category)
    if value is None or isinstance(value, bool):
        return (None, None)
    if not isinstance(value, (int, float)) or value < 0:
        return (None, None)
    return (float(value), "bank_policy")


def _compute_monthly_lift(
    metrics: ValueMetrics, arpu: float | None, methodology: dict[str, Any]
) -> float | None:
    """v0.2 point estimate: weekly_affected × week→month × baseline_pct × ARPU.
    Returns None when ARPU is unavailable for the journey."""
    if arpu is None:
        return None
    multiplier = float(
        methodology["commercial_estimate"]["weekly_to_monthly_multiplier"]
    )
    return (
        metrics.affected_customers_7d
        * multiplier
        * metrics.counterfactual_baseline_pct
        * arpu
    )


def _hash_inputs(
    shape: ValueShape,
    metrics: ValueMetrics,
    bank_policy: dict[str, Any],
    arpu_used: float | None,
) -> str:
    payload = {
        "shape": {
            "signature_id": shape.signature_id,
            "journey_category": shape.journey_category,
            "screen_class": shape.screen_class,
            "severity": shape.severity,
        },
        "metrics": {
            "affected_customers_7d": metrics.affected_customers_7d,
            "avg_events_per_affected_user": metrics.avg_events_per_affected_user,
            "vulnerable_cohort_share": metrics.vulnerable_cohort_share,
            "counterfactual_baseline_pct": metrics.counterfactual_baseline_pct,
            "mean_friction_seconds_per_affected": metrics.mean_friction_seconds_per_affected,
        },
        # Same partial-hashing posture as Risk: cosmetic policy edits
        # don't bust the audit trail.
        "bank_policy_thresholds": bank_policy.get("escalation_thresholds", {}),
        "bank_policy_deployment_id": bank_policy.get("deployment_id"),
        # The resolved ARPU value (not the full per-journey block) is what
        # actually drove the sized output — hash that so changing an
        # unrelated journey's ARPU doesn't bust this pack's audit trail.
        "arpu_used": arpu_used,
    }
    serialised = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()
