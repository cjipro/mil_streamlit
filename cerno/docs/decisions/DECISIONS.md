# Decision Log

Append-only. Latest entry on TOP. When a decision is superseded, add a
new entry that explicitly references the old; flip the old entry's
status to `superseded` (no other edits to historical entries).

For the entry template see [TEMPLATE.md](TEMPLATE.md).

---

## D-007 — 2026-05-30 — PySpark 2.4 + Python 3.11 incompatibility (FINDING)
**Status:** accepted
**Context:** Replica build on a Windows dev box (conda env, Python 3.11.15 + Java 8 + all bank-edge lib pins). `pyspark==2.4` installs cleanly via conda-forge but fails to **import**: its vendored `cloudpickle.py` calls `types.CodeType(...)` with a pre-Python-3.11 signature (`TypeError: code expected at least 16 arguments, got 15`). Python 3.11 added `qualname` and the exception table to the `CodeType` signature; pyspark 2.4 never got the patch.
**Decision:** The "Python 3.11 + pyspark 2.4.0" combination documented in `APPROVED_LIBRARIES.md` cannot work as advertised in a clean install. **Action:** confirm against the actual bank edge node what's really running — three plausible answers: (a) Python ≤3.10 (and the 3.11 lock is aspirational/wrong), (b) a patched pyspark 2.4 in an internal artifactory, (c) pyspark 3.x with the 2.4 entry being stale. Until confirmed, local Spark smoke uses **pyspark 3.5.x on Python 3.11 + Java 8** (works) with the version gap documented; bank-edge Step 2 sessionise code targets the actually-installed version.
**Consequences:** `cerno.spark` is lazy-imported, so the 45/45 cerno test suite is unaffected. Any local Spark smoke (e.g. a future `tests/test_spark.py`) must use pyspark 3.5.x or skip if pyspark unavailable. Open: revisit this entry once the bank-edge `pip list` dump is in hand; if the answer is (b) — patched cloudpickle — D-007 supersedes itself with a "use the internal artifactory" entry.
**Implemented by:**
  - docs/findings/2026-05-30.md — the finding write-up
  - SCAFFOLDING.md — notes the constraint
  - cerno/spark.py — lazy import insulates the test suite
**Supersedes:** none

## D-006 — 2026-05-30 — PySpark 2.4.0 compatibility
**Status:** accepted
**Context:** The bank edge node runs PySpark 2.4.0 (per APPROVED_LIBRARIES.md). Newer Spark-3 idioms (`arg_min`, `arg_max`, Adaptive Query Execution) would silently break on the edge.
**Decision:** Any Spark code under `cerno.spark` and downstream sessionise jobs targets PySpark 2.4.0 syntax. Use `struct(value, sort_key)` min/max patterns where 3.x would use `arg_min`/`arg_max`. Lazy-import `pyspark` so missing-JVM environments don't break unrelated tests.
**Consequences:** Tests that need a SparkSession are skip-aware. Sessionise SQL is written in 2.4.0-safe form. No AQE-dependent optimisations.
**Implemented by:**
  - src/cerno/spark.py::get_spark
  - src/cerno/spark.py::stop
**Supersedes:** none

## D-005 — 2026-05-30 — Memory layer file locations
**Status:** accepted
**Context:** Need a deterministic place for STATE.md, DECISIONS.md, CONVENTIONS.md so the parser test can find them and so the Cerno Assistant agent has a stable mental model of where to write decisions.
**Decision:** STATE.md lives at the repo root (single-file, paste-at-session-start). DECISIONS.md + TEMPLATE.md live in `docs/decisions/`. CONVENTIONS.md lives in `docs/`. Findings live in `docs/findings/` (per-day files) with README + TEMPLATE alongside.
**Consequences:** `test_memory_files.py` parses these paths. CONVENTIONS.md may be uploaded to the agent as a Knowledge file once stable.
**Implemented by:**
  - STATE.md
  - docs/decisions/DECISIONS.md
  - docs/decisions/TEMPLATE.md
  - docs/CONVENTIONS.md
  - docs/findings/README.md
  - tests/test_memory_files.py
