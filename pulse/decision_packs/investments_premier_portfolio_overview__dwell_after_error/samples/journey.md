## investments_premier_portfolio_overview__dwell_after_error — Journey altitude

### What happened on `investments.premier.portfolio.overview`

Across **2026-05-10 to 2026-05-16**, 1,247 of 9,108 sessions
(13.7%) on the Premier portfolio overview met the naive
`dwell_after_error` trigger: a prior minor event (filter returned no results,
date range with no data, or transient load hiccup) followed by a dwell of
142s (median) — 61% above the screen's
28-day baseline.

**The detector fired on 0 of these 1,247 sessions.** The negative-class
discriminator suppressed the remaining 1,247 (100%) because at least one
engagement signal was present. This is the cell-10 mechanism: long dwell on
a Premier portfolio is the *signal* of deliberate review, not friction.

### Suppression-signal distribution (across the 1,247 candidates)

| Engagement signal | Sessions exhibiting | Share | Threshold | Direction |
|---|---:|---:|---:|---|
| `scroll_depth_pct` | 1,041 | 83.5% | 60 | above |
| `chart_drilldowns_in_session` | 894 | 71.7% | 2 | above_or_equal |
| `return_within_7_days` | 885 | 71.0% | true | equals |

Median scroll depth across candidates: **78%**.
Median chart drilldowns per candidate session: **3.4**.
7-day return rate across candidates: **71%**.

### Cohort split (across all 1,247 candidates)

| Cohort | Sessions | Share | Suppression rate |
|---|---:|---:|---:|
| Premier_Plus · advised · age 55+ | 462 | 37.0% | 100% |
| Premier · self_directed · age 55+ | 318 | 25.5% | 100% |
| Premier · self_directed · age 35–54 | 211 | 16.9% | 100% |
| Premier_Plus · self_directed · age 55+ | 154 | 12.3% | 100% |
| Premier · advised · age 35–54 | 71 | 5.7% | 100% |
| (other) | 31 | 2.5% | 100% |

> No fairness flag triggered. False-positive rate by cohort: 0.0% across all
> reported cohorts. The suppression mechanism is applied uniformly; no cohort
> bears disproportionate false-positive burden because no cohort bears any.

### Why this matters

Cell 10 is the FrictionBench load-bearing negative. A detector that fires on
deliberate-review dwell is *misreading behaviour* — it would recommend
remediation on a screen the user is choosing to engage with, eroding the
Premier experience and producing audit findings the bank cannot defend.

The discriminator's `fire_only_if` rule restricts firing to error types
(`data_load_failed`, `account_authorization_lost`) that genuinely block the
user from seeing their portfolio. Minor filter and date-range events do not
qualify. In this run, zero candidate sessions carried a blocking error type
AND lacked engagement signals.

### Suggested action

`none_expected_at_cell_10` — the deliverable for cell 10 is the non-fire
itself. Operations should monitor the suppression rate (target: ≥95% across
all candidate sessions) and the false-positive rate (target: ≤2%); a drift
in either is the early warning that the discriminator needs recalibration.

### Confidence

Detector reports **high** (0.88–0.95,
bootstrap CI 95%). Brier score on the calibration set: 0.06.
False-positive rate on cell-10 ground truth: 0.000.
