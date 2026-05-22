## cards_credit_apply_eligibility__abandon_before_submit — Journey altitude

### What happened on `cards.credit.apply.eligibility`

Across **2026-05-10 to 2026-05-16**, 1,486 of 11,209
sessions that completed the eligibility form inputs (13.3%) left
the screen without clicking "check eligibility". These users filled the form
but did not submit — they read what they had typed and chose not to let the
bank look at their credit file.

Detector required:
- prior completion of income_range_band, employment_status, residency_duration_years
- dwell on eligibility screen above the 90th-percentile baseline
- session exit with no `eligibility_check_submitted` event
- (excluded) sessions that returned within 30 minutes — those are tab-parks,
  not true abandonments

Statistical significance: **p = 0.0006** against the rolling baseline
(n = 22,108).

### Final-field focus distribution

The field the user was looking at when they left:

| Field | Sessions | Share |
|---|---:|---:|
| `credit_authorization_consent` | 698 | 47.0% |
| `existing_credit_commitments` | 252 | 17.0% |
| `income_range_band` | 193 | 13.0% |
| `employment_duration_months` | 163 | 11.0% |
| `residency_duration_years` | 104 | 7.0% |
| (other) | 76 | 5.1% |

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Age 18–24 · thin-file · new-to-credit | 579 | 39.0% | 2.0× |
| Gig / self-employed · any age | 327 | 22.0% | 1.8× |
| Recent job change · age 25–34 | 193 | 13.0% | 1.4× |
| Age 35–54 · PAYE | 178 | 12.0% | 0.6× |
| Existing-card high-utilisation · any | 134 | 9.0% | 1.2× |
| (other) | 75 | 5.0% | 0.4× |

> **Fairness check triggered.** closed_door_cohort_return_rate — thin-file
> 18–24 abandoners returned at 6% within 7 days, below the configured 10%
> floor. This is "closed door" behaviour: a cohort overrepresented in
> abandonment AND under-returning is consistent with a product that
> structurally won't serve them. Independent fairness review required before
> remediation rollout. Closed-door cohort return rates trigger Consumer
> Duty outcome-2 and outcome-3 reporting consideration.

### Return behaviour (the load-bearing sub-variation)

| Window | Returned | Share |
|---|---:|---:|
| Within 24h | 163 | 11.0% |
| Within 7d  | 282  | 19.0% |
| Never (in window) | 1,204 | 81.0% |

Unlike a multi-step loan application — where 24h return rates run ~37% and
save-and-resume is the dominant lever — this screen's abandoners return at
~11% in 24h and ~19% in 7d. The
behaviour signature is "closed door" not "interrupted journey". Save-and-resume
would be cosmetic; the load-bearing remediation is transparency.

### Suggested remediation category

`soft_search_disclosure_clarity` — 47% of abandoners' final-focused field
is `credit_authorization_consent`, indicating the user was reading the
soft-search disclosure and chose not to proceed. The current copy ("we
may check your credit file") reads as a hard search to many users.
Replacing with explicit "this is a soft search, no footprint on your
credit file, will not affect your score" + surfacing eligible lower-limit
products for the declared profile addresses the modal abandonment reason
while keeping the eligibility check honest.

### Confidence

Detector reports **medium-high** (0.76–0.87,
bootstrap CI 95%). Brier score on the calibration set: 0.10.
