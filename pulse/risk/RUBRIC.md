# Pulse Risk — rubric (worked examples)

Machine-readable rubric: [`rubric.yaml`](./rubric.yaml). Reference
scorer: [`score.py`](./score.py). Methodology paper:
[`RISK_DESIGN.md`](./RISK_DESIGN.md).

Filed under [PULSE-99].

## Tier words (closed enum)

| Numeric | Word | Meaning |
|---|---|---|
| 0 | `NOMINAL` | within expected range — no special flag |
| 1 | `WATCH` | moderate signal, monitoring warranted |
| 2 | `ESCALATE` | high-severity friction with material customer impact |
| 3 | `REGULATORY-FLAG` | crosses a published regulatory expectation, with crossed thresholds or chronicled precedent |

Extending the enum is a methodology-version change. The set is closed by
construction — a test asserts it.

## Worked examples

### Example 1 — P2 NOMINAL (no adjustments)

A low-severity friction on a journey not in scope of any regulatory
taxonomy, low affected count, no cohort over-representation, no
Chronicle precedent.

```
shape:    signature_id=lazy_scroll, journey_category=behavioural_noise,
          screen_class=marketing_page, severity=P2
impact:   affected_customers_7d=15, vulnerable_cohort_overrep_ratio=1.0
policy:   affected_customers_7d_window=500, vulnerable_cohort_overrep_floor=1.25
chronicle: empty
```

Base tier: `P2 → 0` (NOMINAL).
Adjustments: none fire.
**Tier: NOMINAL.**

### Example 2 — P1 with regulatory match → ESCALATE

A medium-severity friction on a `context_loss` journey class that the
regulatory taxonomy treats as a Consumer Understanding concern.

```
shape:    signature_id=unclear_validation_message,
          journey_category=context_loss, screen_class=credit_application,
          severity=P1
impact:   affected_customers_7d=200,  vulnerable_cohort_overrep_ratio=1.1
policy:   affected_customers_7d_window=500, vulnerable_cohort_overrep_floor=1.25
chronicle: empty
```

Base tier: `P1 → 1` (WATCH).
Adjustments: `regulatory_match` fires
(`fca_consumer_duty.outcome_3_consumer_understanding`).
**Tier: ESCALATE.** (1 + 1 = 2)

### Example 3 — P0 with all four adjustments → REGULATORY-FLAG

High severity. Regulatory match. Affected-customer threshold crossed.
Vulnerable-cohort over-representation crossed. Chronicle precedent matched.

```
shape:    signature_id=account_access_locked_out, journey_category=choke_point,
          screen_class=account_login, severity=P0
impact:   affected_customers_7d=12500, vulnerable_cohort_overrep_ratio=1.45
policy:   affected_customers_7d_window=500, vulnerable_cohort_overrep_floor=1.25
chronicle: TSB CHR-friction-001 verified, matches signature × screen × severity
```

Base tier: `P0 → 2` (ESCALATE).
Adjustments: `regulatory_match`, `affected_customers_threshold`,
`vulnerable_cohort_overrep`, `chronicle_precedent_match` — all four fire.
Sum: `2 + 4 = 6`. Clamped at `max_tier = 3`.
**Tier: REGULATORY-FLAG.**

### Example 4 — P0 absent regulatory match → ESCALATE not REGULATORY-FLAG

A P0 friction on a journey class no published regulatory taxonomy
covers, with material impact but no cohort skew, no Chronicle precedent.

```
shape:    signature_id=novel_friction_signature,
          journey_category=behavioural_noise, screen_class=novel_screen,
          severity=P0
impact:   affected_customers_7d=900, vulnerable_cohort_overrep_ratio=1.1
policy:   affected_customers_7d_window=500, vulnerable_cohort_overrep_floor=1.25
chronicle: empty
```

Base tier: `P0 → 2` (ESCALATE).
Adjustments: `affected_customers_threshold` fires.
**Tier: REGULATORY-FLAG.** (2 + 1 = 3)

Note: a P0 with even one adjustment escalates to the top tier. This is
the precautionary posture — P0 is by definition the engine asserting
the friction is severe; any further signal pushes it onto the
compliance team's docket.

### Example 5 — Chronicle library absent (soft dep)

Same shape as Example 3 but `chronicle_library=None`. The
`chronicle_precedent_match` adjustment cannot fire (there's no library
to match against), but all other adjustments work normally.

```
chronicle_library: None  # methodology degrades gracefully
```

The other three adjustments fire — tier still clamps to REGULATORY-FLAG.
The audit footprint records `chronicle_matches=[]` so a reviewer can see
the library was not consulted at scoring time.

### Example 6 — Same inputs, same tier (determinism)

`score_risk()` is a pure function. Calling it twice with the same
inputs returns `RiskScore` instances with identical `tier`,
`numeric_tier`, `methodology_version`, AND `inputs_hash`. A test
asserts this round-trip.

## Why no axis weights (vs FrictionBench's equal-weight scheme)

FrictionBench's per-axis scoring is on a continuous [0, 1] interval —
weights matter because axes can fight each other on the same detection.
Risk's adjustments are binary fires that each push the tier up by 1.
The relevant choices are (a) which adjustments exist, (b) what severity
the base tier starts at, (c) what the max tier is — all enumerated in
[`rubric.yaml`](./rubric.yaml).

[PULSE-99]: https://cjipro.atlassian.net/browse/PULSE-99
