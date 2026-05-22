# Multi-path convergence — design

**Filed under PULSE-89.**

## What "convergence" means in Pulse

For low-stakes investigations a single analytic path is fine: run one test,
report the result, stamp lineage, move on.

For high-stakes investigations — regulatory escalation, vulnerability
disparity claims, public CHRONICLE-candidate entries — Pulse requires
**multi-path convergence**: the same conclusion must hold across
independently-derived methods. The investigation's `convergence_required: true`
flag triggers this rule.

## The failure mode this guards against

Three statistical methods can converge on the same answer while sharing the
same hidden cohort bias. If `chi-squared`, `Fisher's exact`, and `propensity-score
matching` all agree that friction is concentrated on screen X, that
convergence is not load-bearing if all three are blind to the fact that
their cohort sampling under-represents the over-65 vulnerable segment by
40%. The convergent answer would be biased even though every method
"agreed."

This is Krishna Gade's panel point (2026-05-17 ML-Ops critique). The fix is
not "more statistical methods." The fix is "a method that exercises a
different axis of analysis."

## The rule

For any investigation with `convergence_required: true`:

> The convergence panel MUST include **at least one** fairness-aware method
> alongside at least one statistical-power method.

The decision pack's `fairness_methods_required: true` field is the
operational gate — packs used in regulatory or vulnerability-disparity
contexts must set it true. The engine refuses to mark an investigation
convergent if `fairness_methods_required: true` AND no fairness-aware
method ran.

## The methods

See `methods.yaml` for the authoritative registry. Summary:

### Statistical power (catches "is the effect real?")

- **chi_squared** — k×k contingency on cohort × outcome.
- **fishers_exact** — preferred when expected cell frequency < 5.
- **propensity_score_matching** — synthetic counterfactual matching for
  observational causal claims.

### Fairness-aware (catches "is the effect equal across cohorts?")

- **demographic_parity** — `P(outcome | A) == P(outcome | B)`. Disparate
  impact detection.
- **equalised_odds** — TPR + FPR equal across cohorts. Conditions on
  ground truth.
- **calibration_by_cohort** — predicted-vs-actual rate equal across
  cohorts at each predicted-probability bucket. Catches "agrees on average,
  diverges at extremes."

## Per-question-class examples

Per ticket acceptance criteria: at least one fairness-aware method per
question class. From `methods.yaml`:

| Question class | Example fairness-aware method |
|---|---|
| scope | demographic_parity |
| time | calibration_by_cohort |
| cause | equalised_odds |
| verbatim | demographic_parity |
| comparison | demographic_parity |
| persistence | calibration_by_cohort |
| action | equalised_odds |

These are *minimum-viable examples* — not the only choice for any class.
Investigators can pick a different fairness-aware method from the registry
if the question shape suggests it. The minimum bar is "at least one
fairness-aware method that applies to this class."

## What's NOT in v1

- The actual statistical kernels (numerical implementations live in the
  analytics ticket, not here).
- Auto-selection logic (the v1 engine doesn't pick methods; the decision
  pack does, and the validator just enforces the floor).
- LLM-based fairness reasoning (forbidden by the non-LLM lock; if it ever
  lands it's a separate ship per the synthesis design).

## Why not check for fairness in every investigation

Cost and noise. Fairness-aware methods need cohort labels, which are only
populated on the subset of subjects where the bank has consented attributes.
Running them by default on every low-stakes investigation produces a lot of
null results and trains operators to ignore the signal. Gating on
`convergence_required: true` keeps the signal load-bearing.
