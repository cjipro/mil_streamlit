# Pulse Risk methodology v0 — design

CASP-style methodology paper. Published before any production Risk score
runs against bank deployments. Mirrors the FrictionBench discipline of
publishing the rubric before the scores.

Filed under [PULSE-99].

## What Risk is, in one sentence

Risk is a **computed** canvas slot — not author-declared. The engine takes
the friction signature's coordinates, the deployment's bank policy, the
public regulatory taxonomy, and (if available) the Chronicle precedent
library, and emits one of four closed tier-words: `NOMINAL`, `WATCH`,
`ESCALATE`, `REGULATORY-FLAG`.

The Pulse Design Direction lock (2026-05-17) places Risk and Value as the
two computed axes of a CLARK-style 2×2; the load-bearing cell is
`REGULATORY-FLAG` (high risk, low value — "not just a value question").
This methodology paper covers the Risk axis only; Value lives in a peer
methodology (PULSE-101).

## Why Risk is computed not declared

Two reasons.

**Reproducibility.** A pack author declaring `risk: high` and shipping
that declaration into a decision pack is unauditable: there is no path
from the assertion back to the inputs that supported it. A computed Risk
score with `methodology_version` and `inputs_hash` pinned in the output
lets any auditor reproduce or contest the score with the same
methodology bytes.

**Per-deployment relevance.** Different banks commit to different
escalation thresholds (`bank_policy.yaml`) and operate under partially
different regulatory perimeters. A declared Risk tier from a pack author
would assume one bank's posture; a computed Risk tier respects each
deployment's commitments.

## Inputs

The scorer takes four input groups:

1. **FrictionShape** — `signature_id`, `journey_category`, `screen_class`,
   `severity` (`P0` / `P1` / `P2`). The pack already carries these via
   `hypothesis.yaml`.

2. **ImpactMetrics** — `affected_customers_7d` (integer count detected
   in a rolling 7-day window) and `vulnerable_cohort_overrep_ratio`
   (cohort harm rate / baseline harm rate). The engine measures these.

3. **bank_policy** — the parsed
   [`pulse/contracts/bank_policy.yaml`](../contracts/bank_policy.yaml).
   Per-deployment escalation thresholds. Pulse ships no defaults; the
   bank commits to numbers explicitly.

4. **chronicle_library** *(optional, soft dependency)* — the parsed
   [`pulse/risk/chronicle/`](./chronicle/) library. Risk methodology
   consumes only `verification_status: verified` entries (the matcher
   fails closed on pending-review entries).

## Computation

Tier is computed as `min(REGULATORY-FLAG, base_tier + Σ adjustments)`.

`base_tier` is a function of severity per
[`rubric.yaml`](./rubric.yaml):

| Severity | Base tier (numeric) | Base tier-word |
|---|---|---|
| P0 | 2 | ESCALATE |
| P1 | 1 | WATCH |
| P2 | 0 | NOMINAL |

Adjustments stack — each adds `+1` and the total is clamped at the
top tier:

| Adjustment | Fires when |
|---|---|
| `regulatory_match` | a `regulatory_taxonomy.yaml` entry matches the shape's `(journey_category, screen_class)` |
| `affected_customers_threshold` | `impact.affected_customers_7d ≥ bank_policy.escalation_thresholds.affected_customers_7d_window` |
| `vulnerable_cohort_overrep` | `impact.vulnerable_cohort_overrep_ratio ≥ bank_policy.escalation_thresholds.vulnerable_cohort_overrep_floor` |
| `chronicle_precedent_match` | ≥1 **verified** Chronicle entry matches `(signature_id × screen_class × severity)` |

Adjustments are **monotonic** — they only push the tier up. Risk is
precautionary; "the bank set a stricter floor" is never a reason to
de-escalate.

## Output

`RiskScore` (frozen dataclass) carries:
- `tier` (closed enum tier-word)
- `numeric_tier` (0..3 underlying integer)
- `base_tier` (severity-derived starting point, for diff explanation)
- `adjustments_applied` (which rubric keys fired)
- `regulatory_matches` (the matched taxonomy codes)
- `chronicle_matches` (the matched verified Chronicle entry IDs)
- `methodology_version` (pinned from rubric.yaml)
- `inputs_hash` (SHA-256 over the deployment-affecting inputs)

The audit footprint (`methodology_version` + `inputs_hash`) is what
makes the score reproducible. Any consumer can re-run `score_risk()`
with the same methodology bytes and same inputs and assert the same
tier landed.

## Things this methodology deliberately does NOT do

- **No tier reduction** — `bank_policy.yaml` cannot opt a deployment
  out of a tier the engine computed. A bank that disagrees with a
  score can escalate to governance review; it cannot silently lower
  the tier in its own deployment config.
- **No LLM inference** — v1 is non-LLM runtime per the architectural
  lock. Tier computation is deterministic arithmetic over closed
  enums + thresholds.
- **No pack-author override** — packs declare the friction shape; the
  engine owns the tier. A pack that declares its own `risk_tier`
  field would be ignored by `score_risk()`.
- **No fairness-method substitution** — fairness gating happens inside
  the pack's analytic layer (`hypothesis.yaml`) and feeds the cohort
  over-representation metric this scorer consumes; the scorer does
  not re-derive fairness.

## Versioning

The `methodology_version` in [`rubric.yaml`](./rubric.yaml) bumps on:

- any change to `tier_words` (adding / removing / renaming tiers)
- any change to `base_tier_by_severity` mappings
- any change to adjustment keys or `delta` values
- adding or removing a `regulatory_taxonomy.yaml` entry

Decision packs pin `required_pulse_version` in their metadata —
methodology-version changes will surface as compatibility failures at
load time, by design.

## Why CASP-style "publish before scoring"

CASP (Critical Assessment of Protein Structure Prediction) publishes
its assessment criteria before each round so submissions know exactly
what they are being judged on. Pulse adopts the same discipline for
Risk: this document, the rubric YAML, and the regulatory taxonomy YAML
all ship under Apache-2.0 and are intentionally legible. A bank
disputing a tier can read the methodology and contest the inputs; it
cannot reverse-engineer a black box.

## v0.1 acknowledged limits

- **Linear adjustment stack** — adjustments add independently rather
  than interacting. v0.2 will revisit if real deployments produce
  patterns that need (e.g.) "regulatory_match AND
  vulnerable_cohort_overrep together should push to REGULATORY-FLAG
  even from a P1 base." For v0.1 the linear rule has the virtue of
  being trivially auditable.
- **No incident-recency weighting on Chronicle matches** — a 2014
  Chronicle precedent adjusts the tier exactly as much as a 2025 one.
  Future versions may weight by `incident_year` / `year` recency.
- **Single-jurisdiction taxonomy at v0** — `regulatory_taxonomy.yaml`
  is UK + EU focused at v0. US, APAC, EMEA-ex-EU taxonomies are
  additive (no methodology-version change required for adding new
  entries; required only for restructuring the taxonomy schema).

[PULSE-99]: https://cjipro.atlassian.net/browse/PULSE-99
