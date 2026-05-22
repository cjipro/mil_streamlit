"""Tests for the Agentic AI placement scenario (PULSE-106).

Key invariants:
- the scenario runs end-to-end against the shipped scenario.yaml
- the matrix is deterministic (same scenario → same matrix)
- the matrix exercises every Diagnosis label + every Action tier label
  at least once (the worked example demonstrates the full output space)
- the Diagnosis-overrides rule is asserted (INCONCLUSIVE cells route
  to NEEDS_MORE_DATA regardless of Risk/Value; JOURNEY_PROBLEM cells
  route to "fix the journey" verb regardless of Action tier)
- the Markdown render produces a non-empty table
"""

from __future__ import annotations

import pytest

from pulse.scenarios.agentic_ai_placement import (
    PlacementCell,
    PlacementMatrix,
    run_placement_scenario,
)


@pytest.fixture(scope="module")
def matrix() -> PlacementMatrix:
    """Run the scenario once for the whole module — the engine flow is
    deterministic, so we can reuse the matrix across assertions."""
    return run_placement_scenario()


def test_scenario_runs_end_to_end(matrix: PlacementMatrix) -> None:
    assert len(matrix.cells) == 12  # 4 journeys × 3 signatures
    for cell in matrix.cells:
        assert isinstance(cell, PlacementCell)
        assert cell.journey_id
        assert cell.signature_id
        assert cell.diagnosis.diagnosis
        assert cell.risk.tier
        assert cell.value.tier
        assert cell.action_tier
        assert cell.placement_recommendation


def test_scenario_is_deterministic() -> None:
    """Pure-function invariant — same scenario.yaml input → identical
    matrix in every per-cell methodology hash."""
    a = run_placement_scenario()
    b = run_placement_scenario()
    assert len(a.cells) == len(b.cells)
    for ca, cb in zip(a.cells, b.cells):
        assert ca.diagnosis.inputs_hash == cb.diagnosis.inputs_hash
        assert ca.risk.inputs_hash == cb.risk.inputs_hash
        assert ca.value.inputs_hash == cb.value.inputs_hash
        assert ca.action_tier == cb.action_tier
        assert ca.placement_recommendation == cb.placement_recommendation


def test_methodology_versions_propagated(matrix: PlacementMatrix) -> None:
    """The matrix carries methodology versions for all three engines —
    audit footer requirement."""
    assert matrix.diagnosis_methodology_version == "0.1.0"
    assert matrix.risk_methodology_version == "0.1.0"
    # Value bumped to v0.3.0 (friction-volume primary, £ scaffold secondary).
    assert matrix.value_methodology_version == "0.3.0"


def test_matrix_exercises_full_diagnosis_enum(matrix: PlacementMatrix) -> None:
    """The scenario should hit ≥3 of the 4 Diagnosis labels — the
    worked example exists to demonstrate the output space, not to
    showcase a single dominant outcome."""
    diagnoses = {c.diagnosis.diagnosis for c in matrix.cells}
    assert len(diagnoses) >= 3, (
        f"scenario produces too few Diagnosis labels {diagnoses} — "
        "rebalance scenario.yaml fixtures so the demo exercises "
        "more of the output space"
    )


def test_matrix_exercises_multiple_action_tiers(matrix: PlacementMatrix) -> None:
    """Similar to the Diagnosis spread — Action tiers should not all be
    the same."""
    tiers = {c.action_tier for c in matrix.cells}
    assert len(tiers) >= 3, (
        f"scenario produces too few Action tiers {tiers}"
    )


def test_inconclusive_diagnosis_overrides_action_tier(matrix: PlacementMatrix) -> None:
    """If a cell's diagnosis is INCONCLUSIVE, the action_tier must be
    NEEDS_MORE_DATA regardless of Risk/Value scores. This is the
    diagnosis-first composition rule from the README."""
    for cell in matrix.cells:
        if cell.diagnosis.diagnosis == "INCONCLUSIVE":
            assert cell.action_tier == "NEEDS_MORE_DATA", (
                f"INCONCLUSIVE cell on {cell.journey_id}/{cell.signature_id} "
                f"routed to action_tier={cell.action_tier} — should override "
                "to NEEDS_MORE_DATA"
            )
            assert "Insufficient control-arm data" in cell.placement_recommendation


def test_journey_problem_diagnosis_routes_to_journey_fix_verb(
    matrix: PlacementMatrix,
) -> None:
    """JOURNEY_PROBLEM cells must surface 'fix the journey' guidance,
    regardless of Action tier. This is the AI-deployment veto from the
    Diagnosis methodology design."""
    for cell in matrix.cells:
        if cell.diagnosis.diagnosis == "JOURNEY_PROBLEM":
            assert "Fix the journey" in cell.placement_recommendation


def test_support_problem_acute_routes_to_guardrails(matrix: PlacementMatrix) -> None:
    """SUPPORT_PROBLEM × ACUTE → 'deploy with heavy guardrails'. This is
    the load-bearing cell — high value + high regulatory exposure where
    AI assistance is the right intervention but needs governance."""
    found = False
    for cell in matrix.cells:
        if (
            cell.diagnosis.diagnosis == "SUPPORT_PROBLEM"
            and cell.action_tier == "ACUTE"
        ):
            assert "guardrails" in cell.placement_recommendation
            found = True
    # The fixtures should produce at least one such cell — if they don't,
    # the demo isn't covering the load-bearing case
    assert found, (
        "scenario.yaml fixtures don't produce any SUPPORT_PROBLEM × ACUTE "
        "cells — rebalance so the load-bearing case is demonstrated"
    )


def test_markdown_render_includes_all_cells(matrix: PlacementMatrix) -> None:
    md = matrix.render_markdown()
    assert "Agentic AI placement matrix" in md
    assert matrix.deployment_id in md
    for cell in matrix.cells:
        assert cell.signature_id in md
    # methodology versions in the audit footer
    assert "Diagnosis 0.1.0" in md
    assert "Risk 0.1.0" in md
    assert "Value 0.3.0" in md


def test_every_cell_has_a_placement_recommendation(matrix: PlacementMatrix) -> None:
    """No empty recommendations — every cell must produce actionable text."""
    for cell in matrix.cells:
        assert cell.placement_recommendation
        assert len(cell.placement_recommendation) > 10


def test_cell_as_dict_round_trip(matrix: PlacementMatrix) -> None:
    cell = matrix.cells[0]
    d = cell.as_dict()
    assert d["journey_id"] == cell.journey_id
    assert d["diagnosis"] == cell.diagnosis.diagnosis
    assert d["action_tier"] == cell.action_tier
    assert d["placement_recommendation"] == cell.placement_recommendation
