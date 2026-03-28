"""
ft_cityam.py — Financial Times + City AM RSS signal source.
Trust weight: 0.90. Status: ACTIVE.
Method: RSS feeds (free, no auth).
Editorial verification adds weight — banking tech failures covered within hours.

Zero Entanglement: no imports from internal modules.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.90

FEEDS = {
    "financial_times": "https://www.ft.com/rss/home/uk",
    "city_am": "https://www.cityam.com/feed/",
}

BANKING_KEYWORDS = [
    "bank", "banking app", "banking", "migration", "outage",
    "IT failure", "mobile banking", "fintech",
    "NatWest", "Lloyds", "HSBC", "Monzo", "Revolut", "Barclays",
]

COMPETITOR_KEYWORDS = {
    "NatWest": ["natwest"],
    "Lloyds": ["lloyds", "lbg", "lloyds bank"],
    "HSBC": ["hsbc"],
    "Monzo": ["monzo"],
    "Revolut": ["revolut"],
    "Barclays": ["barclays"],
}


class FTCityAMSource(SignalSource):
    """
    Single source class covering both FT and City AM feeds.
    Instantiated once per competitor — scans all feeds for mentions.
    """
    source_name = "ft_cityam"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        self.competitor_keywords = COMPETITOR_KEYWORDS.get(competitor, [competitor.lower()])

    def fetch(self) -> list[dict]:
        try:
            import feedparser
        except ImportError:
            raise ImportError("feedparser not installed. Run: pip install feedparser")

        all_entries = []
        for feed_name, feed_url in FEEDS.items():
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    all_entries.append({
                        "feed_source": feed_name,
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "tags": [t.get("term", "") for t in entry.get("tags", [])],
                    })
            except Exception as exc:
                logger.warning("[ft_cityam] feed %s failed: %s", feed_name, exc)

        return all_entries

    def parse(self, raw: list[dict]) -> list[dict]:
        """Filter to entries that mention this competitor."""
        results = []
        for entry in raw:
            text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()

            competitor_mentioned = any(kw in text for kw in self.competitor_keywords)
            banking_relevant = any(kw.lower() in text for kw in BANKING_KEYWORDS)

            if competitor_mentioned and banking_relevant:
                entry["competitor_mentioned"] = self.competitor
                results.append(entry)

        return results

    def to_signal(self, parsed_item: dict) -> RawSignal:
        title = parsed_item.get("title", "").lower()
        is_outage = any(kw in title for kw in ["outage", "failure", "down", "it failure", "disruption"])
        severity_class = "P1" if is_outage else "P2"

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            raw_data=parsed_item,
        )


def build_all_sources(apps_config_path: Path) -> list[FTCityAMSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False):
            sources.append(FTCityAMSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
