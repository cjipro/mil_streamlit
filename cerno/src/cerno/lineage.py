"""Lineage — hash chain across manifests.

Each manifest carries `source_snapshot_id` pointing at the snapshot it
was derived from. A chain reads:

    source  →  MA_D  →  MA_S  →  marts

with each layer's manifest holding the previous layer's snapshot_id.
`chain_id` and `verify_chain` are the primitives that make tampering
visible.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

from cerno.manifest import Manifest


def chain_id(prev_snapshot: str | None, this_snapshot: str) -> str:
    """Hash-link `prev_snapshot` to `this_snapshot`.

    sha256 of `<prev>||<this>` truncated to 16 hex. None for the head of
    the chain is normalised to the empty string so the hash is stable.
    """
    prev = prev_snapshot or ""
    payload = f"{prev}||{this_snapshot}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def verify_chain(manifests: Sequence[Manifest]) -> tuple[bool, list[str]]:
    """Verify that each manifest's `source_snapshot_id` matches the
    previous manifest's `snapshot_id`.

    Returns (ok, errors). The first manifest is treated as the head
    of the chain and is not back-checked.
    """
    errors: list[str] = []
    for i in range(1, len(manifests)):
        prev = manifests[i - 1]
        cur = manifests[i]
        if cur.source_snapshot_id != prev.snapshot_id:
            errors.append(
                f"chain break at index {i} (layer={cur.layer!r}): "
                f"source_snapshot_id={cur.source_snapshot_id!r} "
                f"expected={prev.snapshot_id!r}"
            )
    return len(errors) == 0, errors
