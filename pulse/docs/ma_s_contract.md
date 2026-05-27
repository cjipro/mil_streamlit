# MA_S Contract — Sessionised Journey Strings + Friction Scoring

**Ticket:** PULSE-142. **Status:** design + contract (sanitised). **Scope:** Pulse engine.

Sanitised engine design — **generic placeholders only, no real-source identifiers.**
Real-source column bindings live outside this repo and are never committed here.

## Purpose

Behavioural event log → sessionised journey strings (**MA_S**) → friction features →
**friction × reach** prioritisation → **agentic candidates**
(the chain: friction → demand failure → chat-AI / Lever introduction).

## Source event shape (generic)

Each row = **one operation invocation with a response code**. Generic columns, bound per source:

| Placeholder | Meaning |
|---|---|
| `[identity]` | session/identity key — the sessionisation partition key |
| `[timestamp]` | event time |
| `[opcode]` | operation identity |
| `[status]` | response/status code — one **success sentinel** value; all others = error |
| `[payload]` | distinguishes API calls (carry an **alias/handle**) from screen operations |

## Op 1 — Sessionise (events → MA_S)

- Partition by `[identity]` → order by `[timestamp]` → split on **idle gap** (default 30 min, parameterised).
- **Dwell** = `LEAD([timestamp]) − [timestamp]`; **terminal dwell censored** (never 0); cap 300s.
- **Per-event token:** base = alias-if-API (from `[payload]`) else `[opcode]`; decorate `(CODE-ERROR)` iff `[status] != success_sentinel`; append `[dwell]`. The literal `-ERROR` is a SQL sentinel.
- **`event_string`** = the ordered token sequence = **source of truth** (transition-model tokens + hazard dwell + SQL pattern search via the `-ERROR` sentinel).
- **Calculated metrics = typed COLUMNS** (not embedded in the string):
  `n_ops, n_errors, duration_s, max_dwell_s, retries, end_op, error_rate,
  time_to_first_error_s, position_of_first_error, had_error_loop, cascade_flag, outcome`
  + LIST columns `error_ops[]`, `error_idx[]`, `error_codes[]`.
- Single-event **bounce** sessions flagged as a distinct shape.

## Op 2 — Feature translation (taxonomy lookup; identity-independent)

- **`Event_String_Sequence`** — translated to readable names, ordered, **errors kept** (visual + variant view).
- **`Event_String_Set`** — dedup + alphabetical, **errors kept** (aggregation fingerprint).

## Op 3 — Identity resolve

`[identity] → customer_id` (separate, gated, re-runnable; adds `customer_id`).

## Op 4 — Attribute enrich

`customer_id → cohort / demographics / value-bucket-later` (customer-grain join; supplies value + fairness axes).

## Modeling — per outcome lens

Shared raw substrate; **per-lens target + feature engineering + leakage boundary**
(a metric that's a target in one lens is a feature in another).

- **Transition (Markov):** two grains (op-code = localisation, feature = flow/cascade); absorbing states → fundamental matrix `N=(I−Q)⁻¹` → `P(abandon | at X)`, expected steps. Re-solved per outcome.
- **Hazard (survival):** Cox / Kaplan-Meier (statsmodels); right-censoring; hazard ratios; C-index; Schoenfeld PH test.
- **Regression:** LR spine + HistGradientBoosting challenger; grouped-by-customer CV (`StratifiedGroupKFold`); PR-AUC / recall@precision; calibration.

## Prioritisation

- **`Priority = Friction × Reach`** (multiply, not add/avg). Reach = distinct customers, **set-union across lenses**.
- **2×2 quadrant policy:** Q2 HF/HV → prioritise (agentic candidates) · Q1 HV/LF → monitor + benchmark · Q3 HF/LV → effort-gate (RICE) + severity/fairness floor · Q4 LF/LV → diagnose (great UX? niche? blind spot) + model FP/specificity check.
- CLARK-tiered; **agentic candidate = weak-link ∩ agentic-addressable**.
- Gates: `min_sample_size` + CIs + fairness lens before any claim.

## Segmentation (deferred)

- **MVP = session grain, single-journey scope, no intent segmentation.**
- Re-entry gated on a **per-journey boundary-marker registry** (entry op + completion op + cancel op per journey; mined + domain-validated). Method when unblocked: **outcome-anchoring + detour detection**, validated against the synthetic generator's ground-truth boundaries.

## Runtime

Python 3.11, **CPU-only**; DuckDB + PyArrow + numpy + scikit-learn + statsmodels; classical + deterministic; **no LLM at runtime**.

## Relationship to the committed engine

The committed `pulse/` pipeline is **screen-based** (`screen_id` + `event_type`) with **aggregate-only MA_S**; this contract specifies the **op-code / response-code + `event_string`** model — a rebuild against bank reality. Reuses proven `pulse/` patterns:
- DuckDB sessionise (**ORDER BY `sequence_no`**, not `event_ts`),
- robust per-screen dwell baseline (median + MAD × 1.4826),
- the classical detectors (dwell z-score, back-press burst, terminal abandonment),
- lineage / fairness / decision scaffolding for the later phases.
