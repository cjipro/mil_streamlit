# Pulse Value — rubric (worked examples)

Machine-readable rubric: [`value_methodology.yaml`](./value_methodology.yaml).
Reference scorer: [`score.py`](./score.py). Methodology paper:
[`VALUE_DESIGN.md`](./VALUE_DESIGN.md).

Filed under [PULSE-101].

## Tier words (closed enum)

| Numeric | Word | Meaning |
|---|---|---|
| 0 | `NOMINAL` | minimal value at stake — no special prioritisation |
| 1 | `WATCH` | moderate signal worth monitoring |
| 2 | `SIGNIFICANT` | material commercial impact |
| 3 | `COMMERCIAL-OPPORTUNITY` | high-value pattern that warrants prioritised investment |

Extending the enum is a methodology-version change. The set is closed by
construction — a test asserts it.

## Worked examples

### Example 1 — P2 NOMINAL (no adjustments)

Low-severity friction, small affected population, low frequency, no
vulnerable-cohort concentration, small counterfactual baseline.

```
shape:   signature_id=lazy_scroll, journey_category=behavioural_noise,
         screen_class=marketing_page, severity=P2
metrics: affected_customers_7d=15, avg_events_per_affected_user=1.1,
         vulnerable_cohort_share=0.05, counterfactual_baseline_pct=0.05
policy:  affected_customers_7d_window=500
```

Base tier: `P2 → 0` (NOMINAL). No adjustments fire.
**Tier: NOMINAL.**

### Example 2 — P1 with high frequency → SIGNIFICANT

A medium-severity friction that customers encounter multiple times per
visit — a fix ends the recurring frustration.

```
shape:   signature_id=multi_back_press, journey_category=context_loss,
         screen_class=account_management, severity=P1
metrics: affected_customers_7d=100, avg_events_per_affected_user=4.2,
         vulnerable_cohort_share=0.1, counterfactual_baseline_pct=0.1
policy:  affected_customers_7d_window=500
```

Base tier: `P1 → 1` (WATCH). `high_frequency_per_user` fires (4.2 ≥ 3).
**Tier: SIGNIFICANT.** (1 + 1 = 2)

### Example 3 — P0 with all four adjustments → COMMERCIAL-OPPORTUNITY

High severity. Large affected population. High per-user frequency.
Vulnerable cohorts disproportionately affected. Large counterfactual.

```
shape:   signature_id=dwell_after_error, journey_category=choke_point,
         screen_class=credit_application, severity=P0
metrics: affected_customers_7d=12500, avg_events_per_affected_user=3.5,
         vulnerable_cohort_share=0.55, counterfactual_baseline_pct=0.40
policy:  affected_customers_7d_window=500
```

Base tier: `P0 → 2` (SIGNIFICANT).
Adjustments: all four fire. Sum: `2 + 4 = 6`. Clamped at `max_tier = 3`.
**Tier: COMMERCIAL-OPPORTUNITY.**

### Example 4 — P0 with no metric adjustments → SIGNIFICANT not COMMERCIAL-OPPORTUNITY

A P0 friction with small population, low frequency, no cohort
concentration, small counterfactual — the friction itself is severe,
but fixing it doesn't unlock material commercial volume.

```
shape:   signature_id=dwell_after_error, journey_category=choke_point,
         screen_class=credit_application, severity=P0
metrics: affected_customers_7d=20, avg_events_per_affected_user=1.0,
         vulnerable_cohort_share=0.1, counterfactual_baseline_pct=0.05
policy:  affected_customers_7d_window=500
```

Base tier: `P0 → 2` (SIGNIFICANT). No adjustments fire.
**Tier: SIGNIFICANT.**

This is the case worth understanding: a P0 friction can be `SIGNIFICANT`
on the Value axis without being `COMMERCIAL-OPPORTUNITY`. Severity and
commercial value are correlated but not identical — Value methodology
keeps the distinction visible.

### Example 5 — Same Risk inputs, different Value adjustments

The Risk axis would treat Example 4 above as `ESCALATE` (P0 base, no
regulatory match, no thresholds crossed, no Chronicle precedent). The
Value axis treats it as `SIGNIFICANT`. The 2×2 cell is
**(Risk=ESCALATE, Value=SIGNIFICANT)** → renders as **ACUTE** in the
downstream CLARK-style Action tier (high on both axes).

By contrast Example 2 above sits at (Risk=WATCH, Value=SIGNIFICANT) —
this is the kind of cell that produces a `COMMERCIAL-OPPORTUNITY`
Action tier downstream: worth fixing for the commercial unlock,
without crossing a regulatory line.

### Example 6 — Same inputs, same tier (determinism)

`score_value()` is a pure function. Calling it twice with the same
inputs returns `ValueScore` instances with identical `tier`,
`numeric_tier`, `methodology_version`, and `inputs_hash`. A test
asserts this round-trip — symmetric with Risk.

## Why thresholds are fixed in the methodology at v0

The three internal thresholds (`threshold_events_per_user=3`,
`threshold_cohort_share=0.4`, `threshold_baseline_pct=0.25`) live in
[`value_methodology.yaml`](./value_methodology.yaml) rather than in
[`pulse/contracts/bank_policy.yaml`](../contracts/bank_policy.yaml).
This is deliberate at v0:

- the methodology should be reproducible across deployments without
  per-bank tuning (CASP discipline)
- moving thresholds to `bank_policy.yaml` would let banks tune their
  way down to never crossing a tier — Value should resist that
  for the same reason Risk does

v0.2 may move some thresholds to per-deployment configuration once the
methodology has been observed in real deployments and the
single-population threshold (`affected_customers_7d_window`) has
proven workable as the cross-axis anchor.

