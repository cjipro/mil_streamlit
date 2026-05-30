"""Tests for cerno.io — write_parquet (with manifest + idempotency)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from cerno.io import _content_snapshot, read_parquet_with_manifest, write_parquet
from cerno.manifest import Manifest, read_manifest


def _table() -> pa.Table:
    return pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})


def test_write_emits_parquet_and_manifest(tmp_path: Path) -> None:
    out = tmp_path / "ma_d"
    m = write_parquet(
        _table(), out, layer="ma_d", grain="raw event", run_id="run-1"
    )
    assert isinstance(m, Manifest)
    assert m.row_count == 3
    assert m.layer == "ma_d"
    assert (out / "data.parquet").exists()
    assert (out / "_MANIFEST.json").exists()


def test_idempotent_skip_on_identical_content(tmp_path: Path) -> None:
    out = tmp_path / "ma_d"
    m1 = write_parquet(_table(), out, layer="ma_d", grain="raw event")
    parquet_file = out / "data.parquet"
    mtime1 = parquet_file.stat().st_mtime_ns

    # Second write with identical content should skip.
    m2 = write_parquet(_table(), out, layer="ma_d", grain="raw event")
    mtime2 = parquet_file.stat().st_mtime_ns

    assert m1.snapshot_id == m2.snapshot_id
    assert mtime1 == mtime2  # file untouched


def test_different_content_triggers_write(tmp_path: Path) -> None:
    out = tmp_path / "ma_d"
    write_parquet(_table(), out, layer="ma_d", grain="raw event")
    snap1 = read_manifest(out).snapshot_id

    # Different table content → different snapshot → write proceeds.
    other = pa.table({"a": [10, 20, 30], "b": ["p", "q", "r"]})
    write_parquet(other, out, layer="ma_d", grain="raw event")
    snap2 = read_manifest(out).snapshot_id

    assert snap1 != snap2


def test_round_trip_via_read_parquet_with_manifest(tmp_path: Path) -> None:
    out = tmp_path / "ma_d"
    write_parquet(_table(), out, layer="ma_d", grain="raw event")
    table, manifest = read_parquet_with_manifest(out)
    assert table.num_rows == 3
    assert manifest.row_count == 3


def test_content_snapshot_is_deterministic() -> None:
    s1 = _content_snapshot(_table())
    s2 = _content_snapshot(_table())
    assert s1 == s2
    assert len(s1) == 16


def test_lineage_threading_via_source_snapshot_id(tmp_path: Path) -> None:
    # Write a "source" layer, capture its snapshot, thread it into the
    # next layer via source_snapshot_id.
    src_out = tmp_path / "source"
    src_manifest = write_parquet(_table(), src_out, layer="source", grain="raw")

    derived_out = tmp_path / "ma_d"
    derived = pa.table({"a": [100, 200], "b": ["m", "n"]})
    derived_manifest = write_parquet(
        derived,
        derived_out,
        layer="ma_d",
        grain="raw event",
        source_snapshot_id=src_manifest.snapshot_id,
    )
    assert derived_manifest.source_snapshot_id == src_manifest.snapshot_id
