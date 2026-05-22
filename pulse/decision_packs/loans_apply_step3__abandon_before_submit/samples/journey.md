## loans_apply_step3__abandon_before_submit — Journey altitude

### What happened on `loans.apply.step3`

Across **2026-05-10 to 2026-05-16**, 1,103 of 8,402
high-intent sessions (13.1%) abandoned the loan application at
step 3 without clicking submit. High intent = both step 1 and step 2 completed
cleanly; these users reached the final input page and stopped.

Detector required:
- prior completion of step 1 and step 2
- dwell on step 3 above the 90th-percentile baseline
- session exit with no `submit_clicked` event
- (excluded) sessions that returned within 30 minutes — those are tab-parks,
  not true abandonments

Statistical significance: **p = 0.001** against the rolling baseline
(n = 14,902).

### Final-field focus distribution

The field the user was looking at when they left:

| Field | Sessions | Share |
|---|---:|---:|
| `monthly_outgoings_total` | 562 | 51.0% |
| `employer_address_line1` | 196 | 17.8% |
| `loan_purpose_other_text` | 154 | 14.0% |
| `monthly_income_other` | 98 | 8.9% |
| (other) | 93 | 8.4% |

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Age 25–34 · first-time borrower | 485 | 44.0% | 1.8× |
| Age 35–54 · first-time borrower | 264 | 23.9% | 1.2× |
| Age 25–34 · repeat borrower | 167 | 15.1% | 0.7× |
| Age 55+ · any | 142 | 12.9% | 1.3× |
| (other) | 45 | 4.1% | 0.4× |

> **Fairness check triggered.** vulnerable_cohort_overrepresentation —
> sessions tagged `recent_credit_decline` make up 28% of the affected
> set vs 11% of high-intent sessions overall. Independent fairness review
> required before remediation rollout.

### 24-hour return behaviour

37% of abandoning sessions returned to step 3 within
24 hours — these are recoverable with a save-and-resume affordance or a
proactive nudge.

### Suggested remediation category

`field_specific_friction_removal` — the final-field distribution names a
single dominant friction point (`monthly_outgoings_total`, 51% of
abandonments). Breaking the field into guided sub-components and offering
an "estimate later" path addresses the modal failure mode while preserving
the underwriting signal.

### Confidence

Detector reports **medium-high** (0.74–0.86,
bootstrap CI 95%). Brier score on the calibration set: 0.11.
