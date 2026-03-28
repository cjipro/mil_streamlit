"""
historical_loader.py — MIL historical backfill loader.
Status: STUB — Week 3 (PULSE-2H dependency).

Purpose: Backfill historical signal data from App Store, Google Play,
Reddit, and YouTube before the live harvester was running. Enables
CHRONICLE similarity matching against a richer baseline.

Dual-write storage contract (to be implemented in Week 3):
  1. Collect historical data from source APIs
  2. Write to local:  mil/data/historical/{source}/{competitor}/
  3. Write to HDFS:   /user/mil/historical/{source}/{competitor}/
  Local is working copy. HDFS is permanent record.

Zero Entanglement: no imports from pulse/, poc/, app/, dags/,
or any internal module.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Storage helpers — wired in, ready for Week 3 implementation
from mil.storage.hdfs_client import dual_write_historical  # noqa: F401

LOCAL_HISTORICAL_BASE = Path(__file__).parent.parent / "data" / "historical"


def run_backfill(competitor: str, source: str, days_back: int = 90) -> None:
    """
    STUB — implement in Week 3.
    Backfill historical signals for a given competitor and source.
    Writes to both local and HDFS.
    """
    raise NotImplementedError(
        "historical_loader.run_backfill() is STUB — activate in Week 3. "
        "Dual-write to mil/data/historical/ and /user/mil/historical/ is pre-wired."
    )
