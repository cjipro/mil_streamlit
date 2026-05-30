"""Manifest schema + emit / read / verify.

Every transform that writes Parquet emits a `_MANIFEST.json` next to
the output. Manifests carry the snapshot_id used for idempotency and
the source_snapshot_id used for lineage chaining.

Per D-003: `snapshot_id` is computed by content (sorted natural-key
sha256, first 16 hex chars). See cerno.io._content_snapshot.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST_FILENAME = "_MANIFEST.json"
MANIFEST_VERSION = "1.0"


@dataclass
class Manifest:
    """Single-file manifest describing a Parquet output directory."""

    layer: str                          # e.g., "ma_d", "ma_s", "mart_daily"
    grain: str                          # human-readable, e.g., "one row per session"
    row_count: int
    snapshot_id: str                    # 16 hex chars of content sha256
    source_snapshot_id: str | None = None  # for lineage chaining
    partitions: list[str] = field(default_factory=list)
    run_id: str = ""
    params: dict = field(default_factory=dict)
    version: str = MANIFEST_VERSION


def write_manifest(out_dir: str | Path, manifest: Manifest) -> Path:
    """Persist the manifest as `<out_dir>/_MANIFEST.json`. Returns its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / MANIFEST_FILENAME
    target.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def read_manifest(out_dir: str | Path) -> Manifest:
    """Load the manifest from `<out_dir>/_MANIFEST.json`."""
    path = Path(out_dir) / MANIFEST_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(**data)


def verify_manifest(out_dir: str | Path) -> tuple[bool, list[str]]:
    """Verify that `row_count` matches the actual Parquet content.

    Returns (ok, errors). Empty errors list iff verify passes.
    """
    errors: list[str] = []
    try:
        m = read_manifest(out_dir)
    except FileNotFoundError as exc:
        return False, [str(exc)]
    except (json.JSONDecodeError, TypeError) as exc:
        return False, [f"manifest unreadable: {exc}"]

    parquet_files = sorted(Path(out_dir).rglob("*.parquet"))
    if not parquet_files:
        errors.append("no parquet files alongside manifest")
        return False, errors

    try:
        import pyarrow.parquet as pq  # lazy import

        actual_rows = sum(pq.read_metadata(p).num_rows for p in parquet_files)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"failed to read parquet metadata: {exc}")
        return False, errors

    if actual_rows != m.row_count:
        errors.append(
            f"row_count mismatch: manifest={m.row_count} actual={actual_rows}"
        )

    return len(errors) == 0, errors
