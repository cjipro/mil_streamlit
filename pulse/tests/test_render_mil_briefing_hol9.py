"""Smoke tests for the HOL-9 briefing-surface integration of Value/Risk
methodologies + Chronicle-as-matcher.

Verifies:
- per-pack Value + Risk + Action badges render on pack cards
- Box 3 Intelligence Brief surfaces the engine-computed Action tier
  (not the hand-typed CLARK label)
- new V3 panels (VALUE SCORING + RISK SCORING) render with per-pack
  breakdowns
- Chronicle panel evolves from static cell catalogue to matched-precedent
  display; renders the curator-handoff message when no verified matches
  exist (the seed-batch state)
- colour-map sanity gates for Risk and Value tier-words (catches enum drift)

Filed under HOL-9.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from holter.preview import render_mil_briefing  # noqa: E402


def test_per_pack_badges_render_on_pack_cards() -> None:
    """The new tier badges (VALUE / RISK / ACTION) must appear on
    pack cards in the journey_cards render."""
    # Force re-index in case earlier tests cached an empty state
    render_mil_briefing._PACK_CELL_INDEX = None

    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_journey_cards(packs)

    # At least one pack card should carry all three badge labels
    assert "VALUE ·" in html
    assert "RISK ·" in html
    assert "ACTION ·" in html

    # Specific tier-word labels we know appear in the placement matrix
    # for the seed batch
    assert "COMMERCIAL-OPPORTUNITY" in html
    assert "REGULATORY-FLAG" in html


def test_intelligence_brief_uses_engine_action_tier() -> None:
    """Box 3 must render the engine-computed Action tier from the
    placement scenario, not the hand-typed CLARK label."""
    render_mil_briefing._PACK_CELL_INDEX = None
    packs = render_mil_briefing.discover_packs()
    headline = render_mil_briefing.headline_pack(packs)
    html = render_mil_briefing.render_intelligence_brief(headline, packs)

    # The CLARK-style placement recommendation sentence should appear
    # (it's emitted by run.py's _placement_recommendation())
    placement_sentences = (
        "Deploy AI assistance",
        "Fix the journey",
        "Don't deploy",
        "Insufficient control-arm data",
        "Monitor —",
        "Not worth deploying",
    )
    assert any(s in html for s in placement_sentences), (
        "Box 3 didn't surface an engine-computed placement recommendation"
    )

    # The legacy hand-typed CLARK label should NOT appear when the
    # engine is loaded (it's the fallback only)
    assert "PULSE-1 — DETECTOR ACTIVE" not in html
    assert "PULSE-0 — DISCRIMINATOR REQUIRED" not in html


def test_value_scoring_panel_renders_with_per_pack_rows() -> None:
    render_mil_briefing._PACK_CELL_INDEX = None
    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_value_scoring_panel(packs)

    assert "VALUE SCORING" in html
    assert "Pulse Value methodology v0" in html
    # Per-row breakdown text includes the methodology axis names
    assert "severity" in html.lower() or "base:" in html
    # At least one pack name should appear in the rows
    assert "loans_apply_step3" in html


def test_risk_scoring_panel_renders_with_per_pack_rows() -> None:
    render_mil_briefing._PACK_CELL_INDEX = None
    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_risk_scoring_panel(packs)

    assert "RISK SCORING" in html
    assert "Pulse Risk methodology v0" in html
    # Per-row content: regulatory matches, adjustments, chronicle column
    assert "REGULATORY MATCHES" in html
    assert "ADJUSTMENTS FIRED" in html
    assert "CHRONICLE" in html
    # At least one known regulatory taxonomy short-name should appear
    # (we trim to last segment so e.g. "outcome_1_products_services" not full path)
    assert any(t in html for t in (
        "outcome_1_products_services",
        "outcome_3_consumer_understanding",
        "outcome_4_consumer_support",
        "high_risk_credit_scoring",
    ))


def test_chronicle_panel_shows_curator_handoff_when_no_verified_matches() -> None:
    """Seed-batch Chronicle entries all ship pending_human_review so the
    matcher always returns empty. The Chronicle panel must surface this
    explicitly (never silent) with the curator-handoff explanation."""
    render_mil_briefing._PACK_CELL_INDEX = None
    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_chronicle(packs)

    assert "NO VERIFIED MATCHES" in html
    assert "Curator handoff pending" in html
    assert "pending_human_review" in html
    assert "Two-stage trust model" in html

    # The context card showing which pack the matcher was run for
    assert "Headline pack" in html


def test_chronicle_panel_falls_back_when_engine_unavailable() -> None:
    """If the engine import fails the Chronicle panel still renders
    (with a clear 'matcher offline' card)."""
    render_mil_briefing._PACK_CELL_INDEX = None
    with patch.dict(sys.modules, {"pulse.scenarios.agentic_ai_placement": None}):
        # Also reset cache so the patched failure is observed
        render_mil_briefing._PACK_CELL_INDEX = None
        packs = render_mil_briefing.discover_packs()
        html = render_mil_briefing.render_chronicle(packs)

    assert "UNAVAILABLE" in html or "Chronicle matcher offline" in html
    # Context card still renders so panel layout doesn't collapse
    assert "Headline pack" in html

    # Reset cache after the patched test so other tests see real state
    render_mil_briefing._PACK_CELL_INDEX = None


def test_risk_color_map_matches_pulse_99_rubric() -> None:
    """Sanity gate: Risk colour map must cover the full PULSE-99 tier-words
    enum. Drift would silently render badges as grey."""
    from pulse.risk import load_rubric

    rubric_tiers = set(load_rubric()["tier_words"])
    color_map_tiers = set(render_mil_briefing._RISK_COLORS.keys())
    assert rubric_tiers == color_map_tiers


def test_value_color_map_matches_pulse_101_methodology() -> None:
    """Sanity gate: Value colour map must cover the full PULSE-101
    tier-words enum."""
    from pulse.value import load_methodology

    methodology_tiers = set(load_methodology()["tier_words"])
    color_map_tiers = set(render_mil_briefing._VALUE_COLORS.keys())
    assert methodology_tiers == color_map_tiers


def test_full_page_render_includes_all_hol9_sections() -> None:
    """End-to-end: the full briefing page should contain every HOL-9
    sub-deliverable wired in via render_page()."""
    render_mil_briefing._PACK_CELL_INDEX = None
    packs = render_mil_briefing.discover_packs()
    html = render_mil_briefing.render_page(packs)

    # All four HOL-9 sections present
    assert html.count("VALUE SCORING") == 1
    assert html.count("RISK SCORING") == 1
    assert "CHRONICLE — matched precedents" in html  # panel title

    # Old static cell-catalogue title is gone
    assert "CELL CATALOGUE — FrictionBench v0.1" not in html
