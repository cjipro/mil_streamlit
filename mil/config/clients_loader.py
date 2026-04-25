"""mil/config/clients_loader.py — typed accessors for clients.yaml (MIL-85).

Replaces the Barclays hardcode in briefing_data.py and the implicit peer
list scattered across benchmark_engine.py / publish_v4.py / briefing_email.py.
Loaded once per process via @lru_cache.

Public API:
    clients()                       -> list[Client]   (all entries)
    subjects()                      -> list[Client]   (status == "subject")
    monitored()                     -> list[Client]   (status == "monitored")
    incumbent_slugs()               -> list[str]
    neobank_slugs()                 -> list[str]
    by_slug(slug)                   -> Client | None
    display_name(slug)              -> str            (raises KeyError if unknown)
    slug_for_display_name(name)     -> str | None     (case-insensitive)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "clients.yaml"

ClientStatus = Literal["subject", "monitored", "retired"]
MarketTier = Literal["incumbent", "neobank"]


@dataclass(frozen=True)
class Client:
    client_slug: str
    display_name: str
    market_tier: MarketTier
    workos_org_id: str
    status: ClientStatus
    onboarded: str


def _validate_entry(idx: int, raw: dict) -> Client:
    required = ("client_slug", "display_name", "market_tier", "status")
    missing = [f for f in required if f not in raw]
    if missing:
        raise ValueError(f"clients.yaml entry [{idx}] missing fields: {missing}")
    if raw["status"] not in ("subject", "monitored", "retired"):
        raise ValueError(f"clients.yaml entry [{idx}] invalid status: {raw['status']}")
    if raw["market_tier"] not in ("incumbent", "neobank"):
        raise ValueError(f"clients.yaml entry [{idx}] invalid market_tier: {raw['market_tier']}")
    slug = raw["client_slug"]
    if not slug or not slug.replace("-", "").isalnum() or slug != slug.lower():
        raise ValueError(f"clients.yaml entry [{idx}] slug must be lowercase alphanumeric/hyphen: {slug!r}")
    return Client(
        client_slug=slug,
        display_name=raw["display_name"],
        market_tier=raw["market_tier"],
        workos_org_id=raw.get("workos_org_id", "") or "",
        status=raw["status"],
        onboarded=raw.get("onboarded", "") or "",
    )


@lru_cache(maxsize=1)
def clients() -> tuple[Client, ...]:
    """Load and validate all client entries. Cached per process."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"clients.yaml not found at {_CONFIG_PATH}")
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    entries = raw.get("clients", []) or []
    if not entries:
        raise ValueError(f"clients.yaml has no 'clients' entries at {_CONFIG_PATH}")
    parsed = tuple(_validate_entry(i, e) for i, e in enumerate(entries))
    slugs = [c.client_slug for c in parsed]
    if len(slugs) != len(set(slugs)):
        dupes = [s for s in slugs if slugs.count(s) > 1]
        raise ValueError(f"clients.yaml has duplicate client_slugs: {sorted(set(dupes))}")
    logger.info(
        "clients.yaml loaded: %d entries (%d subject, %d monitored, %d retired)",
        len(parsed),
        sum(c.status == "subject" for c in parsed),
        sum(c.status == "monitored" for c in parsed),
        sum(c.status == "retired" for c in parsed),
    )
    return parsed


def subjects() -> list[Client]:
    return [c for c in clients() if c.status == "subject"]


def monitored() -> list[Client]:
    return [c for c in clients() if c.status == "monitored"]


def incumbent_slugs() -> list[str]:
    return [c.client_slug for c in clients() if c.market_tier == "incumbent" and c.status != "retired"]


def neobank_slugs() -> list[str]:
    return [c.client_slug for c in clients() if c.market_tier == "neobank" and c.status != "retired"]


def by_slug(slug: str) -> Client | None:
    for c in clients():
        if c.client_slug == slug:
            return c
    return None


def display_name(slug: str) -> str:
    c = by_slug(slug)
    if c is None:
        raise KeyError(f"unknown client_slug: {slug!r}")
    return c.display_name


def slug_for_display_name(name: str) -> str | None:
    target = name.strip().lower()
    for c in clients():
        if c.display_name.lower() == target:
            return c.client_slug
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    cs = clients()
    print(f"loaded {len(cs)} clients:")
    for c in cs:
        org = c.workos_org_id or "(unset)"
        print(f"  {c.client_slug:14s}  {c.display_name:14s}  {c.market_tier:9s}  {c.status:10s}  workos={org}")
    print()
    print(f"subjects:       {[c.client_slug for c in subjects()]}")
    print(f"monitored:      {[c.client_slug for c in monitored()]}")
    print(f"incumbents:     {incumbent_slugs()}")
    print(f"neobanks:       {neobank_slugs()}")
