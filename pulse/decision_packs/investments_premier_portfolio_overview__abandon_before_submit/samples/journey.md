## investments_premier_portfolio_overview__abandon_before_submit — Journey altitude

### What happened on `investments.premier.portfolio.overview`

Across **2026-05-10 to 2026-05-16**, 287 of 2,184
high-intent sessions (13.1%) abandoned the Premier portfolio
overview without initiating their inferred intended action (trade, advisor
message, or report download). High intent = the session entered with at
least one of: push notification about a portfolio drop, deep-link from an
advisor email, in-session search for a specific holding, or a chart
drilldown that focused an amount-input affordance.

Detector required:
- one or more entry intent signals
- dwell above the 90th-percentile baseline
- session exit with no `trade_initiated`, `advisor_message_sent`, or
  `report_downloaded` event
- (excluded) sessions that returned within 30 minutes — tab-parks
- (excluded) advised clients who initiated a phone call to their advisor
  within 24 hours — that's handoff, not abandonment

Statistical significance: **p = 0.004** against the rolling baseline
(n = 11,247).

### Entry intent distribution

| Entry intent | Sessions | Share |
|---|---:|---:|
| Push notification: portfolio drop | 142 | 49.5% |
| In-session holding search | 78 | 27.2% |
| Chart drilldown → amount-input focus | 41 | 14.3% |
| Advisor email deep-link | 26 | 9.1% |

### Inferred intended action (not taken)

| Inferred action | Sessions | Share |
|---|---:|---:|
| `trade_initiated` | 138 | 48.1% |
| `advisor_message_sent` | 89 | 31.0% |
| `report_downloaded` | 60 | 20.9% |

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| Premier · self_directed · age 35–54 | 149 | 51.9% | 2.4× |
| Premier · self_directed · age 55+ | 71 | 24.7% | 1.4× |
| Premier_Plus · self_directed · any | 38 | 13.2% | 1.6× |
| Premier · advised · any | 19 | 6.6% | 0.3× |
| (other) | 10 | 3.5% | 0.5× |

> **Fairness check triggered.** vulnerable_cohort_overrepresentation —
> sessions tagged `recent_significant_loss_band` make up 31% of the affected
> set vs 12% of high-intent sessions overall. Vulnerable clients may be
> abandoning trade flows because the cognitive load of the loss is higher
> than the friction the detector measures. Independent fairness review
> required before any nudge-based remediation rolls out — a re-engagement
> push to a stressed client is regulator-relevant.

### 24-hour return / handoff behaviour

- 42% of abandoning sessions returned to the screen within
  24 hours — recoverable with a re-engagement nudge.
- 78% of *advised* abandoners initiated a phone call to their advisor within
  24 hours — these are correctly excluded by the detector as handoffs, not
  abandonments. The 287 affected sessions skew self_directed accordingly.

### Suggested remediation category

`friction_at_trade_initiation` — the 49.5% of bursts entering from a
portfolio-drop push notification with `trade_initiated` as the inferred
action and an exit at the "confirm holdings to sell" step name the modal
failure: the user landed ready to act, but the trade flow doesn't carry the
context forward. Pre-selecting the holding from the push payload, surfacing
a one-tap confirm, and adding a "save trade draft" affordance addresses the
modal failure while leaving the underwriting / suitability checks intact.

Pair with `intent_capture_at_entry` to harden the inference (currently
push-payload deep-linking discards the trigger-holding context by step 2).

### Confidence

Detector reports **medium-high** (0.71–0.84,
bootstrap CI 95%). Brier score on the calibration set: 0.12.
