# MA_S Contract — Sessionised Journey Strings + Friction Scoring

**Ticket:** PULSE-142. **Status:** design + contract (sanitised). **Scope:** Pulse engine.

Sanitised engine design — **generic placeholders only, no real-source identifiers.**
Real-source column bindings live outside this repo and are never committed here.

## Purpose

Behavioural event log → sessionised journey strings (**MA_S**) → friction features →
**friction × reach** prioritisation → **agentic candidates**
(the chain: friction → demand failure → chat-AI / Lever introduction).

## Data layers

- **MA_D** — the **raw event log**. One row per atomic event (one operation invocation + its response code). Produced from the source by the bounded-extract step. Scale: potentially tens of billions of rows.
- **MA_S** — the **sessionised view, derived from MA_D** by Op 1 (sessionise). One row per session. Carries the `event_string` + typed metric columns + LIST columns. The primary working layer for downstream analysis.

Subsequent layers (op-code/feature lookup, customer attributes) join onto MA_S. MA_D is not re-read once MA_S is built, except for re-derivation / lineage verification.

## Source event shape (generic)

Each row = **one operation invocation with a response code**. Generic columns, bound per source:

| Placeholder | Meaning |
|---|---|
| `[identity]` | session/identity key — the sessionisation partition key |
| `[timestamp]` | event time |
| `[opcode]` | operation identity |
| `[status]` | response/status code — one **success sentinel** value; all others = error |
| `[payload]` | distinguishes API calls (carry an **alias/handle**) from screen operations |

## Op 1 — Sessionise (MA_D → MA_S)

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

## Error analysis

Errors are a primary analytical signal. Throughout the pipeline:

- **Detected:** `[status] ≠ success_sentinel`.
- **Decorated** inline in `event_string` as `(CODE-ERROR)` (CODE = the actual response code). The `-ERROR` suffix is a SQL sentinel so error-bearing sessions filter cheaply (`WHERE event_string LIKE '%-ERROR%'`) and errors count cheaply (substring count of `-ERROR`).
- **Aggregated** on the MA_S row as columns: `n_errors, error_rate, error_ops[], error_codes[], error_idx[], had_error_loop, cascade_flag, time_to_first_error_s, position_of_first_error`.

Analytical questions: top error codes by frequency; op-code × error-code matrix; error loops (repeated identical failure on same op); error cascades (≥2 distinct error-bearing op-codes per session); error → downstream-outcome attribution (which errors precede a call within 60 min / a chat-failed / a low-NPS / an abandonment); error rates per cohort (fairness lens); recovery vs abandonment after an error.

Error analysis feeds: the Risk axis of friction scoring; the Friction × Reach matrix (errors-driving-calls are the highest-yield agentic territory); the Markov + hazard layers (error transitions, post-error hazard).

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

## Runtime stack by stage

| Stage | Engine | Why |
|---|---|---|
| **Extract** (source → MA_D) | pyodbc / pyspark / DuckDB (depending on source) | Match the connector to where the source lives |
| **Sessionise** (MA_D → MA_S) | **PySpark** | MA_D is at scale (potentially tens of billions of rows) — distributed processing required |
| **All MA_S-layer analysis** (validation, features, scoring, prioritisation) | **DuckDB** | MA_S fits in DuckDB's columnar working set; ergonomic for analytical SQL |
| **Serving** (MA_S → FastAPI → Holter) | **DuckDB** | Cache MA_S on first access (`CREATE OR REPLACE TABLE ma_s_cached AS …`) so repeated UI queries hit a warm view |

General constraints: **Python 3.11, CPU-only**; approved libraries only (`duckdb, pyarrow, numpy, scikit-learn, statsmodels, pyspark, pyodbc, stdlib`); no network calls, no pip installs, no external services; **no LLM at runtime** — classical ML + statistics only. Procurement-passable for a regulated UK bank.

**Overnight automation opportunity:** once the sessionise job is stable, scheduling it as a nightly pipeline refreshes MA_S without manual intervention. Design scripts to support this — **idempotent on the date dimension**, parameterised by date range, emit a manifest + run-id for lineage.

## Relationship to the committed engine

The committed `pulse/` pipeline is **screen-based** (`screen_id` + `event_type`) with **aggregate-only MA_S**; this contract specifies the **op-code / response-code + `event_string`** model — a rebuild against bank reality. Reuses proven `pulse/` patterns:
- DuckDB sessionise (**ORDER BY `sequence_no`**, not `event_ts`),
- robust per-screen dwell baseline (median + MAD × 1.4826),
- the classical detectors (dwell z-score, back-press burst, terminal abandonment),
- lineage / fairness / decision scaffolding for the later phases.
