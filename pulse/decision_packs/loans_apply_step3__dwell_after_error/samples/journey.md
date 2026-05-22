## loans_apply_step3__dwell_after_error — Journey altitude

### What happened on `loans.apply.step3`

Across **2026-05-10 to 2026-05-16**, 1,847 of 12,506 sessions
(14.8%) showed the `dwell_after_error` pattern: a validation error
followed by a dwell of 87s (median) — 46%
above the screen's 28-day baseline.

Statistical significance: **p = 0.003** against the rolling baseline
(n = 14,902). Above the configured threshold of
p<0.01.

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Mobile · age 55+ | 758 | 41.0% | 2.1× |
| Mobile · age 35–54 | 412 | 22.3% | 1.1× |
| Desktop · age 55+ | 267 | 14.5% | 1.4× |
| First-time visitor | 198 | 10.7% | 1.6× |
| Returning visitor | 212 | 11.5% | 0.7× |

> **Fairness check triggered.** Cohort recall disparity
> 0.21 exceeds the pack's configured trigger of
> 0.15. Independent fairness review required before
> remediation rollout.

### Most-cited error types

- `INCOME_DOC_FORMAT_REJECTED` — 1,094 occurrences (59% of errors)
- `EMPLOYMENT_DATE_RANGE_INVALID` — 463 occurrences (25% of errors)
- `ADDRESS_LOOKUP_TIMEOUT` — 187 occurrences (10% of errors)
- `OTHER` — 103 occurrences (6% of errors)

### Suggested remediation category

`template_fix` — INCOME_DOC_FORMAT_REJECTED dominates the error mix and is
upstream of every other failure mode at this step; clarifying the validator
message and accepted-format guidance addresses 59% of the affected sessions
with one change.

### Confidence

Detector reports **high** (0.82–0.91,
bootstrap CI 95%). Brier score on the calibration set: 0.08.
