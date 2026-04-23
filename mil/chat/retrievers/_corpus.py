"""
mil/chat/retrievers/_corpus.py — shared review-corpus loader.

Loads and normalises every enriched review file under
mil/data/historical/enriched/ into a flat list of dicts.
Used by BM25Retriever and EmbeddingRetriever.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_MIL_ROOT = Path(__file__).parent.parent.parent
CORPUS_DIR = _MIL_ROOT / "data" / "historical" / "enriched"


@lru_cache(maxsize=1)
def load_review_records() -> list[dict]:
    """Return every enriched review as a normalised dict."""
    records: list[dict] = []
    if not CORPUS_DIR.exists():
        logger.warning("[corpus] dir missing: %s", CORPUS_DIR)
        return records

    for path in sorted(CORPUS_DIR.glob("*_enriched.json")):
        try:
            with path.open(encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning("[corpus] failed to load %s: %s", path.name, exc)
            continue

        # Enriched files wrap records under a container. Legacy pure-list files
        # are still accepted as a fallback.
        if isinstance(payload, dict):
            rows = payload.get("records", [])
            src = payload.get("source") or path.stem.rpartition("_")[0]
            comp = (payload.get("competitor") or "unknown").lower()
        elif isinstance(payload, list):
            rows = payload
            stem = path.stem.replace("_enriched", "")
            src, _, comp = stem.rpartition("_")
            if not src:
                src, comp = stem, "unknown"
        else:
            continue

        for i, row in enumerate(rows):
            text = f"{row.get('title') or ''} {row.get('review') or row.get('content') or ''}".strip()
            if not text:
                continue
            records.append({
                "id":          f"{path.stem}#{i}",
                "text":        text,
                "source":      src,
                "competitor":  comp.lower() if isinstance(comp, str) else "unknown",
                "issue_type":  row.get("issue_type"),
                "severity":    row.get("severity_class"),
                "date":        row.get("date"),
                "rating":      row.get("rating"),
                "journey":     row.get("customer_journey"),
            })

    logger.info("[corpus] loaded %d reviews from %s", len(records), CORPUS_DIR)
    return records


def corpus_mtime() -> float:
    """Max mtime across corpus files — for cache invalidation."""
    if not CORPUS_DIR.exists():
        return 0.0
    mtimes = [p.stat().st_mtime for p in CORPUS_DIR.glob("*_enriched.json")]
    return max(mtimes) if mtimes else 0.0


def reload() -> None:
    load_review_records.cache_clear()
