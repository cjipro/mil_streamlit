## international_beneficiary_setup__abandon_before_submit — Journey altitude

### What happened on `international.beneficiary.setup`

Across **2026-05-10 to 2026-05-16**, 718 of 4,902
high-intent sessions (14.6%) abandoned the international payment
at the beneficiary review screen without firing `payment_initiated`. High
intent = corridor selected and beneficiary fields entered cleanly; these
users reached the final review page and stopped.

Detector required:
- prior completion of corridor_select and beneficiary_entry
- dwell on review screen above the 90th-percentile baseline
- session exit with no `payment_initiated` event
- (excluded) sessions that returned within 30 minutes — those are tab-parks,
  not true abandonments

Statistical significance: **p = 0.0006** against the rolling baseline
(n = 7,884).

### Final-field focus distribution

The field the user was looking at when they left:

| Field | Sessions | Share |
|---|---:|---:|
| `intermediary_bank_swift` | 280 | 39.0% |
| `sanctions_disclosure_modal` | 158 | 22.0% |
| `beneficiary_address_line2` | 108 | 15.0% |
| `fee_breakdown_disclosure` | 86 | 12.0% |
| `iban` | 54 | 7.5% |
| (other) | 32 | 4.5% |

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Age 35–54 · personal · high-risk corridor | 273 | 38.0% | 2.0× |
| Age 55+ · personal · any corridor | 152 | 21.2% | 1.6× |
| First-time intl · business | 122 | 17.0% | 1.4× |
| Repeat intl · personal · low-risk corridor | 96 | 13.4% | 0.6× |
| (other) | 75 | 10.4% | 0.5× |

> **Fairness check triggered.** corridor_risk_band_sanctions_disparity —
> high-risk-corridor sessions (predominantly remittance senders to FATF
> grey-list jurisdictions) abandon at the `sanctions_disclosure_modal`
> at 2.4× the rate of low-risk corridors, despite being equally likely to
> have a legitimate payment. Sanctions screening itself is non-negotiable
> (regulator-mandated), but the disclosure UX is in our gift and
> disproportionately drives drop-off in this cohort. Regulator-defensible
> justification on file: independent fairness review required before
> any sanctions-message redesign rollout, to confirm the redesign doesn't
> reduce the deterrent effect against actual illicit attempts.

### 24-hour return behaviour

41% of abandoning sessions returned to the beneficiary
review screen within 24 hours — these are recoverable with a save-and-resume
affordance or a proactive nudge (subject to sanctions re-screening on resume).

### Suggested remediation category

`intermediary_bank_auto_suggest` — the final-field distribution names a
single dominant friction point (`intermediary_bank_swift`, 39% of
abandonments). For ~85% of our supported corridors the intermediary bank
is auto-routable and the field is shown only because the original 2014
flow was built before that routing existed. Hiding it by default (with
"advanced" expand) addresses the modal failure mode. Stack with
`sanctions_disclosure_clarity` to address the second-largest cluster
and the fairness-flagged cohort in one ship.

### Confidence

Detector reports **medium-high** (0.76–0.87,
bootstrap CI 95%). Brier score on the calibration set: 0.12.
