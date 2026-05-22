"""Smoke tests for the HOL-10 phase 4 V3-layer filter recompute.

The recompute logic lives in JS (browser-side); these tests verify the
*structural* contract — that the per-pack data attributes and aggregate
markers the JS targets are actually present in the rendered HTML.

A future browser-test harness (chrome-devtools MCP) could drive the
filter dropdowns and assert visible-count changes; this is the
unit-level guard that keeps the JS from going silent if the markers
drift.

Filed under HOL-10 phase 4.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from holter.preview import render_mil_briefing  # noqa: E402


def _packs() -> list[dict]:
    render_mil_briefing._PACK_CELL_INDEX = None
    return render_mil_briefing.discover_packs()


def test_commentary_cards_have_data_packname() -> None:
    """Pack commentary cards carry data-packname so JS can hide/show
    them in sync with the pack-card visibility."""
    html = render_mil_briefing.render_commentary_block(_packs())
    # At least one card per pack name should appear
    for name in ("loans_apply_step3__dwell_after_error",
                 "international_beneficiary_setup__abandon_before_submit"):
        assert f'data-packname="{name}"' in html


def test_bench_rows_have_data_packname() -> None:
    html = render_mil_briefing.render_bench_block(_packs())
    assert 'bench-issue-row" data-packname=' in html


def test_churn_pills_have_data_packname_and_pill_class() -> None:
    """Friction risk score pills carry both data-packname (for hide/show)
    and data-pill-class (for re-tallying positive vs discriminator counts)."""
    html = render_mil_briefing.render_churn_block(_packs())
    assert 'data-pill-class="positive"' in html
    assert 'data-pill-class="discriminator"' in html
    # Score + count aggregate markers
    assert 'data-aggregate="churn-score"' in html
    assert 'data-aggregate="churn-positive-count"' in html
    assert 'data-aggregate="churn-discriminator-count"' in html


def test_value_scoring_rows_carry_tier_and_packname() -> None:
    html = render_mil_briefing.render_value_scoring_panel(_packs())
    assert 'data-value-tier=' in html
    # At least one of the tier-words from PULSE-101 should appear as the attr
    assert any(f'data-value-tier="{t}"' in html for t in (
        "NOMINAL", "WATCH", "SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"
    ))
    # Tier-count chips marked for JS update
    assert 'data-tier-chip="value:' in html
    assert 'data-tier-count>' in html


def test_risk_scoring_rows_carry_tier_and_packname() -> None:
    html = render_mil_briefing.render_risk_scoring_panel(_packs())
    assert 'data-risk-tier=' in html
    assert any(f'data-risk-tier="{t}"' in html for t in (
        "NOMINAL", "WATCH", "ESCALATE", "REGULATORY-FLAG"
    ))
    assert 'data-tier-chip="risk:' in html


def test_placement_matrix_rows_carry_action_tier_and_diagnosis() -> None:
    """Placement matrix per-row attrs drive the 2x2 aggregate recompute."""
    html = render_mil_briefing.render_placement_matrix(_packs())
    assert 'data-action-tier=' in html
    assert 'data-diagnosis=' in html
    # All five aggregate-target tiles present
    for key in ("action-acute", "action-regflag", "action-commercial",
                "action-nominal-watch", "action-inconclusive"):
        assert f'data-aggregate="{key}"' in html


def test_placement_matrix_packname_matches_pack_dir_convention() -> None:
    """The row's data-packname must follow the seed pack-directory naming
    convention (<journey>__<signature>) so JS visibility filtering can
    cross-reference pack cards in the body."""
    html = render_mil_briefing.render_placement_matrix(_packs())
    # Spot-check one known pack
    assert 'data-packname="loans_apply_step3__dwell_after_error"' in html


def test_clark_protocol_tiles_have_aggregate_markers() -> None:
    html = render_mil_briefing.render_clark_protocol(_packs())
    assert 'data-aggregate="clark-positive"' in html
    assert 'data-aggregate="clark-negative"' in html
    assert 'data-aggregate="clark-total"' in html


def test_filter_js_has_v3_recompute_function() -> None:
    """The recomputeV3 + recomputeTierChips functions must appear in the
    embedded FILTER_JS — that's what the per-pack markers feed."""
    assert "function recomputeV3" in render_mil_briefing.FILTER_JS
    assert "function recomputeTierChips" in render_mil_briefing.FILTER_JS
    # And recomputeV3 is wired into applyFilters
    assert "recomputeV3(visibleCards)" in render_mil_briefing.FILTER_JS


def test_full_page_carries_full_v3_recompute_contract() -> None:
    """End-to-end: every V3 panel + aggregate marker + FILTER_JS hook
    appears in the composed page."""
    render_mil_briefing._PACK_CELL_INDEX = None
    html = render_mil_briefing.render_page(_packs())
    # Per-pack hooks
    assert html.count("data-packname=") >= 60  # 12 packs × ~5 V3 placements
    # Aggregate hooks for each subsystem
    for marker in (
        'data-aggregate="churn-score"',
        'data-aggregate="clark-positive"',
        'data-aggregate="action-acute"',
        'data-tier-chip="value:',
        'data-tier-chip="risk:',
    ):
        assert marker in html
    # JS wired
    assert "recomputeV3(visibleCards)" in html
