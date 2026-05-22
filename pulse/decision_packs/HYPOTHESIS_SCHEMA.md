# Decision-pack hypothesis schema — canvas-completeness

Filed under [PULSE-103]. Peer doc: [`METADATA_SCHEMA.md`](./METADATA_SCHEMA.md).
Machine-readable schema: [`hypothesis_schema.yaml`](./hypothesis_schema.yaml).
Validator: [`validate_hypothesis.py`](./validate_hypothesis.py).

## What hypothesis declares

Every decision pack ships a `hypothesis.yaml` per cell-signature pair.
This schema covers the **canvas-completeness** slots — the
declared fields the engine needs to drive Value (PULSE-101) and Risk
(PULSE-99) tier computation, plus the actor-role slot that drives
briefing-surface composition.

Analytic fields (`cell_id`, `signature_id`, `analytic`, `cohort_axes`,
`evidence_required`, etc.) pre-date this schema and are not yet
validator-enforced; they'll join the validator as the analytic layer
stabilises.

## Two gates

### Gate 1 — canvas-completeness

Pack MUST declare:
- `actors` — non-empty list from the closed enum
  `{investigation_consumer, ml_engineer, mrm_reviewer, compliance_reviewer}`
- `value_inputs` — mapping with three required keys (`severity_class`,
  `vulnerable_cohort_sensitivity`, `population_segment_addressed`)
- `risk_inputs` — mapping with two required keys + one optional
  (`regulatory_taxonomies`, `policy_areas`, optional `chronicle_precedents`)

### Gate 2 — computed-slot immutability

Pack MUST NOT declare:
- `value_output` — owned by the Value methodology (PULSE-101)
- `risk_output` — owned by the Risk methodology (PULSE-99)

Mirrors the `synthesis_mode != llm_augmented` immutability gate in
[`METADATA_SCHEMA.md`](./METADATA_SCHEMA.md). Pack-authored declarations
of computed slots would defeat the reproducibility +
per-deployment-relevance posture both methodologies depend on.

## Field reference

### `actors` (list[enum], required, non-empty)

Closed set of consumer roles this pack is built for. Drives downstream
rendering (which actor's altitude the briefing surface composes for) and
access scoping.

| Value | Used by |
|---|---|
| `investigation_consumer` | Workspace surface (HOL-3) |
| `ml_engineer` | MLOps Console (HOL-6) |
| `mrm_reviewer` | MLOps Console (HOL-6), MRM lens |
| `compliance_reviewer` | Briefing surface (HOL-9), Risk badge focus |

### `value_inputs` (mapping, required)

What the Value methodology needs the pack to declare. The engine
combines these with runtime telemetry + bank_policy to compute the
Value tier.

| Key | Type | Notes |
|---|---|---|
| `severity_class` | enum: `high` / `medium` / `low` | Pack-author declared severity. Maps to `P0` / `P1` / `P2` in the methodology |
| `vulnerable_cohort_sensitivity` | bool | Does the pack expect friction to disproportionately affect vulnerable cohorts? |
| `population_segment_addressed` | non-empty string | Customer segment ID (free-form at v0) |

### `risk_inputs` (mapping, required)

What the Risk methodology needs the pack to declare.

| Key | Type | Notes |
|---|---|---|
| `regulatory_taxonomies` | list[string] (may be empty) | Each entry must match a `taxonomy_code` in [`pulse/risk/regulatory_taxonomy.yaml`](../risk/regulatory_taxonomy.yaml). Validator cross-checks. |
| `policy_areas` | list[string] (may be empty) | Bank-internal policy-area IDs. NOT cross-validated at pack registration — `bank_policy.yaml` is per-deployment. |
| `chronicle_precedents` | list[string] (optional) | Pointers to CHR-friction-NNN entries. Validator checks format; does not check existence (precedents may be authored later). |

## Worked example

```yaml
# pack hypothesis.yaml — canvas-completeness slots

actors:
  - investigation_consumer
  - compliance_reviewer

value_inputs:
  severity_class: high
  vulnerable_cohort_sensitivity: true
  population_segment_addressed: uk_retail_credit_applicants

risk_inputs:
  regulatory_taxonomies:
    - fca_consumer_duty.outcome_3_consumer_understanding
    - fca_consumer_duty.outcome_4_consumer_support
  policy_areas:
    - vulnerable_customer_handling
  chronicle_precedents:
    - CHR-friction-005
```

A pack declaring `value_output` or `risk_output` is rejected with a
message pointing at the methodology that owns the computed slot.

## Loading from Python

```python
from pulse.decision_packs import load_hypothesis, DecisionPackHypothesisError

try:
    hyp = load_hypothesis("packs/my_pack/hypothesis.yaml")
except DecisionPackHypothesisError as e:
    # pack does not register
    raise
```

[PULSE-103]: https://cjipro.atlassian.net/browse/PULSE-103
