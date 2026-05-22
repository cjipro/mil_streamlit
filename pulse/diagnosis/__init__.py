"""Pulse Diagnosis methodology — problem-locus disambiguation (PULSE-105).

Runs BEFORE Value (PULSE-101) and Risk (PULSE-99) tier scoring in the
decision flow. Answers "is this a SUPPORT problem, a JOURNEY problem,
BOTH, or INCONCLUSIVE?" by comparing assistance-using sessions against
self-sufficient sessions on the same journey.
"""

from pulse.diagnosis.score import (
    DiagnosisResult,
    JourneyArmObservation,
    JourneyIdentity,
    diagnose_problem_locus,
    load_rubric,
)

__all__ = [
    "DiagnosisResult",
    "JourneyArmObservation",
    "JourneyIdentity",
    "diagnose_problem_locus",
    "load_rubric",
]
