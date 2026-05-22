"""Hash-chain row computation.

Pattern mirrored from MIL-65 (mil/auth/audit/src/hash.ts):
  row_hash = SHA256(canonical_json(hashed_columns) + "|" + prev_row_hash)
  first row's prev_row_hash = literal string GENESIS

Tampering with any prior row's content changes its row_hash, which breaks
the next row's prev_row_hash reference, which cascades forward — the
verifier catches it.

Filed under PULSE-89.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from pulse.lineage.canonical import canonical_json, sha256_hex

GENESIS = "genesis"  # literal string used as prev_row_hash for the first row

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


@functools.lru_cache(maxsize=1)
def _hashed_columns() -> list[str]:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["hashed_columns"]


def hash_row(content: dict[str, Any], prev_row_hash: str) -> str:
    """Compute row_hash for a row whose content fields are already populated."""
    filtered = {col: content.get(col) for col in _hashed_columns()}
    return sha256_hex(canonical_json(filtered) + "|" + prev_row_hash)


def recompute_row_hash(row: dict[str, Any]) -> str:
    """Recompute row_hash from a stored row (verifier use)."""
    return hash_row(row, row["prev_row_hash"])
