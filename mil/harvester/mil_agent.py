"""
mil_agent.py — MIL inference agent (Qwen-14B + CAC + RAG).
Status: STUB — Week 3 (PULSE-2H).

Purpose: Qwen-14B inference with CAC formula and RAG against CHRONICLE.md.
Produces Inference Cards with confidence scores and CHRONICLE traces.
Writes findings to the canonical exit point: mil/outputs/mil_findings.json.

CAC Formula: C_mil = ( alpha * Vol_sig + beta * Sim_hist ) / ( delta * Delta_tel + 1 )
Starting weights: alpha=0.4, beta=0.4, delta=0.2 — not tuned before Day 30.

Dual-write storage contract (to be implemented in Week 3):
  1. Generate findings via CAC + RAG
  2. Write to local:  mil/outputs/mil_findings.json  (THE exit point)
  3. Write to HDFS:   /user/mil/findings/mil_findings_{timestamp}.json
  Local is working copy. HDFS is permanent record.

Zero Entanglement: no imports from pulse/, poc/, app/, dags/,
or any internal module. Findings are read by CJI Pulse via
mil/outputs/mil_findings.json only — never by direct import.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Storage helpers — wired in, ready for Week 3 implementation
from mil.storage.hdfs_client import dual_write_findings  # noqa: F401

FINDINGS_PATH = Path(__file__).parent.parent / "outputs" / "mil_findings.json"


def run_inference(signals: list[dict]) -> dict:
    """
    STUB — implement in Week 3.
    Runs CAC formula + RAG against CHRONICLE.md on signal batch.
    Writes findings to mil/outputs/mil_findings.json and HDFS.
    """
    raise NotImplementedError(
        "mil_agent.run_inference() is STUB — activate in Week 3. "
        "Dual-write to mil/outputs/mil_findings.json and /user/mil/findings/ is pre-wired."
    )
