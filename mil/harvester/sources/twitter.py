"""
twitter.py — Twitter/X Filtered Stream source.
Trust weight: 0.60. Status: STUB — API PLAN REQUIRED.

IMPORTANT: twitter.com/i/premium does NOT grant API access.
API access requires developer.twitter.com Basic plan ($100/mo) minimum.
Filtered Stream requires a REDACTED from a paid API plan.

To activate:
  1. Purchase Basic plan at developer.twitter.com
  2. Set twitter_x.enabled: true in mil/config/apps_config.yaml
  3. Update TWITTER_BEARER_TOKEN in .env with new token
  4. Change status = "ACTIVE" in this class
  5. Run: py mil/tests/test_filtered_stream.py to verify

Current test results (2026-03-28):
  - REDACTED auth: PASS (HTTP 200 on rules endpoint)
  - Filtered Stream open: FAIL (HTTP 402 — credits depleted)
  - Conclusion: Token valid. API plan required for stream access.

Jax filter required — first-mover signal but highest noise source.

Zero Entanglement: no imports from internal modules.
"""
import os
import json
import logging
import urllib.parse
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.60

STREAM_URL = "https://api.twitter.com/2/tweets/search/stream"
RULES_URL = "https://api.twitter.com/2/tweets/search/stream/rules"
RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterSource(SignalSource):
    """
    STUB — interface complete, ready to activate when API plan purchased.

    Architecture:
    - Primary: Filtered Stream (real-time, zero latency)
    - Fallback: Recent search with credit check guard
    - Stream rules defined per-competitor in apps_config.yaml twitter_keywords

    Jax filter handles: coordinated bot campaigns, fake trending,
    astroturfing narratives.
    """
    source_name = "twitter_x"
    trust_weight = TRUST_WEIGHT
    status = "STUB"

    def __init__(self, competitor: str, competitor_config: dict, env_path: Path = None):
        super().__init__(competitor, competitor_config)
        self.keywords = competitor_config.get("twitter_keywords", [competitor])
        if env_path:
            load_dotenv(env_path)
        raw_token = os.getenv("TWITTER_BEARER_TOKEN", "")
        self.bearer_token = urllib.parse.unquote(raw_token)

    def _headers(self) -> dict:
        return {"Authorization": f"REDACTED{self.bearer_token}"}

    def _credit_check(self) -> bool:
        """Check if recent search credits are available before calling."""
        import requests
        resp = requests.get(
            RECENT_SEARCH_URL,
            headers=self._headers(),
            params={"query": "test", "max_results": 10},
            timeout=10,
        )
        return resp.status_code == 200

    def fetch(self):
        raise NotImplementedError(
            "TwitterSource is STUB — API plan required. "
            "See docstring for activation instructions."
        )

    def parse(self, raw) -> list[dict]:
        raise NotImplementedError("TwitterSource is STUB.")

    def to_signal(self, parsed_item: dict) -> RawSignal:
        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            jax_flags=parsed_item.get("jax_flags", []),
            jax_clean=parsed_item.get("jax_clean", True),
            raw_data=parsed_item,
        )


def build_all_sources(apps_config_path: Path, env_path: Path = None) -> list[TwitterSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False):
            sources.append(TwitterSource(
                competitor=comp["name"],
                competitor_config=comp,
                env_path=env_path,
            ))
    return sources
