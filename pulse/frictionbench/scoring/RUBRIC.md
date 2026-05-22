# FrictionBench v0.1 — scoring rubric (worked examples)

**Filed under PULSE-88.** Machine-readable rubric: [`rubric.yaml`](rubric.yaml).
Reference scorer: [`score.py`](score.py).

## Per-detection scoring

Each detection is scored on 6 axes. 5 contribute to the aggregate (equal-weighted
at v0.1). Time-to-detect is reported separately and ranked, not point-scored.

| Axis | Method | Range | Aggregate weight |
|---|---|---|---|
| Screen identification | exact / same-journey-wrong-step / other | 0.0 / 0.5 / 1.0 | 0.2 |
| Signature classification | exact / same-family / other | 0.0 / 0.5 / 1.0 | 0.2 |
| Cohort identification | multi-label F1 | [0.0, 1.0] | 0.2 |
| Cause identification | exact / plausible-component / plausible-wrong / implausible | 0.0 / 0.2 / 0.5 / 1.0 | 0.2 |
| Confidence calibration | 1 − Brier score | [0.0, 1.0] | 0.2 |
| Time-to-detect (seconds) | rank | rank-ordered | — (separate column) |

**Per-detection aggregate** = weighted mean of the 5 contributing axes.

## Worked examples

### Example 1 — perfect detection

Ground truth (cell 1, `loans.apply.step3` × `dwell_after_error`):
```yaml
screen_id: loans.apply.step3
signature_id: dwell_after_error
should_fire: true
root_cause: template
cohort_tags: [premier, over_50]
confidence_target: 0.85
```

Detector output:
```yaml
screen_id: loans.apply.step3
signature_id: dwell_after_error
cohort_tags: [premier, over_50]
root_cause: template
confidence: 0.85
time_to_detect_seconds: 4.2
```

Scoring:

| Axis | Reasoning | Score |
|---|---|---|
| screen | exact match | 1.0 |
| signature | exact match | 1.0 |
| cohort | F1 of `{premier, over_50}` vs `{premier, over_50}` | 1.0 |
| cause | exact `template` | 1.0 |
| calibration | confidence=0.85, outcome=1, Brier=(0.85-1)²=0.0225, score=1-0.0225 | 0.9775 |

**Aggregate = (1.0 + 1.0 + 1.0 + 1.0 + 0.9775) / 5 = 0.9955.**

### Example 2 — wrong screen but same journey

Same ground truth as Example 1. Detector reported `loans.apply.step2` instead
of `step3` (both belong to journey `loans`).

| Axis | Reasoning | Score |
|---|---|---|
| screen | same journey, wrong step | 0.5 |
| signature | exact match | 1.0 |
| cohort | F1 perfect | 1.0 |
| cause | exact | 1.0 |
| calibration | 1−Brier as Example 1 | 0.9775 |

**Aggregate = (0.5 + 1.0 + 1.0 + 1.0 + 0.9775) / 5 = 0.8955.**

### Example 3 — cell 10 negative correctly NOT fired

Ground truth (cell 10, `investments.premier.portfolio.overview` × `dwell_after_error`):
```yaml
screen_id: investments.premier.portfolio.overview
signature_id: dwell_after_error
should_fire: false  # long dwell = interest, not friction
root_cause: none
cohort_tags: []
confidence_target: 0.05
```

Detector output:
```yaml
signature_id: none  # detector correctly abstained
confidence: 0.05
```

Scoring:

| Axis | Reasoning | Score |
|---|---|---|
| screen | n/a — detector didn't claim a screen (set to ground-truth screen for the math) | 1.0 |
| signature | truth is `none`, detector is `none` → correct abstention | 1.0 |
| cohort | both empty → perfect agreement | 1.0 |
| cause | truth is `none`, detector is `none` → correct abstention | 1.0 |
| calibration | confidence=0.05, outcome=0, Brier=(0.05-0)²=0.0025, score=0.9975 | 0.9975 |

**Aggregate = (1.0 + 1.0 + 1.0 + 1.0 + 0.9975) / 5 = 0.9995.**

This is the critical case: a detector that confidently fires on cell 10 is
mis-classifying interest as friction, and it loses points on signature
(0), cause (0), and calibration (Brier=(0.85-0)²=0.7225 → 0.2775).

### Example 4 — false positive on negative-screen session

Negative-screen session (one of the 754):
```yaml
cell_id: negative_screens
screen_id: dashboard.home
signature_id: none
should_fire: false
```

Detector erroneously emits a detection. This detection does NOT score per
the per-cell rubric (it has no target cell). Instead it counts toward the
**false-positive penalty**, which applies after cell aggregation:

```
final_score = max(0, macro_average_across_cells - 0.05 * false_positive_count)
```

10 false positives on the 754-session pool subtracts 0.5 from the macro
score. 20+ false positives drives the final score to the floor (0.0).

## Aggregation chain

```
per-detection score
   │
   ▼
mean across cell's 1000 detections
   │
   ▼
macro-average across 12 cells
   │
   ▼
subtract 0.05 × false_positive_count (floored at 0)
   │
   ▼
FINAL FRICTIONBENCH SCORE
```

## Why equal weights at v0.1

Choosing axis weights before seeing submissions is guessing. Equal weights
are the honest starting point. v0.2 may reweight once we see which axes
discriminate submissions and which axes everyone aces.

## Why time-to-detect is ranked not point-scored

Seconds don't have a natural ceiling. Picking a TTD-to-score curve before
seeing the distribution would bake in arbitrary winners. v0.1 publishes the
TTD column alongside the score column on the leaderboard; v0.2 may decide
whether a transformed TTD enters the aggregate based on what the data
actually looks like.

## False-positive penalty

A perfect-on-12-cells detector that also fires on 10 negative-screen
sessions loses 0.5 from its score. The penalty has to be heavy: detection
systems that "find friction everywhere" are useless in practice, and v1's
explicit success criterion is detect-on-4-targets / zero-fp-on-754 (CLAUDE.md
Pulse Design Direction lock).
