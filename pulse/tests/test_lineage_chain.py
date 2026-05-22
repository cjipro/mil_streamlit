"""Tests for the hash-chain row computation."""

from __future__ import annotations

from pulse.lineage.chain import GENESIS, hash_row, recompute_row_hash


def _row(**overrides) -> dict:
    base = {
        "lineage_id": "lin-1",
        "ts": "2026-05-17T14:30:00.123Z",
        "operation": "ingest",
        "inputs": [],
        "artifact_hash": "a" * 64,
        "pipeline_version": "0.1.0",
        "decision_pack_version": None,
        "template_version": None,
        "config_hash": "c" * 64,
    }
    base.update(overrides)
    return base


def test_hash_row_is_deterministic() -> None:
    row = _row()
    h1 = hash_row(row, GENESIS)
    h2 = hash_row(row, GENESIS)
    assert h1 == h2
    assert len(h1) == 64


def test_hash_row_changes_when_content_changes() -> None:
    a = _row(operation="ingest")
    b = _row(operation="analyse")
    assert hash_row(a, GENESIS) != hash_row(b, GENESIS)


def test_hash_row_changes_when_prev_hash_changes() -> None:
    row = _row()
    assert hash_row(row, GENESIS) != hash_row(row, "different-prev")


def test_dict_key_order_does_not_affect_hash() -> None:
    a = {"operation": "ingest", "lineage_id": "lin-1", "ts": "t", "inputs": [],
         "artifact_hash": "ah", "pipeline_version": "0.1.0",
         "decision_pack_version": None, "template_version": None, "config_hash": "ch"}
    b = {"config_hash": "ch", "template_version": None, "decision_pack_version": None,
         "pipeline_version": "0.1.0", "artifact_hash": "ah", "inputs": [],
         "ts": "t", "lineage_id": "lin-1", "operation": "ingest"}
    assert hash_row(a, GENESIS) == hash_row(b, GENESIS)


def test_list_order_in_inputs_affects_hash() -> None:
    a = _row(inputs=["lin-x", "lin-y"])
    b = _row(inputs=["lin-y", "lin-x"])
    assert hash_row(a, GENESIS) != hash_row(b, GENESIS)


def test_non_hashed_field_does_not_affect_hash() -> None:
    # row_hash + prev_row_hash live OUTSIDE hashed_columns. Adding random
    # non-hashed keys to the content dict must not change the row_hash.
    a = _row()
    b = _row()
    b["irrelevant_field"] = "anything"
    assert hash_row(a, GENESIS) == hash_row(b, GENESIS)


def test_recompute_row_hash_matches_hash_row() -> None:
    row = _row()
    computed = hash_row(row, GENESIS)
    row["prev_row_hash"] = GENESIS
    row["row_hash"] = computed
    assert recompute_row_hash(row) == computed


def test_genesis_anchor_is_literal_string() -> None:
    assert GENESIS == "genesis"
