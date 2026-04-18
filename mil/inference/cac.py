"""
mil/inference/cac.py

CAC formula and volume signal computation.
Extracted from mil_agent.py for independent testability.

CAC Formula: C_mil = (alpha * Vol_sig + beta * Sim_hist) / (delta * Delta_tel + 1)
  alpha=0.40, beta=0.40, delta=0.20  (sensitivity analysis run 2026-04-17)
  delta_tel=0.0 until Phase 2 internal telemetry is available.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from mil.config.thresholds import T as _T
except ImportError:
    from config.thresholds import T as _T

ALPHA = _T("inference.cac_alpha")
BETA  = _T("inference.cac_beta")
DELTA = _T("inference.cac_delta")

SEV_MULTIPLIER = {"P0": 2.0, "P1": 1.5, "P2": 1.0, "ENRICHMENT_FAILED": 0.0}


def compute_vol_sig(cluster: list[dict], total_competitor_records: int) -> float:
    """
    Vol_sig = weighted signal volume, normalised to [0.0, 1.0].
    P0 carries 2x weight, P1 1.5x, P2 1.0x (per MIL_SCHEMA.yaml).
    """
    if total_competitor_records == 0:
        return 0.0
    weighted = sum(
        SEV_MULTIPLIER.get(r.get("severity_class", "P2"), 1.0)
        for r in cluster
    )
    raw = weighted / max(total_competitor_records, 1)
    return min(raw * 5.0, 1.0)


def compute_cac(vol_sig: float, sim_hist: float, delta_tel: float = 0.0) -> float:
    """
    C_mil = (alpha * Vol_sig + beta * Sim_hist) / (delta * Delta_tel + 1)

    delta_tel=0.0: no internal telemetry available (Phase 1).
    Higher delta_tel (Vane gap) lowers confidence by raising the denominator.
    """
    numerator   = (ALPHA * vol_sig) + (BETA * sim_hist)
    denominator = (DELTA * delta_tel) + 1.0
    return round(numerator / denominator, 4)
