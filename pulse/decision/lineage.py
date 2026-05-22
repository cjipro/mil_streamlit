"""Hash-chained lineage over the decision mart (PULSE-89).

Wires pulse.lineage through the decision layer. Every decision finding is recorded
as an append-only, hash-chained lineage row, re-derivable from the inputs it claims:

    ingest (MA_D)  ->  analyse (MA_S)  ->  analyse (friction detections)
                                              ->  analyse (one row per decision)

Each decision mart row carries its `lineage_id` + `lineage_row_hash`, so a surface
can prove the Action tier it shows is the one the chain anchors. Tampering with any
upstream row's content breaks the chain forward — verify with `verify_decision_lineage`
(or `py -m pulse.lineage.verifier_cli <log>`, or GET /lineage/verify).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pulse.lineage.canonical import canonical_json, sha256_hex
from pulse.lineage.chain import GENESIS, hash_row
from pulse.lineage.verifier import verify_chain
from pulse.serving.marts import MARTS_DIR

DECISIONS_LINEAGE_LOG = MARTS_DIR / "decisions_lineage.jsonl"
PIPELINE_VERSION = "0.1.0"


def _iso_now() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def build_decision_lineage(
    decisions: Iterable[Any],
    *,
    ma_s_manifest: dict[str, Any],
    friction_manifest: dict[str, Any],
    bank_policy: dict[str, Any],
    log_path: Path = DECISIONS_LINEAGE_LOG,
) -> dict[str, Any]:
    """Build + write the hash-chained lineage log for a decision run.

    Returns a summary incl. `decision_anchor`: {(screen_id, signature): (lineage_id,
    row_hash)} so the caller can stamp each decision mart row with its anchor."""
    rows: list[dict[str, Any]] = []
    prev = GENESIS

    def add(operation: str, inputs: list[str], artifact_hash: str,
            config: dict[str, Any], pack_version: str | None = None) -> tuple[str, str]:
        nonlocal prev
        row = {
            "lineage_id": uuid4().hex,
            "ts": _iso_now(),
            "operation": operation,
            "inputs": list(inputs),
            "artifact_hash": artifact_hash,
            "pipeline_version": PIPELINE_VERSION,
            "decision_pack_version": pack_version,
            "template_version": None,
            "config_hash": sha256_hex(canonical_json(config)),
            "prev_row_hash": prev,
        }
        row["row_hash"] = hash_row(row, prev)
        prev = row["row_hash"]
        rows.append(row)
        return row["lineage_id"], row["row_hash"]

    # Upstream stage chain. friction_manifest.source_snapshot_id IS the MA_D snapshot
    # (the audit boundary — lineage starts at adapter ingest, not the bank source).
    ma_d_snapshot = friction_manifest.get("source_snapshot_id") or "unknown"
    ingest_id, _ = add("ingest", [], ma_d_snapshot, {"stage": "generate_ma_d"})
    ma_s_id, _ = add("analyse", [ingest_id],
                     ma_s_manifest.get("snapshot_id", "unknown"), {"stage": "sessionise"})
    friction_id, _ = add("analyse", [ma_s_id],
                         sha256_hex(canonical_json(friction_manifest)), {"stage": "detect_sessions"})

    # One row per decision — artifact_hash is the decision's own content hash, so
    # any later mutation of the decision is provable against the chain.
    decision_anchor: dict[tuple[str, str], tuple[str, str]] = {}
    for d in decisions:
        content = d.as_dict()
        lid, rh = add(
            "analyse", [friction_id], sha256_hex(canonical_json(content)), bank_policy,
            pack_version=f"{d.screen_id.replace('.', '_')}__{d.signature}@{PIPELINE_VERSION}",
        )
        decision_anchor[(d.screen_id, d.signature)] = (lid, rh)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    report = verify_chain(rows)
    return {
        "log_path": str(log_path),
        "rows": len(rows),
        "head_row_hash": rows[-1]["row_hash"] if rows else GENESIS,
        "chain_verified": report.ok,
        "decision_anchor": decision_anchor,
    }


def verify_decision_lineage(log_path: Path = DECISIONS_LINEAGE_LOG) -> dict[str, Any]:
    """Verify the decision lineage log. JSON-serialisable report for /lineage/verify."""
    if not log_path.exists():
        return {"ok": False, "reason": "no_lineage_log", "total_rows": 0, "violations": 0}
    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = verify_chain(rows)
    return {
        "ok": report.ok,
        "total_rows": report.total_rows,
        "violations": [v.__dict__ for v in report.violations],
        "head_row_hash": report.last_row_hash,
    }
