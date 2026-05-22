"""Executable fairness-aware + statistical-power kernels (PULSE-89 convergence).

`methods.yaml` declares the registry + which methods apply per question class;
this module implements the v1 kernels the high-stakes decision path runs:

  - demographic_parity (fairness-aware): disparate-impact ratio of detected
    friction on a protected cohort vs the reference cohort. Observed-data only —
    needs detection + cohort label, both present in production.
  - chi_squared (statistical-power): is the cohort x outcome association real?
    2x2 contingency with Yates continuity correction.

Together they satisfy the multi-path convergence rule (>=1 statistical + >=1
fairness) for investigations flagged high-stakes. Classical + deterministic
(non-LLM lock), pure stdlib (no scipy dependency). Ground-truth-conditioned
methods (equalised_odds / recall disparity) need labels not present in observed
production data — declared in methods.yaml, not run at v1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# 4/5ths (adverse-impact) rule band on the disparity ratio. A protected-cohort
# detection rate >1.25x the reference (or <0.8x) is disparate impact.
_ADVERSE_IMPACT_LOW = 0.8
_ADVERSE_IMPACT_HIGH = 1.25
_CHI2_SIGNIFICANCE = 0.05


@dataclass(frozen=True)
class FairnessResult:
    """Convergence result for one finding: a fairness-aware + a statistical method."""

    assessed: bool
    protected_group: str
    protected_rate: float | None
    reference_rate: float | None
    disparity_ratio: float | None        # protected_rate / reference_rate
    parity_difference: float | None      # protected_rate - reference_rate
    chi2_statistic: float | None
    chi2_p_value: float | None
    statistically_significant: bool
    disparate_impact: bool
    methods: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "assessed": self.assessed,
            "protected_group": self.protected_group,
            "protected_rate": self.protected_rate,
            "reference_rate": self.reference_rate,
            "disparity_ratio": self.disparity_ratio,
            "parity_difference": self.parity_difference,
            "chi2_statistic": self.chi2_statistic,
            "chi2_p_value": self.chi2_p_value,
            "statistically_significant": self.statistically_significant,
            "disparate_impact": self.disparate_impact,
            "methods": list(self.methods),
            "reason": self.reason,
        }


def _not_assessed(protected_group: str, reason: str) -> FairnessResult:
    return FairnessResult(
        assessed=False, protected_group=protected_group, protected_rate=None,
        reference_rate=None, disparity_ratio=None, parity_difference=None,
        chi2_statistic=None, chi2_p_value=None, statistically_significant=False,
        disparate_impact=False, methods=(), reason=reason,
    )


def chi_squared_2x2(a: int, b: int, c: int, d: int) -> tuple[float | None, float | None]:
    """2x2 chi-squared with Yates continuity correction. Table [[a,b],[c,d]].
    Returns (statistic, p_value); (None, None) when a margin is zero.
    p-value is exact for 1 dof: P(X>x) = erfc(sqrt(x/2))."""
    n = a + b + c + d
    r1, r2, c1, c2 = a + b, c + d, a + c, b + d
    if min(r1, r2, c1, c2) == 0 or n == 0:
        return (None, None)
    num = n * (abs(a * d - b * c) - n / 2.0) ** 2
    # Yates correction can drive the numerator term negative for tiny tables; clamp.
    chi2 = max(0.0, num) / (r1 * r2 * c1 * c2)
    p = math.erfc(math.sqrt(chi2 / 2.0))
    return (round(chi2, 4), round(p, 6))


def assess_fairness(
    *,
    protected_fired: int,
    protected_total: int,
    reference_fired: int,
    reference_total: int,
    protected_group: str = "vulnerable_flag",
    min_cohort: int = 5,
) -> FairnessResult:
    """demographic_parity + chi_squared over a protected vs reference cohort.

    Detection rates: P(fired | protected) vs P(fired | reference). disparity_ratio
    = protected_rate / reference_rate. disparate_impact when the ratio leaves the
    4/5ths band. chi_squared tests whether the cohort x outcome association is real."""
    if protected_total < min_cohort or reference_total < min_cohort:
        return _not_assessed(protected_group, "insufficient cohort sample")

    p_rate = protected_fired / protected_total
    r_rate = reference_fired / reference_total
    ratio = round(p_rate / r_rate, 4) if r_rate > 0 else None
    diff = round(p_rate - r_rate, 4)

    chi2, p_value = chi_squared_2x2(
        protected_fired, protected_total - protected_fired,
        reference_fired, reference_total - reference_fired,
    )
    significant = p_value is not None and p_value < _CHI2_SIGNIFICANCE
    disparate = ratio is not None and (ratio < _ADVERSE_IMPACT_LOW or ratio > _ADVERSE_IMPACT_HIGH)

    return FairnessResult(
        assessed=True,
        protected_group=protected_group,
        protected_rate=round(p_rate, 4),
        reference_rate=round(r_rate, 4),
        disparity_ratio=ratio,
        parity_difference=diff,
        chi2_statistic=chi2,
        chi2_p_value=p_value,
        statistically_significant=significant,
        disparate_impact=disparate,
        methods=("demographic_parity", "chi_squared"),
        reason="ok",
    )
