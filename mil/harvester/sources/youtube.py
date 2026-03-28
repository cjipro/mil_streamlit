"""
youtube.py — YouTube Data API v3 source.
Trust weight: 0.75. Status: ACTIVE.
Quota: 10,000 units/day free tier (Google Cloud).
Jax filter required — like farming, spam replies, bot view inflation.

Credentials: YOUTUBE_API_KEY from .env

Zero Entanglement: no imports from internal modules.
"""
import os
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.75

FIX_GUIDE_KEYWORDS = [
    "app not working", "app fix", "bank app problem", "bank down fix"
]

APP_REVIEW_KEYWORDS = [
    "app review", "banking app review", "mobile banking review"
]

# Jax thresholds
LIKE_FARMING_RATIO_THRESHOLD = 50.0   # likes:comments ratio anomaly
BOT_VIEW_RATIO_THRESHOLD = 0.001      # comment:view ratio too low


class YouTubeSource(SignalSource):
    source_name = "youtube"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict, env_path: Path = None):
        super().__init__(competitor, competitor_config)
        self.keywords = competitor_config.get("youtube_channel_keywords", [competitor])
        if env_path:
            load_dotenv(env_path)
        self.api_key = os.getenv("YOUTUBE_API_KEY", "")

    def fetch(self) -> list[dict]:
        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("google-api-python-client not installed. Run: pip install google-api-python-client")

        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY not set in environment.")

        youtube = build("youtube", "v3", developerKey=self.api_key)
        results = []

        for keyword in self.keywords:
            try:
                # Search for relevant videos
                search_queries = [
                    f"{keyword} app not working",
                    f"{keyword} app fix",
                    f"{keyword} down",
                ]
                for query in search_queries:
                    search_resp = youtube.search().list(
                        q=query,
                        part="id,snippet",
                        type="video",
                        maxResults=10,
                        order="date",
                        relevanceLanguage="en",
                        regionCode="GB",
                    ).execute()

                    for item in search_resp.get("items", []):
                        video_id = item["id"].get("videoId", "")
                        if not video_id:
                            continue
                        snippet = item.get("snippet", {})

                        # Fetch statistics for Jax checks
                        stats_resp = youtube.videos().list(
                            part="statistics",
                            id=video_id,
                        ).execute()
                        stats = {}
                        if stats_resp.get("items"):
                            stats = stats_resp["items"][0].get("statistics", {})

                        results.append({
                            "video_id": video_id,
                            "title": snippet.get("title", ""),
                            "description": snippet.get("description", "")[:500],
                            "published_at": snippet.get("publishedAt", ""),
                            "channel_title": snippet.get("channelTitle", ""),
                            "search_query": query,
                            "view_count": int(stats.get("viewCount", 0)),
                            "like_count": int(stats.get("likeCount", 0)),
                            "comment_count": int(stats.get("commentCount", 0)),
                        })
            except Exception as exc:
                logger.warning("[youtube] keyword '%s' search failed: %s", keyword, exc)

        return results

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw

    def _jax_check(self, item: dict) -> list[str]:
        """YouTube-specific Jax checks. Returns list of flag strings."""
        flags = []
        likes = item.get("like_count", 0)
        comments = item.get("comment_count", 0)
        views = item.get("view_count", 0)

        if comments > 0 and likes / comments > LIKE_FARMING_RATIO_THRESHOLD:
            flags.append("JAX_LIKE_FARMING")

        if views > 1000 and comments > 0 and comments / views < BOT_VIEW_RATIO_THRESHOLD:
            flags.append("JAX_BOT_VIEW_INFLATION")

        return flags

    def to_signal(self, parsed_item: dict) -> RawSignal:
        jax_flags = self._jax_check(parsed_item)
        title = parsed_item.get("title", "").lower()

        is_fix_guide = any(kw in title for kw in FIX_GUIDE_KEYWORDS)
        severity_class = "P2" if is_fix_guide else "INFO"

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            jax_flags=jax_flags,
            jax_clean=len(jax_flags) == 0,
            raw_data=parsed_item,
        )


def build_all_sources(apps_config_path: Path, env_path: Path = None) -> list[YouTubeSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False):
            sources.append(YouTubeSource(
                competitor=comp["name"],
                competitor_config=comp,
                env_path=env_path,
            ))
    return sources
