"""
google_play.py — Google Play review source.
Trust weight: 0.90. Status: ACTIVE.
Method: google-play-scraper library.

Zero Entanglement: no imports from internal modules.
"""
import logging
from pathlib import Path

import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.90
# 100 reviews per page × 5 pages = 500 reviews. Same rationale as AppStoreSource:
# covers ~6 days of observed review velocity with margin against cron drift.
MAX_PAGES = 5
PAGE_SIZE = 100


class GooglePlaySource(SignalSource):
    source_name = "google_play"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        self.package_id = competitor_config.get("google_play_id", "")
        self.max_pages = int(competitor_config.get("google_play_max_pages", MAX_PAGES))

    def fetch(self) -> list:
        try:
            from google_play_scraper import reviews, Sort
        except ImportError:
            raise ImportError("google-play-scraper not installed. Run: pip install google-play-scraper")

        all_results: list = []
        token = None
        page = 0
        for page in range(1, self.max_pages + 1):
            kwargs: dict = {
                "lang": "en",
                "country": "gb",
                "sort": Sort.NEWEST,
                "count": PAGE_SIZE,
            }
            if token is not None:
                kwargs["continuation_token"] = token
            try:
                result, token = reviews(self.package_id, **kwargs)
            except Exception as exc:
                logger.warning("[google_play] %s page=%d fetch failed: %s — stopping pagination",
                               self.competitor, page, exc)
                break
            if not result:
                break
            all_results.extend(result)
            # google-play-scraper returns a _ContinuationToken object; .token is None
            # when no more pages remain.
            if token is None or getattr(token, "token", None) is None:
                break
        logger.info("[google_play] %s — paginated %d pages → %d reviews",
                    self.competitor, page, len(all_results))
        return all_results

    def parse(self, raw: list) -> list[dict]:
        results = []
        for item in raw:
            try:
                results.append({
                    "rating": item.get("score", 3),
                    "content": item.get("content", ""),
                    "thumbsUpCount": item.get("thumbsUpCount", 0),
                    "reviewCreatedVersion": item.get("reviewCreatedVersion", ""),
                    "at": item.get("at", "").isoformat() if hasattr(item.get("at"), "isoformat") else str(item.get("at", "")),
                    "userName": item.get("userName", ""),
                })
            except Exception as exc:
                logger.debug("[google_play] parse item error: %s", exc)
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


def build_all_sources(apps_config_path: Path) -> list[GooglePlaySource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False) and comp.get("google_play_id"):
            sources.append(GooglePlaySource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
