"""
downdetector.py — Downdetector scraper source.
Trust weight: 0.95. Status: ACTIVE.
Highest trust — real-time structured outage reports.
Often first mover before Twitter peaks.

Zero Entanglement: no imports from internal modules.
"""
import time
import random
import logging
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.95
RATE_LIMIT_SECONDS = 30

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# Severity thresholds (spike multiplier vs baseline)
P0_MULTIPLIER = 5.0
P1_MULTIPLIER = 2.0
P2_MULTIPLIER = 1.5

_last_request_time: dict[str, float] = {}


class DowndetectorSource(SignalSource):
    source_name = "downdetector"
    trust_weight = TRUST_WEIGHT
    status = "ACTIVE"

    def __init__(self, competitor: str, competitor_config: dict):
        super().__init__(competitor, competitor_config)
        self.slug = competitor_config.get("downdetector_slug", "")
        self.url = f"https://downdetector.co.uk/status/{self.slug}/"

    def fetch(self) -> str:
        # Rate limiting — 30s minimum between requests per slug
        now = time.time()
        last = _last_request_time.get(self.slug, 0)
        wait = RATE_LIMIT_SECONDS - (now - last)
        if wait > 0:
            logger.debug("[downdetector] Rate limiting %s — waiting %.1fs", self.slug, wait)
            time.sleep(wait)

        ua = random.choice(USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-GB,en;q=0.9",
        }
        resp = requests.get(self.url, headers=headers, timeout=15)
        resp.raise_for_status()
        _last_request_time[self.slug] = time.time()
        return resp.text

    def parse(self, raw: str) -> list[dict]:
        """
        Extract report count from Downdetector page.
        Downdetector embeds chart data as JSON in a script tag.
        Falls back to regex on the visible count if JSON not found.
        """
        results = []

        # Try JSON embed first (more reliable)
        json_match = re.search(
            r'window\.DD\.currentStatus\s*=\s*(\{[^;]+\})',
            raw, re.DOTALL
        )
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                results.append({
                    "current_report_count": data.get("reports", 0),
                    "status": data.get("status", "unknown"),
                    "baseline_report_count": data.get("baseline", 0),
                    "source_url": self.url,
                    "parse_method": "json_embed",
                })
                return results
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback — look for report count in page text
        count_match = re.search(r'(\d+)\s+(?:reports?|problem reports?)\s+in\s+the\s+last\s+24\s+hours', raw, re.IGNORECASE)
        count = int(count_match.group(1)) if count_match else 0

        status_match = re.search(r'class="[^"]*status-[^"]*"[^>]*>([^<]+)<', raw)
        status_text = status_match.group(1).strip() if status_match else "unknown"

        results.append({
            "current_report_count": count,
            "status": status_text,
            "baseline_report_count": 0,   # baseline not available in fallback
            "source_url": self.url,
            "parse_method": "regex_fallback",
        })
        return results

    def to_signal(self, parsed_item: dict) -> RawSignal:
        current = parsed_item.get("current_report_count", 0)
        baseline = parsed_item.get("baseline_report_count", 0)

        spike_detected = False
        severity_class = "INFO"
        spike_multiplier = None

        if baseline > 0:
            spike_multiplier = current / baseline
            if spike_multiplier >= P0_MULTIPLIER:
                severity_class = "P0"
                spike_detected = True
            elif spike_multiplier >= P1_MULTIPLIER:
                severity_class = "P1"
                spike_detected = True
            elif spike_multiplier >= P2_MULTIPLIER:
                severity_class = "P2"
                spike_detected = True

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            spike_detected=spike_detected,
            raw_data={
                "current_report_count": current,
                "baseline_report_count": baseline,
                "spike_multiplier": spike_multiplier,
                "status": parsed_item.get("status"),
                "source_url": parsed_item.get("source_url"),
                "parse_method": parsed_item.get("parse_method"),
            },
        )


def build_all_sources(apps_config_path: Path) -> list[DowndetectorSource]:
    """Build one DowndetectorSource per active competitor."""
    with open(apps_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = []
    for comp in config.get("competitors", []):
        if comp.get("active", False) and comp.get("downdetector_slug"):
            sources.append(DowndetectorSource(
                competitor=comp["name"],
                competitor_config=comp,
            ))
    return sources
