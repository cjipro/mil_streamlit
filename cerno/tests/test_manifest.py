"""Tests for cerno.manifest — write / read / verify."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from cerno.manifest import (
    MANIFEST_FILENAME,
    Manifest,
    read_manifest,
    verify_manifest,
    write_manifest,
)


def _write_sample_parquet(out_dir: Path, n_rows: int = 5) -> None:
    table = pa.table({"a": list(range(n_rows)), "b": [f"v{i}" for i in range(n_rows)]})
    pq.write_table(table, out_dir / "data.parquet")


def test_write_read_round_trip(tmp_path: Path) -> None:
    m = Manifest(
        layer="test_layer",
        grain="one row per thing",
        row_count=10,
        snapshot_id="abc1234567890def",
        source_snapshot_id=None,
        partitions=[],
        run_id="2026-05-30-deadbeef",
        params={"k": "v"},
    )
    write_manifest(tmp_path, m)
    loaded = read_manifest(tmp_path)
    assert loaded.layer == m.layer
    assert loaded.row_count == m.row_count
    assert loaded.snapshot_id == m.snapshot_id
    assert loaded.params == {"k": "v"}


def test_verify_passes_on_matching_row_count(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    _write_sample_parquet(tmp_path, n_rows=5)
    write_manifest(
        tmp_path,
        Manifest(
            layer="test",
            grain="row",
            row_count=5,
            snapshot_id="x" * 16,
        ),
    )
    ok, errors = verify_manifest(tmp_path)
    assert ok, errors


def test_verify_fails_on_tampered_row_count(tmp_path: Path) -> None:
    _write_sample_parquet(tmp_path, n_rows=5)
    # Manifest claims 99 rows but only 5 exist.
    write_manifest(
        tmp_path,
        Manifest(
            layer="test",
            grain="row",
            row_count=99,
            snapshot_id="x" * 16,
        ),
    )
    ok, errors = verify_manifest(tmp_path)
    assert not ok
    assert any("row_count mismatch" in e for e in errors)


def test_verify_fails_when_manifest_missing(tmp_path: Path) -> None:
    _write_sample_parquet(tmp_path, n_rows=3)
    ok, errors = verify_manifest(tmp_path)
    assert not ok
    assert errors


def test_verify_fails_when_no_parquet_files(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        Manifest(layer="test", grain="row", row_count=0, snapshot_id="y" * 16),
    )
    ok, errors = verify_manifest(tmp_path)
    assert not ok
    assert any("no parquet" in e for e in errors)


def test_manifest_file_is_named_correctly(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        Manifest(layer="x", grain="x", row_count=0, snapshot_id="z" * 16),
    )
    assert (tmp_path / MANIFEST_FILENAME).exists()
    # And it's valid JSON.
    json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
