"""
thresholds.py — load and cache mil/config/thresholds.yaml.

Usage:
    from mil.config.thresholds import T
    timeout = T("api.anthropic_timeout_s")   # 60
    clark3  = T("clark.clark3_cac")          # 0.65
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_THRESHOLDS_YAML = Path(__file__).parent / "thresholds.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_THRESHOLDS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def T(dotted_key: str) -> Any:
    """
    Retrieve a threshold value by dotted key (e.g. 'clark.clark3_cac').
    Raises KeyError if the key path does not exist.
    """
    parts = dotted_key.split(".")
    node = _load()
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"[thresholds] key not found: '{dotted_key}'")
        node = node[part]
    return node


def reload() -> None:
    """Force reload (clears lru_cache). Useful in tests."""
    _load.cache_clear()
