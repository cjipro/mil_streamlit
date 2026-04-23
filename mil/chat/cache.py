"""
mil/chat/cache.py — MIL-47.

Content-addressable query cache. Hashes (query, intent, entities) to a
cache key; serves prior synthesis results within a configurable TTL.

Storage: mil/data/ask_query_cache.json — compact JSON object, not JSONL,
so entries can be rewritten on expiry without full-file rewrites of
unrelated rows. File is small by design (<10k entries, LRU-trimmed).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent
_CACHE_PATH  = _MIL_ROOT / "data" / "ask_query_cache.json"

DEFAULT_TTL_SECONDS = 3600  # 1 hour — short enough to reflect daily pipeline runs
MAX_ENTRIES         = 5000


@dataclass(frozen=True)
class CacheKey:
    query: str
    intent: str
    entities_hash: str

    def digest(self) -> str:
        return hashlib.sha256(
            f"{self.query}|{self.intent}|{self.entities_hash}".encode("utf-8")
        ).hexdigest()[:16]


def _entities_hash(entities: dict[str, Any]) -> str:
    stable = json.dumps(
        {k: v for k, v in entities.items() if not k.startswith("_")},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:12]


def key_for(query: str, intent: str, entities: dict[str, Any]) -> CacheKey:
    return CacheKey(
        query=query.strip().lower(),
        intent=intent,
        entities_hash=_entities_hash(entities or {}),
    )


def _read_store() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    try:
        with _CACHE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[cache] read failed, starting fresh: %s", exc)
        return {}


def _write_store(store: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)
    tmp.replace(_CACHE_PATH)


def get(key: CacheKey, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Optional[dict]:
    """Return cached payload if fresh, else None."""
    store = _read_store()
    entry = store.get(key.digest())
    if not entry:
        return None
    if time.time() - entry.get("written_at", 0) > ttl_seconds:
        return None
    return entry.get("payload")


def put(key: CacheKey, payload: dict) -> None:
    """Write payload to cache. Evicts oldest entries if above MAX_ENTRIES."""
    store = _read_store()
    store[key.digest()] = {"written_at": time.time(), "payload": payload}

    if len(store) > MAX_ENTRIES:
        sorted_keys = sorted(store.items(), key=lambda kv: kv[1].get("written_at", 0))
        for k, _ in sorted_keys[: len(store) - MAX_ENTRIES]:
            store.pop(k, None)

    _write_store(store)


def clear() -> None:
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