## Why monotonic adjustments (vs continuous score)

Same answer as Risk: a closed tier-enum is easier to reason about and
brief on than a continuous score, and adjustment-only-up keeps the
audit-trail story simple ("this base tier, plus these adjustments,
clamped at the top"). The numeric tier (0..3) is exposed for
downstream sorting / 2×2 cell logic.

## v0.3 — friction-volume PRIMARY, £ scaffold SECONDARY

The categorical tier is a prioritisation badge. The **primary commercial
unit** is friction-volume: `recoverable_sessions_per_week` /
`recoverable_sessions_per_month` = `affected_customers_7d ×
counterfactual_baseline_pct` (scaled to the window). Computed from metrics
alone — **no ARPU dependency**, always populated. This is the unit surfaces
MUST lead with: it is in the bank's own outcome vocabulary (sessions
recovered, calls deflected, abandonments prevented) and carries no
monetisation assumption.

**Raw £ as a primary signal is forbidden** (the assumption Pandora's box —
every £ figure invites scrutiny on ARPU / baseline / cohort definitions,
derailing the conversation onto methodology instead of friction). The
`estimated_monthly_lift_gbp` field remains as a **secondary cost scaffold**
only: renderers show it as "≈ £X/mo at £Y/session", naming the per-session
ARPU assumption (`arpu_per_session_gbp`) so the reader sees the assumption,
not just the conclusion. Never the lead stat.

## v0.2 — sized commercial estimate (PULSE-107)

The categorical tier above is a prioritisation badge — it answers "which
packs should the product team pay attention to first?" It does **not**
answer "how much money is at stake?" v0.2 added a sized £ estimate; v0.3
(above) demotes it to a scaffold and makes friction-volume primary.

**Output fields on `ValueScore` (v0.2):**

| Field | Type | Populated when |
|---|---|---|
| `estimated_monthly_lift_gbp` | `float \| None` | `bank_policy.arpu_per_journey[shape.journey_category]` is configured |
| `conversion_rate_delta` | `float \| None` | Always (aliased to `metrics.counterfactual_baseline_pct`) |
| `confidence_interval` | `tuple[float, float] \| None` | Never in v0.2 — reserved for v0.3 (bootstrap fixture from HOL-48) |
| `arpu_source` | `str \| None` | `"bank_policy"` when ARPU matched; `None` when missing |

**Formula:**

```
estimated_monthly_lift_gbp
  = affected_customers_7d
  × weekly_to_monthly_multiplier
  × counterfactual_baseline_pct
  × arpu_per_journey[journey_category]
```

`weekly_to_monthly_multiplier ≈ 4.345` (= 365.25 / 12 / 7, avg days per
month ÷ days per week). Lives in `value_methodology.yaml` under
`commercial_estimate.weekly_to_monthly_multiplier`.

### Worked example — sized lift on a COMMERCIAL-OPPORTUNITY pack

Picking up Example 3 above (P0 + all four adjustments → COMMERCIAL-OPPORTUNITY),
assuming the bank has configured `arpu_per_journey[choke_point] = £25/customer/month`:

```
affected_customers_7d         = 12,500
weekly_to_monthly_multiplier  = 4.345
counterfactual_baseline_pct   = 0.40
arpu                          = 25.0

monthly_lift_gbp = 12500 × 4.345 × 0.40 × 25.0
                 ≈ £543,125 / month
```

ValueScore output (abbreviated):
```python
ValueScore(
  tier="COMMERCIAL-OPPORTUNITY",
  numeric_tier=3,
  estimated_monthly_lift_gbp=543_125.0,
  conversion_rate_delta=0.40,
  confidence_interval=None,             # v0.2 ships point estimate only
  arpu_source="bank_policy",
  ...
)
```

### Worked example — ARPU not configured for this journey

Same pack as Example 3, but the bank's `bank_policy.yaml` has not
configured ARPU for `journey_category=choke_point`:

```python
ValueScore(
  tier="COMMERCIAL-OPPORTUNITY",         # categorical tier unaffected
  numeric_tier=3,
  estimated_monthly_lift_gbp=None,       # no ARPU → no sized output
  conversion_rate_delta=0.40,            # still computable from inputs
  confidence_interval=None,
  arpu_source=None,
  ...
)
```

The renderer shows the badge as usual; the £ strip stays hidden until
the deployment commits to per-journey ARPU. The engine deliberately
fails open here — `None` is a valid state, not an error.

### Why ARPU is in `bank_policy.yaml`, not `value_methodology.yaml`

ARPU is per-deployment by nature (different banks, different product
mixes, different commercial baselines). It belongs in the per-deployment
contract, not the methodology rubric — same logic as the
`affected_customers_7d_window` threshold. The methodology fixes the
formula; the bank commits the inputs.

### Why no confidence interval in v0.2

Hubbard's principle (HOL-48): any sized estimate without an uncertainty
band invites false precision. v0.2 ships the structure
(`confidence_interval: tuple[float, float] | None`) but always returns
`None` until the bootstrap fixture from HOL-48 lands. Surfacing a
fabricated CI from the methodology's own assumptions would be worse
than transparency about the gap. v0.3 fills this in once HOL-48 ships
the engine-side bootstrap.

### Why methodology version bumped to 0.2.0

Per the in-place rule, any change to the public output of `score_value`
is a methodology-version change — downstream consumers may pin against
the version for audit reproducibility. The shape of `ValueScore`
extends, the `inputs_hash` payload extends (now includes resolved
`arpu_used`), and the `bank_policy.yaml` schema gains an optional
section. All three are version-pinned changes.

[PULSE-101]: https://cjipro.atlassian.net/browse/PULSE-101
[PULSE-107]: https://cjipro.atlassian.net/browse/PULSE-107
