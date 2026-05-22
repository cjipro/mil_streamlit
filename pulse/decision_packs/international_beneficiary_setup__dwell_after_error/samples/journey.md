## international_beneficiary_setup__dwell_after_error — Journey altitude

### What happened on `international.beneficiary.setup`

Across **2026-05-10 to 2026-05-16**, 924 of 6,318 sessions
(14.6%) showed the `dwell_after_error` pattern: a validation error
followed by a dwell of 142s (median) — 62%
above the screen's 28-day baseline. The cross-border
error taxonomy is wider than retail forms; users with no prior international-
sender history have less context to decode the message.

Statistical significance: **p = 0.001** against the rolling baseline
(n = 7,884). Above the configured threshold of
p<0.01.

### Cohort split

| Cohort | Affected sessions | Share | Recall vs overall |
|---|---:|---:|---:|
| First-time intl sender · non-English UI | 434 | 47.0% | 2.4× |
| First-time intl sender · English UI | 198 | 21.4% | 1.3× |
| Repeat intl sender · high-risk corridor | 124 | 13.4% | 1.6× |
| Age 55+ · any | 98 | 10.6% | 1.5× |
| (other) | 70 | 7.6% | 0.6× |

> **Fairness check triggered.** name_pattern_sanctions_disparity —
> sessions where the beneficiary name triggered a `COUNTRY_SANCTIONS_HOLD`
> fall disproportionately on senders to high-Muslim-majority corridors
> (disparity 0.18 vs the 0.10 trigger). Sanctions-screening behaviour is
> regulator-mandated, but the **UX of the hold message** is in our gift
> and is the lever the pack proposes acting on. Independent fairness
> review required before any sanctions-message redesign rollout.

### Most-cited error types

- `SWIFT_BIC_INVALID` — 412 occurrences (38% of errors)
- `IBAN_CHECKSUM_FAIL` — 247 occurrences (23% of errors)
- `NAME_LATIN_CHARS_REQUIRED` — 196 occurrences (18% of errors)
- `COUNTRY_SANCTIONS_HOLD` — 142 occurrences (13% of errors)
- `ADDRESS_FATF_INCOMPLETE` — 87 occurrences (8% of errors)

### Suggested remediation category

`swift_lookup_affordance` — `SWIFT_BIC_INVALID` is the modal error (38%) and
is almost always self-inflicted: the user typed what the receiving bank told
them without knowing it's not the 8/11-char format. A type-ahead bank-lookup
widget keyed on bank name + country resolves the field for the user and
removes the dominant friction. Pair with `latin_char_helper` on the
beneficiary-name field to cover the second-largest cohort cluster.

### Confidence

Detector reports **high** (0.81–0.90,
bootstrap CI 95%). Brier score on the calibration set: 0.09.
