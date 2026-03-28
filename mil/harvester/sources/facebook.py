"""
facebook.py — Facebook public page signal source.
Trust weight: 0.75. Status: STUB.
Method: TODO — public page scrape (Playwright or facebook-scraper).
Demographic alignment: 35-55 skew — vulnerable customer cohort.
Jax filter required.

Implementation deferred to Day 30 review.
See SOVEREIGN_BRIEF.md Blind Spot Register BS-005.
Do NOT use Meta Graph API — public page scraping only.

Zero Entanglement: no imports from internal modules.
"""
import logging
from pathlib import Path

import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.75


class FacebookSource(SignalSource):
    """
    STUB — interface complete, implementation deferred.

    Options under consideration at Day 30 review:
    - Playwright/headless browser (reliable, adds browser dependency)
    - facebook-scraper library (lighter, potentially fragile)

    Demographic note: Facebook 35-55 skew aligns with vulnerable customer
    cohort in Day 90 vision. Priority signal when activated.
    """
    source_name = "facebook"
    trust_weight = TRUST_WEIGHT
    status = "STUB"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        self.page = competitor_config.get("facebook_page", "")

    def fetch(self):
        raise NotImplementedError(
            "FacebookSource is a STUB. Implementation deferred to Day 30 review. "
            "See SOVEREIGN_BRIEF.md BS-005."
        )

    def parse(self, raw) -> list[dict]:
        raise NotImplementedError("FacebookSource is a STUB.")

    def to_signal(self, parsed_item: dict) -> RawSignal:
        raise NotImplementedError("FacebookSource is a STUB.")


def build_all_sources(apps_config_path: Path) -> list[FacebookSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False) and comp.get("facebook_page"):
            sources.append(FacebookSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
