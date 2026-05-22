"""Pulse detection runtime (PULSE-126).

The interpreter that executes a decision pack's declarative `analytic` spec
over canonical-event sessions and emits FrictionBench-shaped detections.
Classical, deterministic, explainable — the non-LLM runtime lock. This is the
keystone the tracking loop, computed Value/Risk, and any FrictionBench score
all sit on.

Importing this package registers the built-in methods.
"""

from pulse.detection.detect import (
    DETECTION_RUNTIME_VERSION,
    Detection,
    MethodResult,
    ScreenBaseline,
    Session,
    get_method,
    register_method,
    registered_methods,
    run_detection,
)

# Importing methods registers them in the method registry.
from pulse.detection import methods as _methods  # noqa: F401,E402

__all__ = [
    "DETECTION_RUNTIME_VERSION",
    "Detection",
    "MethodResult",
    "ScreenBaseline",
    "Session",
    "get_method",
    "register_method",
    "registered_methods",
    "run_detection",
]
