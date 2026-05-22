# FrictionBench v0.1 — synthetic-to-real transfer evaluation

**Filed under PULSE-88.** Per ML-Ops panel consensus item 7 (Eugene Yan +
Shreya Shankar critique, 2026-05-17).

## Why this exists

A detector that scores 0.95 on the synthetic 12-cell test set is impressive
only if it scores comparably on real bank telemetry. Systems that memorise
synthetic quirks ("the generator emits exactly 30000ms of dwell when it
wants to mark a friction event") will ace the synthetic and flop on the
real.

**The synthetic-to-real gap is the load-bearing metric.** Either of these
patterns on the leaderboard is informative:

- 0.95 synthetic + 0.90 real → real generalisation; the system is learning
  patterns, not memorising templates
- 0.95 synthetic + 0.40 real → synthetic-overfitted; the score is
  misleading and the leaderboard tags it

## The real-labelled set

A curated set of N ≥ 50 real-bank-derived labelled examples,
anonymised + contract-controlled. Each example carries the same
ground-truth schema as the synthetic set ([`../test_set/ground_truth_schema.yaml`](../test_set/ground_truth_schema.yaml)),
so the same scoring script works against both.

The real set is hosted by the benchmark org and shared with verified
submitters under a use-restricted agreement. It is NOT in the public
bundle — that's the contract constraint.

## v0.1 status: real set is empty

At v0.1 the real-labelled set is empty (contract-gated on the
work-machine side). The methodology ships regardless. Submissions can
declare `real_set_reporting.status: unavailable` in their manifest
without being disqualified.

When the real set lands (estimated v0.1.1 or v0.2), submissions are
automatically re-scored and the synthetic-real gap appears on their
leaderboard row.

## Methodology

For each submission with `real_set_reporting.status: reported`:

```
synthetic_score    = macro_average over 12 cells with FP penalty applied
real_score         = macro_average over real-labelled examples with FP penalty applied
synthetic_real_gap = synthetic_score − real_score
```

The gap is **signed**: positive means synthetic > real (the typical
overfit pattern); negative means real > synthetic (rare; suggests the
synthetic set is harder than real for this system).

## Gap thresholds (informational, not gating)

Per panel consensus, gap thresholds are descriptive flags on the
leaderboard, not pass/fail gates:

| Gap | Flag | Interpretation |
|---|---|---|
| ≤ 0.05 | `well_transferred` | The system generalises. |
| 0.05 – 0.15 | `mild_overfit` | Worth investigating; not disqualifying. |
| 0.15 – 0.30 | `synthetic_overfitted` | Score is misleading; treat with scepticism. |
| > 0.30 | `severe_overfit` | The headline synthetic score should not be cited without the gap. |

A `severe_overfit` flag does not remove the submission from the
leaderboard. It surfaces the gap so readers can weight the synthetic
number appropriately.

## TOST-style equivalence (panel consensus #7)

Once N ≥ 50 examples are in the real set, the leaderboard reports a
**TOST (two one-sided tests) equivalence result** with ε = 0.05:

```
H₀: |synthetic_score − real_score| ≥ 0.05  (NOT equivalent)
H₁: |synthetic_score − real_score| < 0.05  (equivalent within ε)
```

Submissions that pass TOST at α = 0.05 carry an `equivalent_within_5pp`
badge. Submissions that fail or are inconclusive show the gap with a
confidence interval. This is the standard ML-Ops practice for
synthetic-real transfer claims.

## Real-set growth plan

- **v0.1.0** — empty (this version)
- **v0.1.1** — N ≈ 50 (target; first real set)
- **v0.2.0** — N ≈ 200 (expanded set; harder generalisation test)
- **v1.0.0** — N ≈ 1000 (gold-standard set; basis for the year-locked benchmark)

Growth gated on (a) contract-side data access, (b) labelling capacity
on the work-machine side. The benchmark spec ships now; the data
substrate grows as it's available.

## Why this beats "just publish the real numbers"

A leaderboard that publishes only real-set scores would (a) be
non-reproducible (real set is contract-controlled, public can't re-run),
(b) be cumulatively biased (the real set's coverage gaps become the
benchmark's gaps), and (c) be slow to evolve (every new system needs
the contract-controlled access to compete).

The two-score approach (synthetic + real + gap) is reproducible on the
synthetic side, accurate on the real side, and surfaces the gap as the
honest signal of generalisation.