**Supersedes:** none

## D-004 — 2026-05-30 — Makefile + plain script entrypoints (both)
**Status:** accepted
**Context:** Some operators prefer `make doctor`; others run `python scripts/doctor.py` directly. Forcing `make` excludes the latter; only shipping scripts loses the named workflow.
**Decision:** Ship both. The Makefile is a thin wrapper over the same commands an operator would type by hand. `make doctor` and `python scripts/doctor.py` are interchangeable.
**Consequences:** Documentation lists both forms. CI uses `python -m pytest` directly (no make dependency in CI).
**Implemented by:**
  - Makefile
  - scripts/doctor.py
**Supersedes:** none

## D-003 — 2026-05-30 — snapshot_id strategy
**Status:** accepted
**Context:** Idempotency requires comparing today's planned output to yesterday's persisted output without re-running the full transform. File-content hash depends on parquet writer determinism (not guaranteed across versions). Row-content hash is stable and writer-independent.
**Decision:** `snapshot_id` = first 16 hex chars of sha256 over the sorted per-row JSON representation of the table. Stable across machines, writer versions, and re-runs.
**Consequences:** `write_parquet` recomputes the snapshot on every call, checks the existing manifest, and skips the write if it matches. Verify also reads the manifest snapshot, not file bytes. Cost: O(n) hash per write — acceptable; layer writes are bounded.
**Implemented by:**
  - src/cerno/io.py::_content_snapshot
  - src/cerno/io.py::write_parquet
  - tests/test_io.py::test_idempotent_skip_on_identical_content
  - tests/test_io.py::test_content_snapshot_is_deterministic
**Supersedes:** none

## D-002 — 2026-05-30 — Safety enforcement at import-time + CI
**Status:** accepted
**Context:** Cerno's architectural lock is "no LLM / DL in the runtime path". Need to make violations LOUD and EARLY. Single-layer enforcement (only at import) misses CI-introduced regressions; CI-only enforcement misses local-dev mistakes.
**Decision:** Defence in depth. `cerno/__init__.py` calls `assert_safe()` at import. `.gitlab-ci.yml` runs a dedicated `safety` job that imports cerno in a clean Python env. Banned list lives in `safety.py::BANNED` as the single source of truth for both layers.
**Consequences:** Failed safety check is hard ImportError (not warning). CI fails on banned-import regression. Outbound HTTP libs (requests/httpx/urllib3) are NOT in the import-time gate (transient test-runner pollution false-positives); they're guarded via CI no-network rules.
**Implemented by:**
  - src/cerno/__init__.py
  - src/cerno/safety.py::assert_safe
  - src/cerno/safety.py::BANNED
  - .gitlab-ci.yml::safety
  - tests/test_safety.py
**Supersedes:** none

## D-001 — 2026-05-30 — Bindings via env + YAML (both)
**Status:** accepted
**Context:** Source column names are bank-specific and must NEVER land in committed code. Operators need a way to bind them at runtime. Env vars are convenient for ad-hoc runs; YAML is auditable and reproducible for scheduled jobs.
**Decision:** `Settings.from_env()` and `Settings.from_yaml(path)` are both first-class classmethods. The class has placeholder defaults (`[identity_col]` etc.) so unset bindings fail validation loudly. `validate()` is called explicitly by the consumer; loaders don't validate automatically (the operator may legitimately load partial settings during exploration).
**Consequences:** Two loader paths to test. Unknown YAML keys raise (catches typos). Env vars use `CERNO_<UPPERCASE_FIELD>` convention.
**Implemented by:**
  - src/cerno/settings.py::Settings.from_env
  - src/cerno/settings.py::Settings.from_yaml
  - src/cerno/settings.py::Settings.validate
  - tests/test_settings.py
**Supersedes:** none
