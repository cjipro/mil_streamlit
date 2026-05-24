"""Pulse taxonomy (PULSE-137) — the real TAQ taxonomy, self-contained.

Loads the committed artifacts in pulse/contracts/:
  - taq_taxonomy.yaml    manifest: counts + vocabularies
  - taq_op_code_map.csv  op_code -> journey, customer_journey

NEVER reads taq-app — regenerate the artifacts with scripts/build_taq_taxonomy.py.
The pulse package stays self-contained (same principle as generate_ma_d.py).

Three tiers (screens.yaml v2):
  Journey (24)           — `journey` field; coarse/technical grouping, NOT customer journeys
  Customer Journey (107) — `feature` field; CJ01..CJ107, the canonical roll-up
  Op-code (697)          — the grain (keyed by screen `id`)

Op-code -> {customer_journey, journey} are parallel, nullable roll-up dimensions. 97
op-codes have no Customer Journey (api + extras) — the ORPHAN bucket, surfaced via
orphans() + coverage() and never silently dropped (else roll-ups undercount and
"verify every claim" breaks).
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

import yaml

_CONTRACTS = Path(__file__).parent / "contracts"
_MANIFEST = _CONTRACTS / "taq_taxonomy.yaml"
_MAP = _CONTRACTS / "taq_op_code_map.csv"


@functools.lru_cache(maxsize=1)
def manifest() -> dict:
    return yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def op_code_map() -> tuple[dict, ...]:
    """All 697 op-code rows: {id, op_code, journey, customer_journey} (customer_journey '' => orphan)."""
    with _MAP.open("r", encoding="utf-8", newline="") as f:
        return tuple(dict(r) for r in csv.DictReader(f))


@functools.lru_cache(maxsize=1)
def _by_id() -> dict:
    return {r["id"]: r for r in op_code_map()}


def journeys() -> list[str]:
    """The 24 Journey-tier values (coarse grouping; not customer journeys)."""
    return list(manifest()["journeys"])


def customer_journeys() -> list[str]:
    """The 107 Customer-Journey values (the canonical roll-up the selectors target)."""
    return list(manifest()["customer_journeys"])


def op_codes() -> list[str]:
    """All 697 op-code ids (the grain)."""
    return [r["id"] for r in op_code_map()]


def lookup(op_code_id: str) -> dict | None:
    """Return {id, op_code, journey, customer_journey} for an op-code id, or None."""
    return _by_id().get(op_code_id)


def orphans() -> list[str]:
    """Op-code ids with no Customer Journey (the unmapped bucket — never dropped)."""
    return [r["id"] for r in op_code_map() if not r["customer_journey"]]


def coverage() -> float:
    """Percent of op-codes that roll up to a Customer Journey."""
    rows = op_code_map()
    mapped = sum(1 for r in rows if r["customer_journey"])
    return round(100.0 * mapped / len(rows), 2) if rows else 0.0


def rollup_by_customer_journey() -> dict[str, list[str]]:
    """Customer Journey -> [op-code ids]. Orphans excluded (see orphans())."""
    out: dict[str, list[str]] = {}
    for r in op_code_map():
        if r["customer_journey"]:
            out.setdefault(r["customer_journey"], []).append(r["id"])
    return out


def rollup_by_journey() -> dict[str, list[str]]:
    """Journey (24-tier) -> [op-code ids]. Every op-code has a journey."""
    out: dict[str, list[str]] = {}
    for r in op_code_map():
        out.setdefault(r["journey"], []).append(r["id"])
    return out
