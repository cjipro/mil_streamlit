"""Audit bundle assembly — re-derivation evidence for a Pulse artifact (PULSE-89).

Implements AUDIT_QUERY_SPEC.md: given an artifact's `lineage_id`, walk the lineage
chain back through its `inputs` to the ingest anchor, gather the version + config
stamps along the way, run the chain verifier over the whole log, and return the
FCA Consumer Duty 2.0 evidence bundle — everything a reviewer needs to re-derive
the artifact from the inputs Pulse claims it used.

Generic over any lineage log; defaults to the decision lineage log
(pulse.decision.lineage). The audit boundary is adapter ingest — lineage does NOT
re-derive backwards into the bank's source systems.

Run:  py -m pulse.audit.bundle <artifact_id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pulse.decision.lineage import DECISIONS_LINEAGE_LOG
from pulse.lineage.verifier import verify_chain

# Fields surfaced per chain row (the content + version/config stamps; the chain
# linkage hashes prev_row_hash/row_hash drive verification, not the bundle view).
_SURFACED = (
    "lineage_id", "operation", "ts", "inputs", "artifact_hash",
    "pipeline_version", "decision_pack_version", "template_version", "config_hash",
)


def _load(log_path: Path) -> list[dict[str, Any]]:
    p = Path(log_path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_audit_bundle(
    artifact_id: str, *, log_path: Path = DECISIONS_LINEAGE_LOG
) -> dict[str, Any]:
    """Assemble the audit bundle for one artifact (lineage_id). See AUDIT_QUERY_SPEC."""
    rows = _load(log_path)
    by_id = {r["lineage_id"]: r for r in rows}
    if artifact_id not in by_id:
        return {"artifact_id": artifact_id, "found": False, "reason": "unknown artifact_id"}

    # Walk back through inputs to the ingest anchor (inputs=[]).
    chain_ids: list[str] = []
    seen: set[str] = set()
    frontier = [artifact_id]
    while frontier:
        lid = frontier.pop()
        if lid in seen or lid not in by_id:
            continue
        seen.add(lid)
        chain_ids.append(lid)
        frontier.extend(by_id[lid].get("inputs", []))
    # Order by the log's append order (causal order: ingest -> ... -> artifact),
    # robust to millisecond ts ties.
    order = {r["lineage_id"]: idx for idx, r in enumerate(rows)}
    chain = sorted((by_id[i] for i in chain_ids), key=lambda r: order[r["lineage_id"]])

    report = verify_chain(rows)  # integrity of the WHOLE log (tamper-evidence)
    pack_versions = sorted({
        r["decision_pack_version"] for r in chain if r.get("decision_pack_version")
    })

    bundle: dict[str, Any] = {
        "artifact_id": artifact_id,
        "found": True,
        "produced_at": chain[-1]["ts"] if chain else None,
        "lineage_chain": [{k: r.get(k) for k in _SURFACED} for r in chain],
        "input_data_snapshot_refs": [],  # DVC integration not shipped (per spec)
        "pipeline_versions": {r["operation"]: r["pipeline_version"] for r in chain},
        # synthesise rows (when present) carry template_version — surface them keyed by row.
        "template_versions": {
            r["lineage_id"]: r["template_version"] for r in chain if r.get("template_version")
        },
        "decision_pack_version": pack_versions[-1] if pack_versions else None,
        # v1 invariant: the only registered SynthesisProvider is deterministic — no
        # LLMSynthesisProvider exists and llm_augmented packs are rejected at validate.
        "synthesis_mode": "deterministic",
        "configs": {
            f"{i}:{r['operation']}": {"config_hash": r["config_hash"]}
            for i, r in enumerate(chain)
        },
        "chain_verified": report.ok,
    }
    if not report.ok:
        bundle["violations"] = [v.__dict__ for v in report.violations]
    return bundle


def main() -> None:
    p = argparse.ArgumentParser(description="Assemble a Pulse audit bundle for an artifact_id")
    p.add_argument("artifact_id")
    p.add_argument("--log", type=str, default=str(DECISIONS_LINEAGE_LOG))
    args = p.parse_args()
    print(json.dumps(build_audit_bundle(args.artifact_id, log_path=Path(args.log)), indent=2))


if __name__ == "__main__":
    main()
