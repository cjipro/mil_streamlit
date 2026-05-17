"""FrictionBench — public benchmark for journey-friction detection systems.

Spec-only at v0.1 per PULSE-88. Out of scope: the actual scoring harness
(Docker streaming runner, leaderboard server) and the real-bank labelled set
(contract-gated). The one piece of shipped code is the per-detection scoring
script (`scoring.score`) — the open-source reference implementation anyone
can re-run.

Filed under PULSE-88.
"""

from pulse.frictionbench.scoring.score import (
    DetectionScore,
    aggregate_cell,
    score_detection,
)

__all__ = ["DetectionScore", "aggregate_cell", "score_detection"]
