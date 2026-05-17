# Pulse lineage chain — design

**Filed under PULSE-89.**

## Purpose

Every artifact Pulse produces — an inference, a synthesis output, a published
finding — must be re-derivable from the inputs it claims. This file is the
substrate that makes "re-derivable" provable.

## Audit boundary

Per Hamel's panel point (echoing Stripe's payment-data lineage approach):
**we do not re-derive lineage backwards into the bank's source systems.**
Lineage starts at the moment data enters the Pulse perimeter. The ingest
stamp on each canonical event (PULSE-87) is the audit boundary.

```
[Bank source systems]   ──┐
                          │  (no lineage from here back — opaque)
                          ▼
                    [adapter ingest]   ←── audit boundary starts HERE
                          │
                          ▼
              [canonical event with envelope]
                          │
                          ▼
                [lineage row: operation=ingest]
```

## Row shape

See `schema.yaml` for the authoritative definition. Every row carries:

- `lineage_id` — UUID, foreign key from artifact records
- `ts` — UTC ms when the operation completed
- `operation` — `ingest | analyse | synthesise | publish`
- `inputs` — list of upstream `lineage_id`s (empty for `ingest`)
- `artifact_hash` — SHA-256 of the canonical-encoded artifact produced
- `pipeline_version` / `decision_pack_version` / `template_version` — semver stamps
- `config_hash` — SHA-256 of the config snapshot active at row time
- `prev_row_hash` — `row_hash` of prior row, or literal `"genesis"` for the first
- `row_hash` — `SHA256(canonical_json(hashed_columns) + "|" + prev_row_hash)`

## Hash chain guarantees

- **Append-only.** Writers never rewrite rows.
- **Tamper-evident.** Mutating any prior row's content changes its `row_hash`,
  which breaks the next row's `prev_row_hash` reference, which cascades forward.
- **Genesis anchor.** First row's `prev_row_hash` is the literal string
  `"genesis"`. Any row pointing to `"genesis"` other than the first is a
  `genesis-missing` violation.
- **Order matters.** Verifier reads rows in append order; out-of-order rows
  fail integrity check.

This is the same pattern as MIL-65's auth audit log (TypeScript, in production
since 2026-04-25). Pulse's Python port: see `canonical.py` (encoding),
`chain.py` (hash), `verifier.py` (chain walk).

## Canonical JSON

Pulse canonical JSON differs from MIL-65's in one respect: **lists are
permitted**. Pulse lineage rows carry `inputs: list[string]` — a list of
upstream lineage_ids — where order is semantically meaningful (input
ordering distinguishes "A then B" from "B then A" for sequential
operations).

All other rules carry: object keys sorted lexicographically, no whitespace,
non-finite numbers rejected.

## Verifier CLI

```
py -m pulse.lineage.verifier_cli path/to/pulse_lineage_log.jsonl
```

Exits 0 on intact chain, 1 on violations, 2 on invocation error. Pattern
matches `mil/auth/audit/src/verify_cli.ts`.

## Why not DVC or MLflow

The ticket reserves DVC/MLflow integration for a separate ticket. We start
with a self-contained JSONL log because:

1. JSONL is auditable with `cat`, `grep`, and `jq`. No tooling required to
   read the chain by hand.
2. The hash chain is independent of any storage backend. We can swap to
   D1, DuckDB, or DVC later without changing the chain semantics.
3. MIL-65 has 6 months of production evidence that the JSONL+hash-chain
   approach is robust under high-frequency append.

DVC and MLflow remain candidates for the inputs-snapshot layer
(`input_data_snapshot_refs` in audit bundles); the lineage chain itself
stays standalone.
