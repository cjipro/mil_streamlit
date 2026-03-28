"""
base.py — Abstract base class for all MIL signal sources.

MIL public data note: MIL processes exclusively public market data.
No internal customer data, no telemetry, no PII. No masking applied.
Competitors appear by their real names in all signals.

Zero Entanglement: this file must never import from pulse/, poc/,
app/, dags/, or any internal module.
"""
import abc
import time
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Error flags ───────────────────────────────────────────────
SILENCE_FLAG = "SILENCE"          # Source returned no data — not an error, a signal
SCHEMA_DRIFT = "SCHEMA_DRIFT"     # Source structure changed — human review required

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0            # seconds, doubles each attempt


@dataclass
class RawSignal:
    """Canonical signal structure. All sources produce this."""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    competitor: str = ""
    trust_weight: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    severity_class: str = "INFO"          # P0, P1, P2, INFO
    spike_detected: bool = False
    error_flag: Optional[str] = None      # SILENCE_FLAG or SCHEMA_DRIFT or None
    jax_flags: list = field(default_factory=list)
    jax_clean: bool = True
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "competitor": self.competitor,
            "trust_weight": self.trust_weight,
            "timestamp": self.timestamp,
            "severity_class": self.severity_class,
            "spike_detected": self.spike_detected,
            "error_flag": self.error_flag,
            "jax_flags": self.jax_flags,
            "jax_clean": self.jax_clean,
            "raw_data": self.raw_data,
        }


class SignalSource(abc.ABC):
    """Abstract base for all MIL signal sources."""

    source_name: str = ""
    trust_weight: float = 0.0
    status: str = "ACTIVE"     # ACTIVE or STUB

    def __init__(self, competitor: str, competitor_config: dict):
        self.competitor = competitor
        self.competitor_config = competitor_config

    @abc.abstractmethod
    def fetch(self) -> Any:
        """Fetch raw data from source. Returns raw response or raises."""
        ...

    @abc.abstractmethod
    def parse(self, raw: Any) -> list[dict]:
        """Parse raw response into list of normalised dicts."""
        ...

    @abc.abstractmethod
    def to_signal(self, parsed_item: dict) -> RawSignal:
        """Convert a parsed item to a RawSignal."""
        ...

    def run(self) -> list[RawSignal]:
        """
        Full fetch → parse → to_signal pipeline with retry and error flags.
        Returns list of RawSignal objects (may be empty on SILENCE).
        """
        if self.status == "STUB":
            logger.info("[%s] %s is a STUB — skipping.", self.source_name, self.competitor)
            return []

        raw = self._fetch_with_retry()
        if raw is None:
            sig = RawSignal(
                source=self.source_name,
                competitor=self.competitor,
                trust_weight=self.trust_weight,
                error_flag=SILENCE_FLAG,
            )
            logger.warning("[%s] %s — SILENCE_FLAG: source returned nothing after %d attempts.",
                           self.source_name, self.competitor, RETRY_ATTEMPTS)
            return [sig]

        try:
            parsed = self.parse(raw)
        except Exception as exc:
            sig = RawSignal(
                source=self.source_name,
                competitor=self.competitor,
                trust_weight=self.trust_weight,
                error_flag=SCHEMA_DRIFT,
                raw_data={"exception": str(exc)},
            )
            logger.error("[%s] %s — SCHEMA_DRIFT: parse failed: %s",
                         self.source_name, self.competitor, exc)
            return [sig]

        if not parsed:
            return []

        signals = []
        for item in parsed:
            try:
                signals.append(self.to_signal(item))
            except Exception as exc:
                logger.warning("[%s] %s — to_signal failed for item: %s", self.source_name, self.competitor, exc)
        return signals

    def _fetch_with_retry(self) -> Any:
        delay = RETRY_BASE_DELAY
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                return self.fetch()
            except Exception as exc:
                logger.warning("[%s] %s — fetch attempt %d/%d failed: %s",
                               self.source_name, self.competitor, attempt, RETRY_ATTEMPTS, exc)
                if attempt < RETRY_ATTEMPTS:
                    time.sleep(delay)
                    delay *= 2
        return None
