# Cerno — Scaffolding

What got built in Step 1, and why each architectural call was made.
Cross-references decisions in
[`docs/decisions/DECISIONS.md`](docs/decisions/DECISIONS.md).

## Phase 1 — Repo bones

Standard Python project skeleton. `pyproject.toml` documents
dependencies but does NOT drive install (the bank edge node has libs
pre-installed). `Makefile` is a thin convenience over scripts that work
standalone (D-004). `.gitlab-ci.yml` runs lint + tests + safety as a
3-stage pipeline.

## Phase 2 — Safety + Settings + Run_id + Logging

The four cross-cutting primitives every downstream module depends on:

- **`safety.py`** — Import-time gate that refuses to load cerno if any
  banned deep-learning / LLM library is present in `sys.modules`. Single
  source of truth for the banned list (D-002).
- **`settings.py`** — Bindings layer. Loads from env or YAML (D-001).
  Carries source column placeholders, sessionise parameters, layer
  paths. `validate()` raises on unbound placeholders.
- **`run_id.py`** — Deterministic run identifiers. Format
  `YYYY-MM-DD-XXXXXXXX` where `XXXXXXXX` is first 8 hex of sha256 over
  sorted params. Anchors manifest idempotency.
- **`logging.py`** — Structured logger with run_id bound to every
  record. Idempotent on handler attachment.

## Phase 3 — Data layer

The primitives that turn the runtime into a working data engine:

- **`db.py`** — DuckDB connection factory. In-memory or file-backed;
  threads pragma set from CPU count.
- **`spark.py`** — SparkSession factory. PySpark 2.4.0-targeted
  (D-006). Lazy-imports pyspark so missing JVMs don't break unrelated
  tests.
- **`manifest.py`** — `Manifest` dataclass + `write_manifest` /
  `read_manifest` / `verify_manifest`. Schema version 1.0.
- **`lineage.py`** — `chain_id` (sha256 of `prev||this`) +
  `verify_chain` (walks manifests, reports broken links).
- **`io.py`** — `write_parquet` with content snapshot_id (D-003) +
  idempotent skip + manifest emit. The load-bearing primitive every
  layer-writing call funnels through.

## Phase 4 — Doctor + Memory layer

The runtime sanity checker + the cross-session memory layer (D-005):

- **`scripts/doctor.py`** — Preflight: Python version, lib imports,
  dir write access, safety gate clean. Exits 0 on green, 1 on red.
- **`STATE.md`** — Session-priming pager at repo root. Paste at the
  start of every Cerno Assistant chat.
- **`docs/decisions/DECISIONS.md`** — Append-only decision log. D-001
  through D-006 seeded with the locks from Phases 1–3.
- **`docs/decisions/TEMPLATE.md`** — Entry template.
- **`docs/CONVENTIONS.md`** — Live snapshot of patterns + primitive
  locations + parameter values.
- **`docs/findings/README.md`** + `TEMPLATE.md` — Working memory of
  analytical observations (lands during Step 2).
- **`tests/test_memory_files.py`** — Parser-level checks that
  STATE.md / DECISIONS.md / CONVENTIONS.md hold their required
  structure.

## What's NOT here

By design — these come in Step 2+, not scaffolding:

- The bounded extract step (source-specific; operator binds locally).
- The PySpark sessionise job (Stage A of the analysis plan).
- The DuckDB validation profile (Step 2 §3 recon).
- Markov / hazard / regression modelling (Stages E–F).
- The Friction × Reach prioritisation matrix (Stage H).
- Synthetic data generators (this is the in-bank deployment; synthetic
  belongs in the OSS Pulse engine, not in Cerno).
