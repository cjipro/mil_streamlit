# Agentic AI placement — worked end-to-end example

Filed under [PULSE-106]. First end-to-end product demonstration of the
v0 Pulse engine spine.

## The question

The bank is moving from "digital assistant" to "AI assistant" (Agentic
AI chat). **Which app journeys should this be deployed on?** Resources
are finite, regulatory exposure varies by journey, and not every
journey is an AI-deployable problem in the first place — some need a
journey fix, not a support-layer intervention.

## The engine pipeline

The scenario exercises the v0 engine spine end-to-end:

```
1. Diagnosis  (PULSE-105)  →  is this an AI-deployable problem at all?
2. Risk       (PULSE-99)   →  how exposed if we deploy or don't?
3. Value      (PULSE-101)  →  how big is the prize if we deploy correctly?
4. Action tier             →  CLARK-style placement recommendation
```

Diagnosis is the gate. An `INCONCLUSIVE` diagnosis (small no-assistance
control arm) short-circuits to `NEEDS_MORE_DATA` regardless of how
appealing the Risk × Value cell looks. A `JOURNEY_PROBLEM` diagnosis
overrides any high-value placement signal — the recommendation becomes
"fix the journey itself; AI assistance is symptomatic relief."

`SUPPORT_PROBLEM` and `BOTH` allow the Risk × Value 2×2 to drive the
placement modifier (deploy with guardrails / don't deploy / deploy first
/ not worth deploying / monitor).

## CLARK-style Action tier composition

The Value × Risk 2×2 maps to a placement decision per
[the canvas-as-discipline lock](../../../CLAUDE.md):

| Risk \ Value | NOMINAL / WATCH | SIGNIFICANT / COMMERCIAL-OPPORTUNITY |
|---|---|---|
| NOMINAL / WATCH | `NOMINAL` / `WATCH` | `COMMERCIAL-OPPORTUNITY` — deploy first |
| ESCALATE / REGULATORY-FLAG | `REGULATORY-FLAG` — don't deploy | `ACUTE` — deploy with heavy guardrails |

Diagnosis overrides:
- `INCONCLUSIVE` → `NEEDS_MORE_DATA` (regardless of 2×2)
- `JOURNEY_PROBLEM` / `BOTH` → "fix journey first" verb (Action tier still
  reported as the modifier)

## Inputs

[`scenario.yaml`](./scenario.yaml) declares 12 cells — 4 journeys ×
3 signatures, drawn from the seed-batch decision packs (PULSE-104).
Each cell carries:
- diagnosis inputs (two arms: assistance-using, no-assistance control)
- risk impact metrics
- value metrics

Numbers are illustrative fixtures, chosen to exercise every cell of
the placement matrix (every combination of Diagnosis × Action tier)
so the worked example demonstrates the full output space.

A shared `bank_policy` block at the top sets the deployment-level
escalation thresholds — the same `affected_customers_7d_window` (500)
escalates both Risk and Value adjustments, per the cross-axis
consistency baked into the v0 methodologies.

## Running

```bash
py -m pulse.scenarios.agentic_ai_placement.run
```

Prints the Markdown placement matrix to stdout. Suitable for screenshot,
paste into a briefing, or feed into the HOL-11 briefing-surface render.

## Audit footprint

The matrix carries methodology versions for all three engines
(Diagnosis / Risk / Value). Per-cell, every score's `inputs_hash` is
reproducible — same scenario.yaml input always produces the same matrix
output. A test asserts this determinism end-to-end.

## What this proves

This is the first end-to-end demonstration that the v0 engine spine
composes into a real product answer. Specifically:

- the v2 methodologies (Diagnosis + Risk + Value) actually compose
  cleanly into a single placement matrix without ad-hoc glue
- the bank_policy contract works as the shared thresholds anchor
- the canvas-completeness schema (PULSE-103) declarations in the seed
  packs surface the right severity / vulnerable_cohort / regulatory
  signals for the methodologies to consume
- the Diagnosis-overrides-Risk/Value-2×2 composition rule produces
  product-meaningful recommendations (not just tier-words)

It's also the artefact to walk internal stakeholders through when the
question is "what does Pulse actually do?"

[PULSE-106]: https://cjipro.atlassian.net/browse/PULSE-106
