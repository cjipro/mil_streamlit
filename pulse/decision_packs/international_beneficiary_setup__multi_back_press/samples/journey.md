## international_beneficiary_setup__multi_back_press — Journey altitude

### What happened on `international.beneficiary.setup`

Across **2026-05-10 to 2026-05-16**, 387 of 6,318 sessions
(6.1%) showed the `multi_back_press` pattern: 5+
back-navigation events within a 108s window, median
inter-press interval 9s.

The discriminator (`inter_press_interval < 20s`) is what separates these from
deliberate fee/corridor review sessions; the affected cohort is moving
back-and-forward too fast to be reading the corridor preview.

Statistical significance: **p = 0.0004** against the rolling baseline
(n = 7,884).

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| First-time intl sender · personal | 209 | 54.0% | 2.3× |
| First-time intl sender · business | 64 | 16.5% | 1.5× |
| Repeat intl sender · personal | 58 | 15.0% | 0.7× |
| Repeat intl sender · business | 32 | 8.3% | 0.4× |
| (other) | 24 | 6.2% | 0.5× |

> **Fairness check triggered.** Cohort recall disparity
> 0.28 exceeds the pack's configured trigger of
> 0.15. Independent fairness review required before
> remediation rollout.

### Outcome distribution

| Exit outcome | Sessions | Share |
|---|---:|---:|
| Abandoned at beneficiary screen | 174 | 45.0% |
| Returned to corridor select then forward | 116 | 30.0% |
| Completed beneficiary save | 58 | 15.0% |
| Switched to assisted / branch channel | 39 | 10.1% |

### Suggested remediation category

`corridor_fee_inline_summary` — 30% of affected sessions returned to the
corridor-select screen and came back, indicating the user wanted to
re-verify the FX rate or fee against what they were about to send to.
A pinned summary card on the beneficiary screen (corridor, mid-market
vs offered rate, arrival window, total fee) removes the need for the
round-trip and addresses 45% abandonment in the same cohort by reducing
the friction of "wait, what was I quoted?".

### Confidence

Detector reports **high** (0.80–0.89,
bootstrap CI 95%). Brier score on the calibration set: 0.10.
