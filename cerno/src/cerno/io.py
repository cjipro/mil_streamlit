"""Parquet IO with manifest emit + idempotency.

`write_parquet` is the load-bearing primitive: every layer-writing call
in cerno funnels through here. It computes the content snapshot_id,
checks whether an existing manifest already matches (idempotent skip
on the overnight re-run path), writes the Parquet, and emits the
_MANIFEST.json.

Per D-003 the snapshot_id is the first 16 hex chars of sha256 over the
sorted per-row JSON representation. Stable across machines and re-runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from cerno.manifest import Manifest, read_manifest, write_manifest

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa


def _content_snapshot(table: "pa.Table") -> str:
    """Sorted natural-key sha256, truncated to 16 hex. Deterministic."""
    row_hashes: list[str] = []
    for row in table.to_pylist():
        row_str = json.dumps(row, sort_keys=True, default=str)
        row_hashes.append(hashlib.sha256(row_str.encode("utf-8")).hexdigest())
    combined = "".join(sorted(row_hashes))
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def write_parquet(
    table: "pa.Table",
    out_dir: str | Path,
    *,
    layer: str,
    grain: str,
    partitions: list[str] | None = None,
    source_snapshot_id: str | None = None,
    run_id: str = "",
    params: dict | None = None,
) -> Manifest:
    """Write `table` to `out_dir` as Parquet, emitting a manifest.

    If `out_dir` already contains a manifest whose snapshot_id matches
    the content we would write, SKIP the write and return the existing
    manifest (logged as "snapshot identical — skipping write" via the
    structured logger by the caller).
    """
    import pyarrow.parquet as pq  # lazy

    out = Path(out_dir)
    snapshot_id = _content_snapshot(table)

    # Idempotency: if an existing manifest matches the snapshot we'd
    # emit, return without touching the filesystem.
    if out.exists():
        try:
            existing = read_manifest(out)
            if existing.snapshot_id == snapshot_id:
                return existing
        except FileNotFoundError:
            pass

    out.mkdir(parents=True, exist_ok=True)

    if partitions:
        pq.write_to_dataset(table, root_path=str(out), partition_cols=partitions)
    else:
        pq.write_table(table, out / "data.parquet")

    manifest = Manifest(
        layer=layer,
        grain=grain,
        row_count=table.num_rows,
        snapshot_id=snapshot_id,
        source_snapshot_id=source_snapshot_id,
        partitions=partitions or [],
        run_id=run_id,
        params=params or {},
    )
    write_manifest(out, manifest)
    return manifest


def read_parquet_with_manifest(
    in_dir: str | Path,
) -> tuple["pa.Table", Manifest]:
    """Read all parquet under `in_dir` and return (table, manifest)."""
    import pyarrow.parquet as pq  # lazy

    in_path = Path(in_dir)
    manifest = read_manifest(in_path)
    files = sorted(in_path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files under {in_path}")
    table = pq.read_table(files[0]) if len(files) == 1 else pq.read_table(in_path)
    return table, manifest
