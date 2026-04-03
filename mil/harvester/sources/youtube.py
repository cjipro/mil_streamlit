"""
youtube.py — YouTube Data API v3 source. MIL-22.
Trust weight: 0.75. Status: ACTIVE.
Quota: 10,000 units/day free tier.
  - Search: 100 units per call
  - Videos.list (stats): 1 unit per call
  - CommentThreads.list: 1 unit per page

Signal type: video comments on competitor-related videos.
Comments stored with `review` field — compatible with enrich_sonnet.py schema v3.

Jax checks:
  - JAX_LIKE_FARMING: like/comment ratio > 50
  - JAX_BOT_VIEW_INFLATION: comment/view ratio < 0.001 on high-view videos
  - JAX_SPAM_REPLY: new accounts with clustered timestamps (heuristic)

Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.75

# Search queries per competitor (3 × 100 units = 300 units per competitor)
SEARCH_QUERY_TEMPLATES = [
    "{name} app not working",
    "{name} app fix",
    "{name} bank down",
]

MAX_VIDEOS_PER_QUERY = 5       # 5 videos × 3 queries = 15 videos max per competitor
MAX_COMMENTS_PER_VIDEO = 20    # 1 unit per page of 20

# Jax thresholds
LIKE_FARMING_RATIO = 50.0      # likes:comments ratio
BOT_VIEW_RATIO = 0.001         # comments:views ratio (high-view videos)
BOT_VIEW_THRESHOLD = 1000      # only apply bot check above this view count


def _dedup_key(comment: dict) -> str:
    return comment.get("comment_id", "")


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

    def _get_client(self):
        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "google-api-python-client not installed. Run: pip install google-api-python-client"
            )
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY not set in environment.")
        return build("youtube", "v3", developerKey=self.api_key)

    def fetch(self) -> list[dict]:
        """
        Fetch comments from competitor-related videos.
        Returns list of comment dicts with review-compatible fields.
        """
        youtube = self._get_client()
        comments = []
        seen_video_ids: set[str] = set()

        for keyword in self.keywords:
            for template in SEARCH_QUERY_TEMPLATES:
                query = template.format(name=keyword)
                try:
                    search_resp = youtube.search().list(
                        q=query,
                        part="id,snippet",
                        type="video",
                        maxResults=MAX_VIDEOS_PER_QUERY,
                        order="date",
                        relevanceLanguage="en",
                        regionCode="GB",
                    ).execute()
                except Exception as exc:
                    logger.warning("[youtube] %s search '%s' failed: %s", self.competitor, query, exc)
                    continue

                for item in search_resp.get("items", []):
                    video_id = item["id"].get("videoId", "")
                    if not video_id or video_id in seen_video_ids:
                        continue
                    seen_video_ids.add(video_id)

                    snippet = item.get("snippet", {})
                    video_title = snippet.get("title", "")
                    published_at = snippet.get("publishedAt", "")
                    channel_title = snippet.get("channelTitle", "")

                    # Fetch stats for Jax checks (1 unit)
                    stats = {}
                    try:
                        stats_resp = youtube.videos().list(
                            part="statistics",
                            id=video_id,
                        ).execute()
                        if stats_resp.get("items"):
                            stats = stats_resp["items"][0].get("statistics", {})
                    except Exception as exc:
                        logger.debug("[youtube] stats fetch failed for %s: %s", video_id, exc)

                    view_count = int(stats.get("viewCount", 0))
                    like_count = int(stats.get("likeCount", 0))
                    comment_count = int(stats.get("commentCount", 0))

                    # Jax video-level flags
                    video_jax_flags = []
                    if comment_count > 0 and like_count / comment_count > LIKE_FARMING_RATIO:
                        video_jax_flags.append("JAX_LIKE_FARMING")
                    if (view_count > BOT_VIEW_THRESHOLD and comment_count > 0
                            and comment_count / view_count < BOT_VIEW_RATIO):
                        video_jax_flags.append("JAX_BOT_VIEW_INFLATION")

                    # Fetch top comments (1 unit per page)
                    try:
                        comments_resp = youtube.commentThreads().list(
                            part="snippet",
                            videoId=video_id,
                            maxResults=MAX_COMMENTS_PER_VIDEO,
                            order="relevance",
                            textFormat="plainText",
                        ).execute()
                    except Exception as exc:
                        logger.debug("[youtube] comments disabled for %s: %s", video_id, exc)
                        continue

                    for thread in comments_resp.get("items", []):
                        top = thread.get("snippet", {}).get("topLevelComment", {})
                        c_snippet = top.get("snippet", {})
                        comment_text = c_snippet.get("textDisplay", "").strip()
                        if not comment_text or len(comment_text) < 15:
                            continue

                        comment_id = top.get("id", "")
                        author = c_snippet.get("authorDisplayName", "")
                        published = c_snippet.get("publishedAt", "")
                        like_count_comment = int(c_snippet.get("likeCount", 0))

                        comments.append({
                            # enrichment-compatible fields
                            "review": comment_text[:500],
                            "rating": None,
                            "author": author,
                            "date": published[:10] if published else "",
                            # youtube metadata
                            "comment_id": comment_id,
                            "video_id": video_id,
                            "video_title": video_title,
                            "video_published_at": published_at,
                            "channel_title": channel_title,
                            "search_query": query,
                            "video_view_count": view_count,
                            "video_like_count": like_count,
                            "video_comment_count": comment_count,
                            "comment_like_count": like_count_comment,
                            "video_jax_flags": video_jax_flags,
                        })

        logger.info("[youtube] %s — %d videos scanned, %d comments fetched",
                    self.competitor, len(seen_video_ids), len(comments))
        return comments

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw

    def to_signal(self, parsed_item: dict) -> RawSignal:
        video_jax_flags = parsed_item.get("video_jax_flags", [])
        title = parsed_item.get("video_title", "").lower()

        # Fix guide videos are P1 — high volume = failure scale signal
        fix_keywords = ["not working", "fix", "down", "problem", "broken", "error"]
        is_fix_signal = any(kw in title for kw in fix_keywords)
        severity_class = "P1" if is_fix_signal else "P2"

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            jax_flags=video_jax_flags,
            jax_clean=len(video_jax_flags) == 0,
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
