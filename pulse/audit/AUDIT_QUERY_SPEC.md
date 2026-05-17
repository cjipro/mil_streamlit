# Pulse audit query — interface spec

**Filed under PULSE-89.**

## Endpoint

```
GET /pulse/audit/<artifact_id>
```

`artifact_id` is the identifier of any Pulse-produced artifact — an ingested
event, an analytic intermediate, a synthesis output, or a published finding.

The handler walks the lineage chain backwards from the artifact to its
ingest anchors, gathers all version + config stamps along the way, and
returns the **audit bundle**: everything a reviewer needs to re-derive
the artifact from the inputs Pulse claims it used.

## Response shape

```json
{
  "artifact_id": "art_2026-05-17_001",
  "produced_at": "2026-05-17T14:32:11.847Z",
  "lineage_chain": [
    {
      "lineage_id": "lin_<uuid>",
      "operation": "ingest",
      "ts": "2026-05-17T14:30:00.123Z",
      "inputs": [],
      "artifact_hash": "<sha256>",
      "pipeline_version": "0.1.0",
      "decision_pack_version": null,
      "template_version": null,
      "config_hash": "<sha256>"
    },
    {
      "lineage_id": "lin_<uuid>",
      "operation": "analyse",
      "ts": "2026-05-17T14:31:48.012Z",
      "inputs": ["lin_<uuid-of-ingest>"],
      "artifact_hash": "<sha256>",
      "pipeline_version": "0.2.0",
      "decision_pack_version": "1.0.0",
      "template_version": null,
      "config_hash": "<sha256>"
    },
    {
      "lineage_id": "lin_<uuid>",
      "operation": "synthesise",
      "ts": "2026-05-17T14:32:11.847Z",
      "inputs": ["lin_<uuid-of-analyse>"],
      "artifact_hash": "<sha256>",
      "pipeline_version": "0.2.0",
      "decision_pack_version": "1.0.0",
      "template_version": "1.0.0",
      "config_hash": "<sha256>"
    }
  ],
  "input_data_snapshot_refs": ["dvc:<hash-1>", "dvc:<hash-2>"],
  "pipeline_versions": {"ingest": "0.1.0", "analyse": "0.2.0", "synthesise": "0.2.0"},
  "template_versions": {"loans.apply.step3.brief": "1.0.0"},
  "decision_pack_version": "journey_friction-1.0.0",
  "synthesis_mode": "deterministic",
  "configs": {
    "ingest": {"adapter": "taq", "contract_version": "1.0.0"},
    "analyse": {"convergence_required": true, "fairness_methods_used": ["demographic_parity"]},
    "synthesise": {"template_library": "journey_friction-1.0.0"}
  },
  "chain_verified": true
}
```

## Field semantics

| Field | Purpose |
|---|---|
| `artifact_id` | The thing the reviewer is asking about |
| `produced_at` | ts of the most recent row in `lineage_chain` |
| `lineage_chain` | Ordered list of rows from ingest → artifact. One row per operation |
| `input_data_snapshot_refs` | DVC-style hashes of input batches (when DVC integration lands) |
| `pipeline_versions` | Map of operation → pipeline semver active when that row was produced |
| `template_versions` | Map of template name → semver (synthesise rows only) |
| `decision_pack_version` | `<pack_name>-<semver>` active throughout the chain |
| `synthesis_mode` | Always `"deterministic"` in v1. Auditors verify this directly |
| `configs` | Operation → config snapshot active at row time (full snapshot is referenced by `config_hash`; this field surfaces the salient knobs) |
| `chain_verified` | Result of running `verify_chain()` over the chain — true if no integrity violations |

## Re-derivation contract

The audit bundle is sufficient for a reviewer to re-derive the artifact:

1. Check out the codebase at `pipeline_versions` + `template_versions`
2. Load the decision pack at `decision_pack_version`
3. Load the input batches by `input_data_snapshot_refs`
4. Apply the configs in `configs`
5. Run the pipeline
6. Compute the artifact hash and check it matches the last row's `artifact_hash`

Step 6 is the integrity proof. If the hashes match, the artifact is
exactly what Pulse claims it produced from those inputs at that pack
version. If they don't match, either the bundle is wrong or the artifact
has been tampered with.

## Chain verification

`chain_verified` is the result of running `pulse.lineage.verify_chain()`
over the chain. The handler MUST run the verifier before responding. If
`chain_verified: false`, the bundle is still returned but `violations`
field is populated:

```json
{
  ...
  "chain_verified": false,
  "violations": [
    {"kind": "row-hash-mismatch", "lineage_id": "lin_xyz",
     "expected": "abc...", "actual": "def..."}
  ]
}
```

A reviewer seeing `chain_verified: false` knows the lineage log itself has
been tampered with or corrupted — Pulse cannot vouch for any artifact whose
chain doesn't verify.

## Backwards lineage (NOT shipped)

Per Hamel's audit-boundary point in the panel: **we do not re-derive
lineage backwards into the bank's source systems.** The chain starts at
the moment data enters the Pulse perimeter (adapter ingest stamp). The
audit bundle's `input_data_snapshot_refs` reference DVC-stored batches of
canonical events; further upstream (the bank's source row that produced
each event) is opaque by design.

## Why this shape

This is the FCA Consumer Duty 2.0 evidence artifact. Any finding Pulse
publishes, any escalation it triggers, any CHRONICLE entry it proposes —
each carries an `artifact_id` that resolves through this endpoint to a
bundle a reviewer can act on without further interrogation.

The shape mirrors the audit-bundle pattern from MIL-65 (auth event audit
export) — same "ordered log + integrity stamps + verifier result" structure.
