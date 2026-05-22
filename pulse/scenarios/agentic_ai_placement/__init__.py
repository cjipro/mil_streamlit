"""Agentic AI placement scenario — worked example (PULSE-106).

Runs the full v0 engine spine across 4 journeys × 3 signatures from the
seed-batch decision packs (PULSE-104) and emits a placement matrix:
"deploy first / deploy with guardrails / don't deploy / not worth it"
per journey × signature, with the audit footprint (methodology versions
+ inputs_hash per call) attached.
"""

from pulse.scenarios.agentic_ai_placement.run import (
    PlacementCell,
    PlacementMatrix,
    run_placement_scenario,
)

__all__ = ["PlacementCell", "PlacementMatrix", "run_placement_scenario"]
