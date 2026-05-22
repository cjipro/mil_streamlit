## loans_apply_step3__multi_back_press — Journey altitude

### What happened on `loans.apply.step3`

Across **2026-05-10 to 2026-05-16**, 612 of 12,506 sessions
(4.9%) showed the `multi_back_press` pattern: 4+
back-navigation events within a 95s window, median
inter-press interval 11s.

The discriminator (`inter_press_interval < 20s`) is what separates these from
deliberate-review sessions; the affected cohort is moving back-and-forward
too fast to be reading.

Statistical significance: **p = 0.0007** against the rolling baseline
(n = 14,902).

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| First-time visitor · mobile | 355 | 58.0% | 2.6× |
| First-time visitor · desktop | 91 | 14.9% | 1.4× |
| Returning · mobile | 88 | 14.4% | 0.6× |
| Returning · desktop | 78 | 12.7% | 0.5× |

> **Fairness check triggered.** Cohort recall disparity
> 0.32 exceeds the pack's configured trigger of
> 0.15. Independent fairness review required before
> remediation rollout.

### Outcome distribution

| Exit outcome | Sessions | Share |
|---|---:|---:|
| Abandoned at step 3 | 287 | 46.9% |
| Returned to step 2 then forward | 198 | 32.4% |
| Completed application | 84 | 13.7% |
| Switched to assisted channel | 43 | 7.0% |

### Suggested remediation category

`progress_indicator_clarity` — outcome distribution shows 47% abandonment
after the burst; first-time mobile users are the dominant cohort. The
step indicator on mobile is collapsed into a dropdown by default — making
"3 of 5" persistently visible (and showing a prior-step summary card)
addresses the "where am I" signal the back-press burst is sending.

### Confidence

Detector reports **high** (0.79–0.88,
bootstrap CI 95%). Brier score on the calibration set: 0.09.
