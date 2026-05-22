## investments_premier_portfolio_overview__multi_back_press — Journey altitude

### What happened on `investments.premier.portfolio.overview`

Across **2026-05-10 to 2026-05-16**, 384 of 9,108 sessions
(4.2%) showed the `multi_back_press` pattern: 4+
back-navigation events within a 102s window, median
inter-press interval 13s.

The discriminator (`inter_press_interval < 20s`) is what separates these from
deliberate-review sessions. On the Premier portfolio overview, deliberate
navigation between time ranges is normal engagement; this signature fires
only on short-interval bursts that indicate the user is *looking for
something they expected to see*.

Statistical significance: **p = 0.002** against the rolling baseline
(n = 11,247).

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Premier · self_directed · age 35–54 | 180 | 46.9% | 2.2× |
| Premier · self_directed · age 55+ | 92 | 24.0% | 1.3× |
| Premier_Plus · self_directed · age 35–54 | 51 | 13.3% | 1.5× |
| Premier · advised · any | 38 | 9.9% | 0.5× |
| (other) | 23 | 6.0% | 0.4× |

> **Fairness check triggered.** Cohort recall disparity
> 0.18 exceeds the pack's configured trigger of
> 0.15. Independent fairness review required before
> remediation rollout.

### Filter / time-range state at back-press burst

| State at burst | Sessions | Share |
|---|---:|---:|
| Filter active from prior session (silently) | 242 | 63.0% |
| Time range mismatch (selected vs displayed) | 87 | 22.7% |
| Both filter + time-range issue | 41 | 10.7% |
| Neither — other navigation confusion | 14 | 3.6% |

### Outcome distribution

| Exit outcome | Sessions | Share |
|---|---:|---:|
| Filter eventually cleared, session continued | 158 | 41.1% |
| Abandoned session | 124 | 32.3% |
| Switched to mobile app | 67 | 17.4% |
| Initiated advisor message | 35 | 9.1% |

### Suggested remediation category

`filter_state_persistence` — 63% of bursts occurred with a silently-active
filter inherited from a prior session. The Premier portfolio overview
currently persists filters across sessions by design (for advised clients
working with an advisor across days); for self_directed clients the same
behaviour reads as the system being broken. Surfacing an "filters active: N"
chip with one-tap clear, and defaulting to "reset on session boundary" for
self_directed clients, addresses the modal failure mode without breaking
the advised-client workflow.

### Confidence

Detector reports **high** (0.81–0.90,
bootstrap CI 95%). Brier score on the calibration set: 0.08.
