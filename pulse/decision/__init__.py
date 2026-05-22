"""Pulse decision layer — compose Diagnosis + Risk + Value onto fired detections.

Turns the pipeline's fired friction detections (pulse.pipeline.detect_sessions)
into decisions: each (screen x signature) finding is scored on the Risk and Value
axes and composed into a CLARK-style Action tier (the Value x Risk 2x2). Diagnosis
(AI-deployability) wires in when an assistance/control arm is available.

Owned by while-sleeping (engine relocated under PULSE-128; scorers PULSE-99/101/105).
"""

from pulse.decision.lineage import build_decision_lineage, verify_decision_lineage
from pulse.decision.score_findings import (
    DecisionRecord,
    build_decisions,
    read_decisions,
    score_findings,
)

__all__ = [
    "DecisionRecord",
    "build_decision_lineage",
    "build_decisions",
    "read_decisions",
    "score_findings",
    "verify_decision_lineage",
]
