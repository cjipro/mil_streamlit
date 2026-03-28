"""
reddit.py — Reddit signal source via official API (PRAW).
Trust weight: 0.85. Status: ACTIVE.
Jax filter required — coordinated narratives appear here.

Credentials: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET from .env

Zero Entanglement: no imports from internal modules.
"""
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.85

SUBREDDITS = [
    "UKPersonalFinance",
    "Banking",
    "Monzo",
    "Revolut",
    "UKBanks",
    "barclayscards",
]


class RedditSource(SignalSource):
    source_name = "reddit"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict, env_path: Path = None):
        super().__init__(competitor, competitor_config)
        self.keywords = competitor_config.get("reddit_mentions", [competitor])
        if env_path:
            load_dotenv(env_path)
        self.client_id = os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")

    def fetch(self) -> list[dict]:
        try:
            import praw
        except ImportError:
            raise ImportError("praw not installed. Run: pip install praw")

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent="MIL-Harvester/1.0 (public market intelligence)",
        )

        results = []
        query = " OR ".join(f'"{kw}"' for kw in self.keywords)

        for sub_name in SUBREDDITS:
            try:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.search(query, sort="new", limit=25, time_filter="day"):
                    results.append({
                        "title": post.title,
                        "body": post.selftext[:1000],
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                        "subreddit": sub_name,
                        "url": f"https://reddit.com{post.permalink}",
                        "post_id": post.id,
                    })
            except Exception as exc:
                logger.warning("[reddit] subreddit %s search failed: %s", sub_name, exc)

        return results

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw  # already structured in fetch()

    def to_signal(self, parsed_item: dict) -> RawSignal:
        # High comment count or negative score = elevated
        num_comments = parsed_item.get("num_comments", 0)
        severity_class = "INFO"
        if num_comments > 50:
            severity_class = "P1"
        elif num_comments > 20:
            severity_class = "P2"

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            jax_flags=[],   # Jax filter applied by voice_intelligence_agent
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
                env_path=env_path,
            ))
    return sources
