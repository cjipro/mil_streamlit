"""Smoke test for the HOL-11 placement-matrix briefing render.

Verifies that:
- render_placement_matrix() returns HTML containing all four key
  components (header / 2x2 aggregate / per-cell rows / lineage footer)
- the function fails closed with a visible banner if PULSE-106 can't
  be loaded — the briefing should never silently swallow the section
- the rendered HTML appears in the full briefing page output

Filed under HOL-11.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Make `holter.preview.render_mil_briefing` importable from pulse/tests/
# (renderer lives in holter/preview/ — sibling to pulse/).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pytest  # noqa: E402

from holter.preview import render_mil_briefing  # noqa: E402


def test_render_placement_matrix_includes_all_components() -> None:
    """All four briefing-block components must render when PULSE-106
    loads successfully."""
    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_placement_matrix(packs)

    # Header
    assert "AGENTIC AI PLACEMENT MATRIX" in html

    # 2x2 aggregate cells (all four CLARK-style labels present)
    assert "ACUTE" in html
    assert "REGULATORY-FLAG" in html
    assert "COMMERCIAL-OPPORTUNITY" in html
    assert "NOMINAL / WATCH" in html

    # Per-cell row markers
    assert "<tbody>" in html
    assert "loans_apply_step3" in html  # at least one journey row

    # Lineage footer
    assert "LINEAGE:" in html
    assert "Diagnosis v0.1.0" in html
    assert "Risk v0.1.0" in html
    assert "Value v0.3.0" in html
    assert "deploy-scenario-agentic-ai-placement" in html


def test_render_placement_matrix_fails_closed_with_visible_banner() -> None:
    """If PULSE-106 import fails, the function returns a fallback block
    with a clear 'unavailable' banner — never silent. This is the
    discipline that keeps the briefing surface honest about engine state."""
    # Force the import inside render_placement_matrix() to raise by
    # monkey-patching the scenarios module to None for the duration of
    # this test.
    with patch.dict(sys.modules, {"pulse.scenarios.agentic_ai_placement": None}):
        html = render_mil_briefing.render_placement_matrix([])

    assert "AGENTIC AI PLACEMENT MATRIX" in html
    assert "PULSE-106 unavailable" in html
    # The fallback must still render a topbar-box so the page layout
    # doesn't break
    assert "topbar-box" in html


def test_full_page_render_includes_placement_section() -> None:
    """End-to-end: the full briefing page render should contain the
    placement matrix section wired in via render_page()."""
    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_page(packs)

    # Header appears once (one block only)
    assert html.count("AGENTIC AI PLACEMENT MATRIX") == 1
    # Lineage footer landed
    assert "Diagnosis v0.1.0" in html
    # Some cell row content rendered (not the fallback)
    assert "PULSE-106 unavailable" not in html


def test_diagnosis_color_map_covers_full_enum() -> None:
    """Sanity: every Diagnosis tier-word from PULSE-105 has a color
    assignment. Adding a tier without a color would render badges as
    grey by default, which is silently degraded."""
    from pulse.diagnosis import load_rubric

    rubric_tiers = set(load_rubric()["tier_words"])
    color_map_tiers = set(render_mil_briefing._DIAGNOSIS_COLORS.keys())
    assert rubric_tiers == color_map_tiers, (
        f"Diagnosis color map drift: rubric={rubric_tiers}, "
        f"colors={color_map_tiers}"
    )


def test_action_color_map_covers_clark_tiers() -> None:
    """Sanity: every Action tier the compositor can emit has a color."""
    # The CLARK-style tiers from run.py + the NEEDS_MORE_DATA override.
    expected = {
        "ACUTE",
        "REGULATORY-FLAG",
        "COMMERCIAL-OPPORTUNITY",
        "WATCH",
        "NOMINAL",
        "NEEDS_MORE_DATA",
    }
    assert expected.issubset(render_mil_briefing._ACTION_COLORS.keys())
