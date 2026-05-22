"""Canonical JSON + SHA-256 helpers for the lineage chain.

Canonical JSON guarantees byte-identical output across runtimes:
  - object keys sorted lexicographically
  - no whitespace
  - non-finite numbers rejected (NaN/Infinity break determinism)
  - tuples coerced to lists (JSON has no tuple distinction)

Lists ARE permitted here (unlike MIL-65's TS variant) because Pulse lineage
rows carry `inputs: list[string]` (upstream lineage_ids). Lists are encoded
recursively in their declared order — order is semantically meaningful and
must NOT be sorted.

Filed under PULSE-89.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def sha256_hex(s: str) -> str:
    """Lowercase hex SHA-256 of a UTF-8 string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    """Deterministic, whitespace-free JSON encoding with sorted object keys."""
    return _encode(value)


def _encode(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError(f"non-finite number in canonical JSON: {v}")
        return json.dumps(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in v) + "]"
    if isinstance(v, dict):
        keys = sorted(v.keys())
        for k in keys:
            if not isinstance(k, str):
                raise TypeError(f"canonical JSON requires string keys, got {type(k).__name__}")
        return "{" + ",".join(json.dumps(k) + ":" + _encode(v[k]) for k in keys) + "}"
    raise TypeError(f"unsupported value type in canonical JSON: {type(v).__name__}")
