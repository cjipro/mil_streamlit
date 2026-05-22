## cards_credit_apply_eligibility__dwell_after_error — Journey altitude

### What happened on `cards.credit.apply.eligibility`

Across **2026-05-10 to 2026-05-16**, 2,214 of 18,341 sessions
(12.1%) showed the `dwell_after_error` pattern: an eligibility
error followed by a dwell of 73s (median) —
58% above the screen's 28-day baseline.

Statistical significance: **p = 0.0009** against the rolling baseline
(n = 22,108). Above the configured threshold of
p<0.01.

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Age 18–24 · thin-file | 1,041 | 47.0% | 2.4× |
| Gig / self-employed · any age | 487 | 22.0% | 2.0× |
| Recent job change · age 25–34 | 308 | 13.9% | 1.6× |
| Age 35–54 · PAYE | 224 | 10.1% | 0.7× |
| Other | 154 | 7.0% | 0.5× |

> **Fairness check triggered.** vulnerable_cohort_overrepresentation —
> thin-file 18–24 users make up 47% of the affected sessions vs 19% of
> eligibility-screen traffic overall (2.4× overrepresentation). Independent
> fairness review required before remediation rollout. Consumer Duty
> foreseeable-harm rules apply: pre-decline friction concentrated in protected
> or vulnerable cohorts is a reportable outcome harm.

### Most-cited error types

- `ELIGIBILITY_PRE_DECLINE` — 1,196 occurrences (54% of errors)
- `INCOME_THRESHOLD_NOT_MET` — 481 occurrences (22% of errors)
- `CREDIT_AUTHORIZATION_DECLINED` — 268 occurrences (12% of errors)
- `EMPLOYMENT_VERIFICATION_FAILED` — 174 occurrences (8% of errors)
- `OTHER` — 95 occurrences (4% of errors)

### Suggested remediation category

`decline_reason_transparency` — `ELIGIBILITY_PRE_DECLINE` dominates the
error mix (54%) and is currently rendered as a generic "we're unable to
offer you this card" message with no actionable detail. Surfacing the
underlying reason (thin file vs income vs residency) inline, paired with
a routing link to lower-limit cards the user is eligible for, addresses
the dwell signal AND the Consumer Duty foreseeable-harm exposure on
thin-file 18–24 users.

### Confidence

Detector reports **high** (0.84–0.92,
bootstrap CI 95%). Brier score on the calibration set: 0.07.
