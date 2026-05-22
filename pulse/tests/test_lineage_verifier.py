"""Tests for verify_chain — chain integrity over append-only rows."""

from __future__ import annotations

from pulse.lineage.chain import GENESIS, hash_row
from pulse.lineage.verifier import verify_chain


def _make_row(prev_hash: str, lineage_id: str, **content) -> dict:
    row = {
        "lineage_id": lineage_id,
        "ts": "2026-05-17T14:30:00.000Z",
        "operation": "ingest",
        "inputs": [],
        "artifact_hash": "a" * 64,
        "pipeline_version": "0.1.0",
        "decision_pack_version": None,
        "template_version": None,
        "config_hash": "c" * 64,
    }
    row.update(content)
    row["prev_row_hash"] = prev_hash
    row["row_hash"] = hash_row(row, prev_hash)
    return row


def _three_row_chain() -> list[dict]:
    r1 = _make_row(GENESIS, "lin-1")
    r2 = _make_row(r1["row_hash"], "lin-2", operation="analyse", inputs=["lin-1"])
    r3 = _make_row(r2["row_hash"], "lin-3", operation="synthesise", inputs=["lin-2"])
    return [r1, r2, r3]


def test_empty_log_is_ok() -> None:
    report = verify_chain([])
    assert report.ok
    assert report.total_rows == 0
    assert report.last_lineage_id is None


def test_single_genesis_row_passes() -> None:
    row = _make_row(GENESIS, "lin-1")
    report = verify_chain([row])
    assert report.ok
    assert report.total_rows == 1
    assert report.last_lineage_id == "lin-1"


def test_three_row_chain_passes() -> None:
    report = verify_chain(_three_row_chain())
    assert report.ok
    assert report.total_rows == 3


def test_tampered_middle_row_caught() -> None:
    rows = _three_row_chain()
    # Tamper: change row 2's operation but leave its row_hash stamped from before.
    rows[1]["operation"] = "EVIL"
    report = verify_chain(rows)
    assert not report.ok
    kinds = [v.kind for v in report.violations]
    assert "row-hash-mismatch" in kinds


def test_chain_break_caught() -> None:
    rows = _three_row_chain()
    # Tamper: rewrite row 3's prev_row_hash so it no longer chains to row 2.
    rows[2]["prev_row_hash"] = "not-the-real-prev"
    # Recompute row 3's own row_hash to make the row-hash-mismatch noise quieter
    # — we want to surface the chain-break specifically.
    rows[2]["row_hash"] = hash_row(rows[2], rows[2]["prev_row_hash"])
    report = verify_chain(rows)
    assert not report.ok
    kinds = [v.kind for v in report.violations]
    assert "chain-break" in kinds


def test_genesis_missing_caught() -> None:
    # First row's prev_row_hash is NOT GENESIS.
    fake_genesis = "x" * 64
    rows = [_make_row(fake_genesis, "lin-1")]
    report = verify_chain(rows)
    assert not report.ok
    assert any(v.kind == "genesis-missing" for v in report.violations)
