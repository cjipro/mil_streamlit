"""
FrictionBench synthetic-to-real transfer evaluation — PULSE-88 / PULSE-143.

Implements the methodology specified in TRANSFER_EVALUATION.md:

  • signed synthetic_real_gap + leaderboard flag (well_transferred / mild_overfit
    / synthetic_overfitted / severe_overfit)
  • TOST (two one-sided tests) equivalence at epsilon=0.05, alpha=0.05, the
    `equivalent_within_5pp` badge

PULSE-143 scope: the STATISTICS are fully implemented and tested here. The only
missing piece is the real-labelled corpus — `real_example_scores` is empty at
v0.1 (contract-gated on the work-machine side). `evaluate_transfer` returns
status="unavailable" until that corpus is supplied; once it lands, the same
functions score it with zero code change. The corpus is the gap, not the math.

Stats: uses scipy.stats.t when available (exact small-sample), else falls back
to a normal (z) approximation — valid at the documented N>=50 threshold and
keeping the module runnable without scipy (mirrors the pure-stdlib instinct in
pulse/convergence/fairness.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Any

# Per TRANSFER_EVALUATION.md
EPSILON = 0.05          # equivalence margin (5 percentage points)
ALPHA = 0.05            # TOST significance level
MIN_N = 50              # real-set size at/after which TOST is reported


# --------------------------------------------------------------------------
# Gap + flag (TRANSFER_EVALUATION.md "Gap thresholds")
# --------------------------------------------------------------------------

def classify_gap(gap: float) -> str:
    """Map a signed synthetic-real gap to its leaderboard flag.

    Flags key off the MAGNITUDE of the gap (a large negative gap — real far
    above synthetic — is still notable), per the spec table."""
    g = abs(gap)
    if g <= 0.05:
        return "well_transferred"
    if g <= 0.15:
        return "mild_overfit"
    if g <= 0.30:
        return "synthetic_overfitted"
    return "severe_overfit"


def compute_gap(synthetic_score: float, real_score: float) -> dict[str, Any]:
    """Signed gap = synthetic − real (positive = the typical overfit pattern)."""
    gap = synthetic_score - real_score
    return {
        "synthetic_score": round(synthetic_score, 4),
        "real_score": round(real_score, 4),
        "synthetic_real_gap": round(gap, 4),
        "flag": classify_gap(gap),
    }


# --------------------------------------------------------------------------
# t-distribution cdf / quantile — scipy if present, else normal approximation
# --------------------------------------------------------------------------

def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _t_cdf(t: float, df: float) -> tuple[float, str]:
    """Return (P(T<=t), method). Uses scipy when importable; else normal approx."""
    try:
        from scipy import stats  # approved (APPROVED_LIBRARIES.md)
        return float(stats.t.cdf(t, df)), "student_t"
    except Exception:
        return _norm_cdf(t), "normal_approx"


def _t_quantile(p: float, df: float) -> float:
    """Inverse t-CDF. scipy when present; else bisection over the normal approx."""
    try:
        from scipy import stats
        return float(stats.t.ppf(p, df))
    except Exception:
        pass
    lo, hi = -100.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        c, _m = _t_cdf(mid, df)
        if c < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------
# TOST equivalence
# --------------------------------------------------------------------------

@dataclass
class TostResult:
    status: str                       # "reported" | "unavailable" | "insufficient_n"
    equivalent: bool | None = None    # None when status != "reported"
    p_value: float | None = None      # max(p_lower, p_upper)
    diff: float | None = None         # mean_syn - mean_real
    ci90: tuple[float, float] | None = None   # (1-2*alpha) CI on diff (TOST-consistent)
    n_syn: int = 0
    n_real: int = 0
    epsilon: float = EPSILON
    alpha: float = ALPHA
    meets_min_n: bool = False
    method: str = "student_t"
    badge: str | None = None          # "equivalent_within_5pp" when equivalent
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in (
            "status", "equivalent", "p_value", "diff", "ci90", "n_syn", "n_real",
            "epsilon", "alpha", "meets_min_n", "method", "badge", "reason")}
        for k in ("p_value", "diff"):
            if d[k] is not None:
                d[k] = round(d[k], 5)
        if d["ci90"] is not None:
            d["ci90"] = [round(d["ci90"][0], 5), round(d["ci90"][1], 5)]
        return d


def tost_equivalence(
    synthetic_scores: list[float],
    real_scores: list[float],
    epsilon: float = EPSILON,
    alpha: float = ALPHA,
) -> TostResult:
    """Two one-sided tests for equivalence of two score samples within ±epsilon.

      H0: |mean_syn - mean_real| >= epsilon   (NOT equivalent)
      H1: |mean_syn - mean_real| <  epsilon   (equivalent)

    Two-sample Welch formulation. Equivalent iff BOTH one-sided tests reject H0
    at alpha (i.e. max(p_lower, p_upper) < alpha)."""
    n1, n2 = len(synthetic_scores), len(real_scores)

    if n2 == 0:
        # v0.1 reality: real corpus not yet supplied (contract-gated).
        return TostResult(status="unavailable", n_syn=n1, n_real=0,
                          epsilon=epsilon, alpha=alpha,
                          reason="real-labelled corpus empty — supply real_example_scores to evaluate")
    if n1 < 2 or n2 < 2:
        return TostResult(status="insufficient_n", n_syn=n1, n_real=n2,
                          epsilon=epsilon, alpha=alpha,
                          diff=(mean(synthetic_scores) - mean(real_scores)) if (n1 and n2) else None,
                          reason="need >=2 observations per sample to estimate variance")

    m1, m2 = mean(synthetic_scores), mean(real_scores)
    v1, v2 = stdev(synthetic_scores) ** 2, stdev(real_scores) ** 2
    diff = m1 - m2

    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0.0:
        # Zero variance in both samples: deterministic — equivalence decided
        # purely by whether the point difference is inside the margin.
        equivalent = abs(diff) < epsilon
        return TostResult(
            status="reported", equivalent=equivalent, p_value=0.0 if equivalent else 1.0,
            diff=diff, ci90=(diff, diff), n_syn=n1, n_real=n2, epsilon=epsilon, alpha=alpha,
            meets_min_n=(n2 >= MIN_N), method="degenerate_zero_variance",
            badge="equivalent_within_5pp" if equivalent else None,
            reason="zero within-sample variance — decided on point difference",
        )

    # Welch–Satterthwaite degrees of freedom
    df = (v1 / n1 + v2 / n2) ** 2 / (
        (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    )

    # Lower test  H0: diff <= -eps  ->  reject when diff sufficiently > -eps
    t_lower = (diff + epsilon) / se
    p_lower_cdf, method = _t_cdf(t_lower, df)
    p_lower = 1.0 - p_lower_cdf                      # P(T > t_lower)
    # Upper test  H0: diff >= +eps  ->  reject when diff sufficiently < +eps
    t_upper = (diff - epsilon) / se
    p_upper, _ = _t_cdf(t_upper, df)                 # P(T < t_upper)

    p_tost = max(p_lower, p_upper)
    equivalent = p_tost < alpha

    # TOST-consistent (1 - 2*alpha) CI on the difference
    t_crit = _t_quantile(1.0 - alpha, df)
    half = t_crit * se
    ci = (diff - half, diff + half)

    return TostResult(
        status="reported", equivalent=equivalent, p_value=p_tost, diff=diff, ci90=ci,
        n_syn=n1, n_real=n2, epsilon=epsilon, alpha=alpha,
        meets_min_n=(n2 >= MIN_N), method=method,
        badge="equivalent_within_5pp" if equivalent else None,
        reason=("equivalent within ±%.2f at alpha=%.2f" % (epsilon, alpha)) if equivalent
               else ("not equivalent (p=%.3f >= alpha=%.2f)" % (p_tost, alpha)),
    )


# --------------------------------------------------------------------------
# Top-level report
# --------------------------------------------------------------------------

def evaluate_transfer(
    synthetic_cell_aggregates: list[float],
    real_example_scores: list[float] | None = None,
    epsilon: float = EPSILON,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    """Full transfer report for a submission.

    Args:
      synthetic_cell_aggregates: per-cell aggregate scores over the synthetic
        12-cell set (e.g. [aggregate_cell(scores) for each cell]).
      real_example_scores: per-example aggregate scores over the real-labelled
        corpus. None / [] at v0.1 (contract-gated) -> status "unavailable".

    Returns a dict ready to drop onto a leaderboard row. When the real corpus
    is empty the report is honest about it (status "unavailable") rather than
    fabricating a transfer number — exactly the PULSE-143 gap.
    """
    real_example_scores = real_example_scores or []
    syn_score = mean(synthetic_cell_aggregates) if synthetic_cell_aggregates else 0.0

    if not real_example_scores:
        return {
            "real_set_reporting": {"status": "unavailable"},
            "synthetic_score": round(syn_score, 4),
            "real_score": None,
            "synthetic_real_gap": None,
            "flag": None,
            "tost": tost_equivalence(synthetic_cell_aggregates, [], epsilon, alpha).as_dict(),
            "note": "real-labelled corpus empty at v0.1 (contract-gated). "
                    "Supply real_example_scores to populate gap + TOST.",
        }

    real_score = mean(real_example_scores)
    gap = compute_gap(syn_score, real_score)
    tost = tost_equivalence(synthetic_cell_aggregates, real_example_scores, epsilon, alpha)
    return {
        "real_set_reporting": {"status": "reported"},
        **gap,
        "tost": tost.as_dict(),
    }
