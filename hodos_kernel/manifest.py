"""
hodos_kernel.manifest — the product definition (HODOS-4 spike).

A decision product IS this manifest. Loads + lightly validates a product.yaml.
The five blocks map 1:1 to the engine stages: sources → canonical → detectors →
decision → synthesis/surface.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REQUIRED = ["product", "sources", "canonical", "detectors", "decision", "surface"]


def load_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        m = yaml.safe_load(f)

    missing = [k for k in _REQUIRED if k not in m]
    if missing:
        raise ValueError(f"{path.name}: manifest missing required blocks: {missing}")

    can = m["canonical"]
    for k in ("entity_id", "group"):
        if k not in can:
            raise ValueError(f"{path.name}: canonical block needs '{k}'")
    for d in m["detectors"]:
        for k in ("id", "metric", "op", "threshold"):
            if k not in d:
                raise ValueError(f"{path.name}: detector {d.get('id','?')} missing '{k}'")
    dec = m["decision"]
    if "thresholds" not in dec or "action_template" not in dec:
        raise ValueError(f"{path.name}: decision block needs 'thresholds' + 'action_template'")
    return m
