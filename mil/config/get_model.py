"""
get_model.py — MIL model routing utility.

Single source of truth for task-to-model mapping.
Reads from mil/config/model_routing.yaml (MIL-MODEL-001).

Usage:
    from mil.config.get_model import get_model

    cfg = get_model("enrichment")
    # {"task": "enrichment", "model": "claude-haiku-4-5-20251001",
    #  "provider": "anthropic", "max_tokens": 8192, "base_url": None, ...}

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_ROUTING_YAML = Path(__file__).parent / "model_routing.yaml"


@lru_cache(maxsize=1)
def _load_routing() -> dict:
    """Load and cache model_routing.yaml. Cached for process lifetime."""
    with open(_ROUTING_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_model(task: str) -> dict:
    """
    Return routing config for the given task.

    Returns a dict with keys:
        task        — the task name
        model       — model identifier string
        provider    — "anthropic" | "ollama"
        max_tokens  — int
        base_url    — Ollama base URL (None for Anthropic)
        api_compat_url — Ollama OpenAI-compat URL (None for Anthropic)
        note        — human-readable rationale

    Raises KeyError if task is not in model_routing.yaml.
    """
    routing = _load_routing()
    routes = routing.get("routes", {})
    providers = routing.get("providers", {})

    if task not in routes:
        raise KeyError(
            f"[get_model] Unknown task '{task}'. "
            f"Valid tasks: {sorted(routes.keys())}"
        )

    route = routes[task]
    provider_name = route["provider"]
    provider = providers.get(provider_name, {})

    return {
        "task":            task,
        "model":           route["model"],
        "provider":        provider_name,
        "max_tokens":      route.get("max_tokens", 512),
        "base_url":        provider.get("base_url"),
        "api_compat_url":  provider.get("api_compat_url"),
        "note":            route.get("note", ""),
    }


def list_routes() -> list[str]:
    """Return sorted list of known task names."""
    return sorted(_load_routing().get("routes", {}).keys())


def reload() -> None:
    """Force reload of model_routing.yaml (clears lru_cache)."""
    _load_routing.cache_clear()


if __name__ == "__main__":
    import json
    print("MIL Model Routing — current assignments\n")
    for task in list_routes():
        cfg = get_model(task)
        print(f"  {task:<22} {cfg['model']:<40} ({cfg['provider']})")
