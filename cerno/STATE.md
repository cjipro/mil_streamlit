# Cerno — STATE

> Session-priming pager. Paste the content of this file at the start of
> every new Cerno Assistant chat. ~200 words. Updated whenever something
> material moves.

## Phase

**Step 1 — Scaffolding · Phase 4 complete.**
Engineering substrate + memory layer landed. Next: Phase 5 (smoke) —
end-to-end run of the primitives, manifest verify, lineage chain, doctor
green, all tests green. After Phase 5 green: **Step 2 — Recon /
Sessionisation** on a bounded extract.

## Latest decisions

- [D-007](docs/decisions/DECISIONS.md) — PySpark 2.4 + Python 3.11 incompat (FINDING; bank-edge versions to confirm)
- [D-006](docs/decisions/DECISIONS.md) — PySpark 2.4.0 compatibility (struct min/max not arg_min/arg_max)
- [D-005](docs/decisions/DECISIONS.md) — Memory layer locations: STATE / decisions / CONVENTIONS
- [D-004](docs/decisions/DECISIONS.md) — Makefile + plain script entrypoints (both)
- [D-003](docs/decisions/DECISIONS.md) — `snapshot_id` = sorted natural-key sha256 (first 16 hex)

## Latest findings

- [2026-05-30](docs/findings/2026-05-30.md) — `pyspark==2.4` cannot import on Python 3.11 in a clean install (vendored cloudpickle pre-3.11). Bank-edge `pip list` dump needed to resolve. Triggered D-007.

## Open questions

- **D-007 resolution** — confirm bank-edge actual Python + pyspark versions on next session at work; pick one of (a) Python ≤3.10, (b) patched pyspark in internal artifactory, (c) pyspark 3.x with stale 2.4 doc entry.
- Source connector for the bounded extract — pyodbc, PySpark, or ACE
  Spark client. Resolved when the operator picks the source on Step 2.
- Error-code table (`taq_error_codes.csv`) — pending Hussain.
- Calibration of `idle_threshold_min` against real session-gap
  distribution — happens in Step 2 §3 (recon validation profile).

## Next step

Run Phase 5 smoke. When green, ship the Step 2 recon page and start the
analytical work on the bounded extract.
