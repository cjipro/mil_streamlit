## cards_credit_apply_eligibility__multi_back_press — Journey altitude

### What happened on `cards.credit.apply.eligibility`

Across **2026-05-10 to 2026-05-16**, 894 of 18,341 sessions
(4.9%) showed the `multi_back_press` pattern: 5+
back-navigation events within a 112s window, median
inter-press interval 9s.

The discriminator (`inter_press_interval < 20s`) is what separates these from
deliberate-review sessions. On this screen the pattern is value-fishing —
users are altering their income or employment-duration answers between
back-presses to find a combination that lets them through the eligibility
gate.

Statistical significance: **p = 0.0004** against the rolling baseline
(n = 22,108).

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Gig / self-employed · returning | 465 | 52.0% | 2.3× |
| New-to-credit · age 18–24 | 188 | 21.0% | 1.7× |
| Recent application <30d · any | 134 | 15.0% | 1.5× |
| PAYE · age 35–54 | 71 | 7.9% | 0.5× |
| Other | 36 | 4.0% | 0.4× |

> **Fairness check triggered.** Cohort recall disparity
> 0.28 exceeds the pack's configured trigger of
> 0.15. Independent fairness review required before
> remediation rollout.

### Field-value change distribution (within burst)

| Field | Sessions changing value | Share |
|---|---:|---:|
| `income_range_band` | 612 | 68.5% |
| `employment_duration_months` | 387 | 43.3% |
| `existing_credit_commitments` | 219 | 24.5% |
| `residency_duration_years` | 96 | 10.7% |

### Outcome distribution

| Exit outcome | Sessions | Share |
|---|---:|---:|
| Abandoned at eligibility | 491 | 54.9% |
| Submitted with revised values | 218 | 24.4% |
| Returned later, fresh session | 117 | 13.1% |
| Switched to assisted channel | 68 | 7.6% |

### Suggested remediation category

`pre_screen_eligibility_indicator` — 68% of burst sessions change
`income_range_band` and 43% change `employment_duration_months`. The
behaviour pattern is consistent with users not knowing where the threshold
sits and probing for it; making the threshold visible (or rendering a
likelihood indicator before submission) removes the incentive to value-fish
and reduces both abandonment and audit risk on misstated answers.

### Confidence

Detector reports **high** (0.80–0.89,
bootstrap CI 95%). Brier score on the calibration set: 0.08.
