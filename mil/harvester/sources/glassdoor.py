"""
glassdoor.py — Glassdoor engineering signal source.
Trust weight: 0.70. Status: STUB — WEEK 3.
Method: scrape (public pages only). Cadence: weekly.

Rationale: Internal engineering stress shows up on Glassdoor
weeks before public-facing failures manifest. Engineering team
sentiment is a leading indicator for operational outages.

Activate in Week 3. Do not build before then.

Zero Entanglement: no imports from internal modules.
"""
import logging
from pathlib import Path

import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.70


class GlassdoorSource(SignalSource):
    """
    STUB — Week 3 activation.
    Interface complete. Scraping method to be confirmed in Week 3.
    """
    source_name = "glassdoor"
    trust_weight = TRUST_WEIGHT
    status = "STUB"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        self.competitor_name = competitor

    def fetch(self):
        raise NotImplementedError("GlassdoorSource is STUB — activate in Week 3.")

    def parse(self, raw) -> list[dict]:
        raise NotImplementedError("GlassdoorSource is STUB.")

    def to_signal(self, parsed_item: dict) -> RawSignal:
        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            raw_data=parsed_item,
        )


def build_all_sources(apps_config_path: Path) -> list[GlassdoorSource]:
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False):
            sources.append(GlassdoorSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
