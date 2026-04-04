"""
downdetector.py — Downdetector scraper source.
Trust weight: 0.95. Status: ACTIVE.
Highest trust — real-time structured outage reports.
Often first mover before Twitter peaks.

Zero Entanglement: no imports from internal modules.
"""
import time
import logging
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .base import SignalSource, RawSignal

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 0.95
RATE_LIMIT_SECONDS = 3          # global delay between any two DD requests (same IP)


def _fetch_html(url: str) -> str:
    """Fetch page HTML via cloudscraper to bypass Cloudflare bot protection."""
    import cloudscraper
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    resp = scraper.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text

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
        # Global rate limiting — minimum gap between any two DD requests
        now = time.time()
        last = _last_request_time.get("_global", 0)
        wait = RATE_LIMIT_SECONDS - (now - last)
        if wait > 0:
            logger.debug("[downdetector] Rate limiting — waiting %.1fs", wait)
            time.sleep(wait)

        html = _fetch_html(self.url)
        _last_request_time["_global"] = time.time()
        return html

    def parse(self, raw: str) -> list[dict]:
        """
        Extract outage status from DownDetector page HTML.

        Primary signal: window.PogoConfig.outage (bool) — most reliable.
        Secondary: H1 status text for warning/danger distinction.
        Tertiary: most-reported-problems breakdown for issue context.
        """
        from bs4 import BeautifulSoup

        # 1. PogoConfig — primary status source
        outage = False
        pogo_match = re.search(r'window\.PogoConfig\s*=\s*(\{[^}]+\})', raw)
        if pogo_match:
            try:
                pogo = json.loads(pogo_match.group(1))
                outage = pogo.get("outage", False)
            except (json.JSONDecodeError, KeyError):
                pass

        soup = BeautifulSoup(raw, "html.parser")

        # 2. H1 status text — distinguish warning vs danger
        h1 = soup.find("h1")
        status_text = h1.get_text(strip=True) if h1 else ""

        # Derive status_level: danger if outage=true, warning if partial, normal otherwise
        status_lower = status_text.lower()
        if outage or "problems" in status_lower and "no current" not in status_lower:
            if "no current" in status_lower or "no problem" in status_lower:
                status_level = "normal"
            else:
                status_level = "danger" if outage else "warning"
        else:
            status_level = "normal"

        # 3. Most-reported-problems breakdown (e.g. "67% App 22% Online Banking")
        problems_breakdown = ""
        body_text = soup.get_text(" ", strip=True)
        prob_match = re.search(r"Most reported problems(.{0,200})", body_text, re.IGNORECASE)
        if prob_match:
            problems_breakdown = re.sub(r"\s+", " ", prob_match.group(1)).strip()[:150]

        return [{
            "current_report_count": 0,       # chart data is API-gated; use status_level for severity
            "baseline_report_count": 0,
            "status": status_level,
            "status_text": status_text[:120],
            "problems_breakdown": problems_breakdown,
            "source_url": self.url,
            "parse_method": "pogo_config",
        }]

    def to_signal(self, parsed_item: dict) -> RawSignal:
        status = parsed_item.get("status", "normal")
        severity_map = {"danger": "P0", "warning": "P1", "normal": "P2"}
        severity_class = severity_map.get(status, "P2")
        spike_detected = status in ("danger", "warning")

        return RawSignal(
            source=self.source_name,
            competitor=self.competitor,
            trust_weight=self.trust_weight,
            severity_class=severity_class,
            spike_detected=spike_detected,
            raw_data={
                "status":              status,
                "status_text":         parsed_item.get("status_text", ""),
                "problems_breakdown":  parsed_item.get("problems_breakdown", ""),
                "source_url":          parsed_item.get("source_url"),
                "parse_method":        parsed_item.get("parse_method"),
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
