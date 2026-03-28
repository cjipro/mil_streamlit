"""
trustpilot.py — Trustpilot review scraper.
Trust weight: 0.80. Status: ACTIVE.
Method: public page scrape.
Note: skewed negative by design — bias is useful for failure detection.

Zero Entanglement: no imports from internal modules.
"""
import logging
import re
import json
from pathlib import Path
from datetime import datetime, timezone

import requests
import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.80

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}


class TrustpilotSource(SignalSource):
    source_name = "trustpilot"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        slug = competitor_config.get("trustpilot_slug", "")
        self.url = f"https://www.trustpilot.com/review/{slug}"

    def fetch(self) -> str:
        resp = requests.get(self.url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text

    def parse(self, raw: str) -> list[dict]:
        """
        Extract reviews from Trustpilot page.
        Trustpilot embeds review data as JSON-LD or in __NEXT_DATA__.
        """
        results = []

        # Try __NEXT_DATA__ JSON embed
        next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', raw, re.DOTALL)
        if next_data_match:
            try:
                data = json.loads(next_data_match.group(1))
                reviews = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("reviews", [])
                )
                for r in reviews:
                    results.append({
                        "rating": r.get("rating", {}).get("stars", 0),
                        "review_text": r.get("text", ""),
                        "title": r.get("title", ""),
                        "date": r.get("dates", {}).get("publishedDate", ""),
                        "verified": r.get("isVerified", False),
                        "source_url": self.url,
                        "parse_method": "next_data",
                    })
                return results
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # Fallback — regex on visible content
        review_blocks = re.findall(
            r'data-service-review-rating="(\d)"[^>]*>.*?<p[^>]*>([^<]{10,500})</p>',
            raw, re.DOTALL
        )
        for rating_str, text in review_blocks[:20]:
            results.append({
                "rating": int(rating_str),
                "review_text": text.strip(),
                "title": "",
                "date": "",
                "verified": False,
                "source_url": self.url,
                "parse_method": "regex_fallback",
            })

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


def build_all_sources(apps_config_path: Path) -> list[TrustpilotSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False) and comp.get("trustpilot_slug"):
            sources.append(TrustpilotSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
