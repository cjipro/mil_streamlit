"""
reddit.py — Reddit signal source via public JSON endpoints (no OAuth).
Trust weight: 0.85. Status: ACTIVE.
Jax filter required — coordinated narratives appear here.

No credentials required. Uses Reddit's public .json API:
  - https://www.reddit.com/r/{subreddit}/new.json?limit=50
  - https://www.reddit.com/search.json?q={query}&sort=new&t=day&limit=50

Zero Entanglement: no imports from internal modules.
"""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.85
REQUEST_DELAY = 2.0   # seconds between requests (Reddit rate limit: ~1 req/sec)

HEADERS = {
    "User-Agent": "MIL-Harvester/1.0 (public market intelligence; contact: mil@cjipro.com)",
    "Accept": "application/json",
}

SUBREDDITS = [
    "UKPersonalFinance",
    "Banking",
    "Monzo",
    "Revolut",
    "UKBanks",
    "barclayscards",
]

COMPETITOR_KEYWORDS = {
    "NatWest": ["natwest"],
    "Lloyds":  ["lloyds", "lbg", "lloyds bank"],
    "HSBC":    ["hsbc"],
    "Monzo":   ["monzo"],
    "Revolut": ["revolut"],
    "Barclays": ["barclays"],
}

BANKING_KEYWORDS = [
    "bank", "banking", "app", "payment", "transfer", "login",
    "outage", "down", "not working", "broken", "error", "issue",
]


def _reddit_get(url: str, params: dict = None) -> dict:
    """GET a Reddit JSON endpoint with rate-limit delay."""
    time.sleep(REQUEST_DELAY)
    resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _extract_posts(data: dict) -> list[dict]:
    """Extract post list from Reddit listing JSON."""
    return [child["data"] for child in data.get("data", {}).get("children", [])
            if child.get("kind") == "t3"]


class RedditSource(SignalSource):
    source_name = "reddit"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict, env_path: Path = None):
        super().__init__(competitor, competitor_config)
        self.keywords = COMPETITOR_KEYWORDS.get(competitor, [competitor.lower()])

    def fetch(self) -> list[dict]:
        """
        Fetch posts from:
        1. Competitor keyword search across subreddits (new, past 7 days)
        2. Browse new posts in each subreddit, filter client-side
        Returns list of post dicts with review-compatible fields.
        """
        seen_ids: set[str] = set()
        results: list[dict] = []

        def _add(post: dict) -> None:
            pid = post.get("id", "")
            if not pid or pid in seen_ids:
                return
            text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
            if not any(kw in text for kw in self.keywords):
                return
            seen_ids.add(pid)
            results.append({
                "post_id":      pid,
                "title":        post.get("title", ""),
                "body":         post.get("selftext", "")[:1000],
                "score":        post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "subreddit":    post.get("subreddit", ""),
                "url":          f"https://reddit.com{post.get('permalink', '')}",
                "date":         datetime.fromtimestamp(
                                    post.get("created_utc", 0), tz=timezone.utc
                                ).strftime("%Y-%m-%d"),
                "source":       "reddit",
                "competitor":   self.competitor.lower(),
            })

        # 1. Global search for competitor keywords (past week)
        query = " OR ".join(self.keywords)
        for sort in ("new", "top"):
            try:
                data = _reddit_get(
                    "https://www.reddit.com/search.json",
                    params={"q": query, "sort": sort, "t": "week", "limit": 50},
                )
                for post in _extract_posts(data):
                    _add(post)
            except Exception as exc:
                logger.warning("[reddit] search %s/%s failed: %s", self.competitor, sort, exc)

        # 2. Browse new posts in each relevant subreddit, filter client-side
        for sub in SUBREDDITS:
            try:
                data = _reddit_get(
                    f"https://www.reddit.com/r/{sub}/new.json",
                    params={"limit": 50, "t": "day"},
                )
                for post in _extract_posts(data):
                    _add(post)
            except Exception as exc:
                logger.warning("[reddit] r/%s browse failed: %s", sub, exc)

        logger.info("[reddit] %s — %d posts collected", self.competitor, len(results))
        return results

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw

    def to_signal(self, parsed_item: dict) -> RawSignal:
        num_comments = parsed_item.get("num_comments", 0)
        if num_comments > 50:
            severity_class = "P1"
        elif num_comments > 20:
            severity_class = "P2"
        else:
            severity_class = "P2"

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            jax_flags=[],
            jax_clean=True,
            raw_data=parsed_item,
        )


def build_all_sources(apps_config_path: Path, env_path: Path = None) -> list[RedditSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False):
            sources.append(RedditSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
