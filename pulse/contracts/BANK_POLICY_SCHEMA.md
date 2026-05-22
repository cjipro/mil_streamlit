# `bank_policy.yaml` — per-deployment policy contract

Per-deployment configuration carrying bank-internal escalation thresholds,
policy-area mappings, and vulnerable-cohort extensions. Read at engine
startup by the Pulse Risk methodology ([PULSE-99]) and Value methodology
([PULSE-101]).

Pulse ships **no bank-specific defaults**. Every threshold below must be
set explicitly on deployment; the validator refuses to start if a required
threshold is missing or still carries a `<TBD>` placeholder. The shipped
[`bank_policy.yaml`](./bank_policy.yaml) is a placeholder template — it
intentionally fails strict validation, and a test enforces that.

Filed under [PULSE-102].

## Naming discipline

This file MUST NOT contain the real bank's name. `deployment_id` is an
opaque token chosen at deployment time. Logs, audit bundles, and any
artifact derived from this file inherit that discipline. Same rule as
[`real_bank_contract.yaml`](./real_bank_contract.yaml).

## Fields

### `version` (string, required)

Contract version. Bump on field-shape change. Currently `0.1.0`.

### `deployment_id` (string, required)

Opaque per-deployment token. Used in audit bundles and lineage chains to
identify which deployment produced a decision pack. **Never the bank's
name** — use a hash, a slug, or any opaque identifier the bank chooses.

### `escalation_thresholds` (mapping, required)

Bank-committed thresholds that escalate a friction signature's Risk tier
when crossed. No defaults — every key must be present and resolved.

- **`affected_customers_7d_window`** (non-negative integer, required) —
  number of customers affected within a rolling 7-day window above which
  the Risk methodology escalates one tier.
- **`vulnerable_cohort_overrep_floor`** (number ≥ 1.0, required) — ratio
  of a cohort's harm rate to the baseline population harm rate. Above
  this floor, the fairness gate escalates the Risk tier one step. The
  regulator's informal anchor sits around 1.25; banks may commit to a
  stricter floor.

### `policy_areas` (list of mappings, required, may be empty)

Bank-internal policy areas mapped onto regulatory taxonomies Pulse
already understands. Risk methodology resolves a friction signature onto
the bank's own internal policy register so investigators see
"Policy 4.7 — Affordability Review" instead of "fca_consumer_duty_2.0 /
PRIN 12" alone.

Each entry:
- **`internal_name`** (non-empty string) — bank's internal policy register
  name.
- **`regulatory_taxonomy`** (enum) — currently must be
  `fca_consumer_duty_2.0`. New taxonomies require a Pulse engine release.
- **`regulatory_section`** (non-empty string) — e.g. `PRIN 12`.

### `vulnerable_cohort_extensions` (list of mappings, required, may be empty)

Optional bank-specific extensions to FCA Consumer Duty vulnerable-cohort
definitions. **Never replaces the regulator's baseline set** — only adds
bank-specific cohorts the bank has internally committed to monitor at the
same standard. Empty list is valid and means "use regulator baseline only."

Each entry:
- **`cohort_id`** (non-empty string, unique within file) — bank-defined slug.
- **`description`** (non-empty string) — one-line description.
- **`rationale`** (non-empty string) — why this cohort warrants
  vulnerable-cohort treatment.

## Loading from Python

```python
from pulse.contracts import load_bank_policy, BankPolicyError

try:
    cfg = load_bank_policy("path/to/deployment_bank_policy.yaml")
except BankPolicyError as e:
    # engine refuses to start
    raise
```

[PULSE-99]: https://cjipro.atlassian.net/browse/PULSE-99
[PULSE-101]: https://cjipro.atlassian.net/browse/PULSE-101
[PULSE-102]: https://cjipro.atlassian.net/browse/PULSE-102
