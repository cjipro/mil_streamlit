"""
voice_intelligence_agent.py — MIL Harvester Orchestrator.

Loads all source classes. Runs ACTIVE sources on schedule.
Skips STUB sources gracefully with INFO log.
Writes signals to mil/data/signals/signals_YYYY-MM-DD_HHMMSS.json.
Applies Jax filter on sources where jax_filter: true.
Logs SILENCE_FLAG and SCHEMA_DRIFT to mil/data/signals/errors.log.

Dual-write storage:
  Local:  mil/data/signals/signals_TIMESTAMP.json  (fast, working copy)
  HDFS:   /user/mil/signals/signals_TIMESTAMP.json (permanent record)
  HDFS failure is non-fatal — local write always succeeds first.

Zero Entanglement: no imports from pulse/, poc/, app/, dags/,
or any internal module. This file is the harvester boundary.
MIL HDFS client connects to port 9871 only — never CJI port 9870.
"""
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# ── Path setup — mil/ is self-contained ──────────────────────
MIL_ROOT = Path(__file__).parent.parent
ENV_PATH = MIL_ROOT.parent / ".env"
APPS_CONFIG = MIL_ROOT / "config" / "apps_config.yaml"
DATA_DIR = MIL_ROOT / "data" / "signals"

# Load .env
load_dotenv(ENV_PATH)

# ── Logging ───────────────────────────────────────────────────
DATA_DIR.mkdir(parents=True, exist_ok=True)

_log_file = DATA_DIR / "errors.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(_log_file, maxBytes=5_000_000, backupCount=3),
    ],
)
logger = logging.getLogger("voice_intelligence_agent")

# ── Import sources ────────────────────────────────────────────
from mil.harvester.sources.downdetector import build_all_sources as dd_sources
from mil.harvester.sources.app_store import build_all_sources as as_sources
from mil.harvester.sources.google_play import build_all_sources as gp_sources
from mil.harvester.sources.reddit import build_all_sources as rd_sources
from mil.harvester.sources.trustpilot import build_all_sources as tp_sources
from mil.harvester.sources.facebook import build_all_sources as fb_sources
from mil.harvester.sources.youtube import build_all_sources as yt_sources
from mil.harvester.sources.ft_cityam import build_all_sources as ft_sources
from mil.harvester.sources.twitter import build_all_sources as tw_sources
from mil.harvester.sources.glassdoor import build_all_sources as gd_sources
from mil.harvester.jax_synthetic_filter import apply_jax_filter
from mil.storage.hdfs_client import dual_write_signals

# Sources where Jax filter is required
JAX_REQUIRED_SOURCES = {"reddit", "youtube", "twitter_x", "facebook"}


def _build_all_sources() -> list:
    """Instantiate one source object per competitor per active source type."""
    kwargs = dict(apps_config_path=APPS_CONFIG, env_path=ENV_PATH)
    kwargs_no_env = dict(apps_config_path=APPS_CONFIG)

    all_sources = []
    all_sources.extend(dd_sources(**kwargs_no_env))
    all_sources.extend(as_sources(**kwargs_no_env))
    all_sources.extend(gp_sources(**kwargs_no_env))
    all_sources.extend(rd_sources(**kwargs))
    all_sources.extend(tp_sources(**kwargs_no_env))
    all_sources.extend(fb_sources(**kwargs_no_env))
    all_sources.extend(yt_sources(**kwargs))
    all_sources.extend(ft_sources(**kwargs_no_env))
    all_sources.extend(tw_sources(**kwargs))
    all_sources.extend(gd_sources(**kwargs_no_env))
    return all_sources


def run_harvest() -> list[dict]:
    """
    Run one full harvest cycle across all ACTIVE sources.
    Returns list of signal dicts. Writes to data/signals/.
    """
    logger.info("=" * 60)
    logger.info("MIL Harvest — starting run")
    logger.info("=" * 60)

    all_sources = _build_all_sources()
    all_signals: list[dict] = []
    errors: list[dict] = []

    active = [s for s in all_sources if s.status == "ACTIVE"]
    stubs = [s for s in all_sources if s.status == "STUB"]

    logger.info("Sources: %d ACTIVE, %d STUB", len(active), len(stubs))
    for stub in stubs:
        logger.info("[STUB] %s / %s — skipping.", stub.source_name, stub.competitor)

    for source in active:
        logger.info("[RUN] %s / %s", source.source_name, source.competitor)
        try:
            signals = source.run()
        except Exception as exc:
            logger.error("[ERROR] %s / %s — unhandled: %s", source.source_name, source.competitor, exc)
            continue

        for sig in signals:
            sig_dict = sig.to_dict() if hasattr(sig, "to_dict") else sig

            # Log error flags
            if sig_dict.get("error_flag"):
                flag = sig_dict["error_flag"]
                logger.warning("[%s] %s / %s — %s",
                               flag, source.source_name, source.competitor, flag)
                errors.append(sig_dict)
                continue

            # Apply Jax filter where required
            if source.source_name in JAX_REQUIRED_SOURCES:
                sig_dict = apply_jax_filter(sig_dict)
                if sig_dict.get("jax_flags"):
                    logger.info("[JAX] %s / %s — flags: %s",
                                source.source_name, source.competitor, sig_dict["jax_flags"])

            all_signals.append(sig_dict)

    # ── Dual-write: local first, then HDFS ───────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_file = DATA_DIR / f"signals_{timestamp}.json"

    # Local write — always first, always succeeds
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_signals, f, indent=2, default=str)
    logger.info("Harvest complete. %d signals written (local): %s", len(all_signals), out_file.name)

    # HDFS write — permanent record, non-fatal on failure
    dual_write_signals(out_file, all_signals, timestamp)

    logger.info("%d SILENCE/SCHEMA_DRIFT errors logged.", len(errors))
    logger.info("=" * 60)

    return all_signals


if __name__ == "__main__":
    run_harvest()
