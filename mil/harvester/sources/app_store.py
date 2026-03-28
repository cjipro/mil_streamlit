"""
app_store.py — Apple App Store review source via iTunes RSS.
Trust weight: 0.90. Status: ACTIVE.
Method: iTunes RSS feed (free, no auth required).
Version field is critical — pinpoints exact update that caused failure.

Zero Entanglement: no imports from internal modules.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.90
BASE_URL = "https://itunes.apple.com/gb/rss/customerreviews/id={APP_ID}/sortBy=mostRecent/json"


class AppStoreSource(SignalSource):
    source_name = "app_store"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        self.app_id = competitor_config.get("app_store_id", "")
        self.url = BASE_URL.format(APP_ID=self.app_id)

    def fetch(self) -> dict:
        resp = requests.get(self.url, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def parse(self, raw: dict) -> list[dict]:
        entries = raw.get("feed", {}).get("entry", [])
        # First entry is app metadata, not a review
        if entries and "im:name" in entries[0]:
            entries = entries[1:]
        results = []
        for entry in entries:
            try:
                results.append({
                    "rating": int(entry.get("im:rating", {}).get("label", 0)),
                    "title": entry.get("title", {}).get("label", ""),
                    "review": entry.get("content", {}).get("label", ""),
                    "version": entry.get("im:version", {}).get("label", ""),
                    "date": entry.get("updated", {}).get("label", ""),
                    "author": entry.get("author", {}).get("name", {}).get("label", ""),
                })
            except Exception as exc:
                logger.debug("[app_store] parse item error: %s", exc)
        return results

    def to_signal(self, parsed_item: dict) -> RawSignal:
        rating = parsed_item.get("rating", 3)
        severity_class = "INFO"
        if rating <= 1:
            severity_class = "P1"
        elif rating <= 2:
            severity_class = "P2"

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            raw_data=parsed_item,
        )


def build_all_sources(apps_config_path: Path) -> list[AppStoreSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False) and comp.get("app_store_id"):
            sources.append(AppStoreSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
