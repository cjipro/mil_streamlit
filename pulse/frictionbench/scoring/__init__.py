"""FrictionBench scoring — open-source reference implementation."""

from pulse.frictionbench.scoring.score import (
    DetectionScore,
    aggregate_cell,
    apply_false_positive_penalty,
    load_rubric,
    macro_average,
    score_detection,
)

__all__ = [
    "DetectionScore",
    "aggregate_cell",
    "apply_false_positive_penalty",
    "load_rubric",
    "macro_average",
    "score_detection",
]
