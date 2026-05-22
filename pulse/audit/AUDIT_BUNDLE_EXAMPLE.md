# Audit bundle — end-to-end example

**Filed under PULSE-89.**

A worked example for one v1 investigation: TAQ App emits a `dwell_after_error`
signature on `loans.apply.step3`, Pulse ingests it, analyses with multi-path
convergence (chi-squared + demographic-parity), synthesises a friction
brief, and publishes it. The audit bundle returned for the published brief
looks like this.

## Investigation summary

- Question class: `cause`
- Friction signature: `dwell_after_error`
- Friction-target screen: `loans.apply.step3`
- Decision pack: `journey_friction-1.0.0`
- `convergence_required: true` (CHRONICLE candidate)
- Methods exercised: `chi_squared` + `demographic_parity`
- Output artifact: `loans.apply.step3 — dwell-after-error finding brief`

## Lineage chain (4 rows)

### Row 1 — ingest

```yaml
lineage_id: lin_a1b2c3d4-...
ts: 2026-05-17T14:30:00.123Z
operation: ingest
inputs: []
artifact_hash: ad77ee...   # SHA-256 of the canonical-encoded batch of TAQ events
pipeline_version: 0.1.0    # pulse.adapters.taq version
decision_pack_version: null
template_version: null
config_hash: 7c19e2...     # taq_contract.yaml version + adapter config
prev_row_hash: genesis
row_hash: <derived>
```

### Row 2 — analyse (chi-squared)

```yaml
lineage_id: lin_e5f6g7h8-...
ts: 2026-05-17T14:31:11.005Z
operation: analyse
inputs: [lin_a1b2c3d4-...]
artifact_hash: 9b4f1e...   # SHA-256 of the analytic output (test statistic + p + bucket counts)
pipeline_version: 0.2.0    # pulse.analytics version (future ticket)
decision_pack_version: 1.0.0
template_version: null
config_hash: 4321ba...     # method=chi_squared, alpha=0.05, etc.
prev_row_hash: <Row 1 row_hash>
row_hash: <derived>
```

### Row 3 — analyse (demographic_parity)

```yaml
lineage_id: lin_i9j0k1l2-...
ts: 2026-05-17T14:31:42.218Z
operation: analyse
inputs: [lin_a1b2c3d4-...]   # same ingest input; different analytic
artifact_hash: c0d8a7...
pipeline_version: 0.2.0
decision_pack_version: 1.0.0
template_version: null
config_hash: 8765dc...     # method=demographic_parity, cohort_key=age_bucket
prev_row_hash: <Row 2 row_hash>
row_hash: <derived>
```

### Row 4 — synthesise

```yaml
lineage_id: lin_m3n4o5p6-...
ts: 2026-05-17T14:32:11.847Z
operation: synthesise
inputs: [lin_e5f6g7h8-..., lin_i9j0k1l2-...]   # both analytics
artifact_hash: 1357fb...   # SHA-256 of the rendered brief text
pipeline_version: 0.2.0
decision_pack_version: 1.0.0
template_version: 1.0.0    # loans.apply.step3.brief template
config_hash: aabbcc...
prev_row_hash: <Row 3 row_hash>
row_hash: <derived>
```

## Audit bundle returned for the published brief

```json
{
  "artifact_id": "art_loans-step3-dwell-2026-05-17_001",
  "produced_at": "2026-05-17T14:32:11.847Z",
  "lineage_chain": [
    {"lineage_id": "lin_a1b2c3d4-...", "operation": "ingest",     "ts": "2026-05-17T14:30:00.123Z", "inputs": [],                                                "artifact_hash": "ad77ee...", "pipeline_version": "0.1.0", "decision_pack_version": null,    "template_version": null,    "config_hash": "7c19e2..."},
    {"lineage_id": "lin_e5f6g7h8-...", "operation": "analyse",    "ts": "2026-05-17T14:31:11.005Z", "inputs": ["lin_a1b2c3d4-..."],                              "artifact_hash": "9b4f1e...", "pipeline_version": "0.2.0", "decision_pack_version": "1.0.0", "template_version": null,    "config_hash": "4321ba..."},
    {"lineage_id": "lin_i9j0k1l2-...", "operation": "analyse",    "ts": "2026-05-17T14:31:42.218Z", "inputs": ["lin_a1b2c3d4-..."],                              "artifact_hash": "c0d8a7...", "pipeline_version": "0.2.0", "decision_pack_version": "1.0.0", "template_version": null,    "config_hash": "8765dc..."},
    {"lineage_id": "lin_m3n4o5p6-...", "operation": "synthesise", "ts": "2026-05-17T14:32:11.847Z", "inputs": ["lin_e5f6g7h8-...", "lin_i9j0k1l2-..."],          "artifact_hash": "1357fb...", "pipeline_version": "0.2.0", "decision_pack_version": "1.0.0", "template_version": "1.0.0", "config_hash": "aabbcc..."}
  ],
  "input_data_snapshot_refs": ["dvc:taq-batch-2026-05-17-14h30"],
  "pipeline_versions": {"ingest": "0.1.0", "analyse": "0.2.0", "synthesise": "0.2.0"},
  "template_versions": {"loans.apply.step3.brief": "1.0.0"},
  "decision_pack_version": "journey_friction-1.0.0",
  "synthesis_mode": "deterministic",
  "configs": {
    "ingest":     {"adapter": "taq", "contract_version": "1.0.0"},
    "analyse_1":  {"method": "chi_squared", "alpha": 0.05},
    "analyse_2":  {"method": "demographic_parity", "cohort_key": "age_bucket"},
    "synthesise": {"template_library": "journey_friction-1.0.0", "template": "loans.apply.step3.brief"}
  },
  "chain_verified": true
}
```

## What a reviewer can do with this bundle

A reviewer (FCA, internal audit, partner risk team) can:

1. **Verify integrity.** `chain_verified: true` means `pulse.lineage.verify_chain()`
   recomputed every `row_hash` in the chain and they all match the stored
   values. Tampering would surface here.

2. **Verify fairness coverage.** `analyse_2` config shows `demographic_parity`
   was run alongside `chi_squared` — satisfies the convergence requirement
   for the CHRONICLE-candidate context (`fairness_methods_required: true`
   on the pack).

3. **Verify deterministic synthesis.** `synthesis_mode: deterministic` —
   no LLM was involved. Same inputs would produce the same brief
   byte-identically.

4. **Re-derive the brief from scratch.** Check out the code at the named
   pipeline versions, load the inputs via the DVC snapshot ref, apply the
   configs shown, re-run, and compare the final `artifact_hash` to
   `1357fb...`. If they match, Pulse is telling the truth about how the
   brief was produced.

This is the FCA Consumer Duty 2.0 evidence pattern in concrete form. Every
output Pulse produces resolves to a bundle of this shape via the
`/pulse/audit/<artifact_id>` endpoint.
