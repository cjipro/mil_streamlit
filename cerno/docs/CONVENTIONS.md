# Cerno — Conventions

Live snapshot of patterns + primitive locations + parameter values.
Rewritten as decisions land or patterns stabilise. NOT append-only —
use [`DECISIONS.md`](decisions/DECISIONS.md) for the history.

## Runtime

- **Python:** 3.11.x (locked; see [D-001](decisions/DECISIONS.md))
- **CPU only.** No GPU paths. No `accelerate`.
- **Approved libs:** duckdb, pyarrow, numpy, scikit-learn, statsmodels,
  pyspark (2.4.0 — see [D-006](decisions/DECISIONS.md)), pyodbc,
  pandas, scipy, PyYAML, joblib + stdlib.
- **Banned at import time:** torch, transformers, sentence_transformers,
  openai, anthropic. Enforced by `cerno.safety.assert_safe`.
- **No network calls.** No `pip install` at runtime — bank env has libs
  pre-installed.

## Bindings

Source column names are bound at runtime per [D-001](decisions/DECISIONS.md).
Generic placeholders only in committed code:

```
[identity_col] [timestamp_col] [opcode_col] [status_col]
[success_sentinel] [payload_col] [parquet_path]
```

Operator binds via `Settings.from_yaml(path)` or `Settings.from_env()`.
Env vars use `CERNO_<UPPERCASE_FIELD>` convention. `validate()` raises
loudly if placeholders remain.

Current parameter defaults:
- `idle_threshold_min = 30` (re-calibrate at Step 2 §3 against
  session-gap percentiles)
- `dwell_cap_s = 300` (struggle-signal cap; raw dwell kept too)

## Primitives

Each module is one file under `src/cerno/`:

| Module | Public API | Purpose |
|---|---|---|
| `safety` | `assert_safe()`, `BANNED`, `SafetyViolation` | Import-time banned-imports gate |
| `settings` | `Settings`, `Settings.from_env`, `from_yaml`, `validate`, `ensure_dirs` | Bindings + parameters |
| `run_id` | `make_run_id(date, params)` | Deterministic run identifiers |
| `logging` | `get_logger(name, run_id)` | Structured logger bound to run_id |
| `db` | `connect(path=None)` | DuckDB connection factory |
| `spark` | `get_spark(app_name)`, `stop(session)` | SparkSession factory (2.4.0-safe) |
| `manifest` | `Manifest`, `write_manifest`, `read_manifest`, `verify_manifest` | `_MANIFEST.json` schema + IO |
| `lineage` | `chain_id(prev, this)`, `verify_chain(manifests)` | Hash chain across manifests |
| `io` | `write_parquet(...)`, `read_parquet_with_manifest(in_dir)` | Parquet IO with manifest emit + idempotency |

## Patterns

1. **Bindings at top of every script.** File paths, column names,
   sentinel values declared as top-of-file constants the operator
   fills in. Body never hardcodes them inline.
2. **Manifest on every write.** Every transform that writes Parquet
   emits a `_MANIFEST.json` next to the output. Snapshot_id strategy:
   sorted natural-key sha256, first 16 hex (see
   [D-003](decisions/DECISIONS.md)).
3. **Idempotent on the date dimension.** Re-runs reproduce. `write_parquet`
   skips when an existing manifest matches the snapshot_id we would
   write. Safe for overnight automation.
4. **Sequence ordering rule.** Order events within a session by
   `sequence_no` when present, NOT by event timestamp. Network
   delivery may reorder events with identical timestamps. If the
   source has no sequence column, fall back to timestamp BUT flag in
   the manifest as a known limitation.
5. **Sanitisation rule for findings docs.** Sanitised aggregates only —
   never raw rows or identifiers. The findings log is auditable,
   public-grade content.
6. **-ERROR sentinel.** Errors decorate `event_string` tokens as
   `(CODE-ERROR)`. Filter cheaply with `WHERE event_string LIKE
   '%-ERROR%'`. Count cheaply with substring-count pattern.
7. **Lineage chains via `source_snapshot_id`.** Every manifest carries
   `source_snapshot_id` pointing at the previous layer's snapshot_id.
   `verify_chain` walks the list and reports breaks.

## Engine-per-stage

| Stage | Engine | Rationale |
|---|---|---|
| Extract (source → MA_D) | pyodbc / PySpark / DuckDB (depending on source) | Source-driven; bounded output is Parquet |
| Sessionise (MA_D → MA_S) | PySpark | MA_D is at scale (tens of billions); needs distributed |
| MA_S analysis (validation, features, transitions, hazard, prioritisation) | DuckDB | Embedded, fast, no cluster required, consistent across analyst machines |
| Serving (MA_S → external consumers) | DuckDB read layer behind FastAPI | Cache MA_S on first access, warm in-memory view |

## Memory discipline

Three files carry state across sessions:
- [`STATE.md`](../STATE.md) — paste at session start
- [`docs/decisions/DECISIONS.md`](decisions/DECISIONS.md) — append-only
  decision log
- [`docs/CONVENTIONS.md`](CONVENTIONS.md) — this file

The agent emits `Decision to log:` blocks for load-bearing decisions
and `Findings to capture:` blocks for analytical observations. The
operator appends to the right file.
