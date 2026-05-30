"""Deterministic run identifiers.

run_id = `YYYY-MM-DD-<8 hex of sha256 of sorted params>`.

Determinism rule (D-003 / D-005): same date + same params yield the
same run_id across machines and re-runs. This is the anchor that makes
manifests idempotent and lineage chains stable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def make_run_id(date: str | None = None, params: dict | None = None) -> str:
    """Return a deterministic run id of the form `YYYY-MM-DD-XXXXXXXX`.

    `date`   — ISO YYYY-MM-DD. Defaults to today UTC.
    `params` — dict of parameters that uniquely identify this run.
               Sorted by key before hashing, so key order does not change
               the digest.
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = json.dumps(params or {}, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:8]
    return f"{date}-{digest}"
