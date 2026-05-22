"""Smoke tests for the HOL-10 phase 3 utility-cluster panels.

Verifies that the four panels (notifications / canvas guide / settings /
avatar menu) render with the right anchors, content, and toggle wiring.
Falls back gracefully when the engine is unavailable.

Filed under HOL-10 phase 3.
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


def test_topnav_buttons_are_interactive_buttons_with_data_panel() -> None:
    """All four phase-3 controls must render as <button> elements with
    data-panel attributes — that's what PANEL_JS hooks onto."""
    html = render_mil_briefing.render_topnav(_packs())
    for btn_id, panel_id in [
        ("btn-notif", "panel-notif"),
        ("btn-guide", "panel-guide"),
        ("btn-settings", "panel-settings"),
        ("btn-avatar", "panel-avatar"),
    ]:
        assert f'id="{btn_id}"' in html, f"missing button id {btn_id}"
        assert f'data-panel="{panel_id}"' in html, (
            f"button {btn_id} missing data-panel={panel_id}"
        )


def test_notification_badge_shows_unread_count() -> None:
    html = render_mil_briefing.render_topnav(_packs())
    # Badge should be present with a count (synthesised events list)
    assert "topnav-icon-badge" in html
    # And the count should match the synthesise helper
    events = render_mil_briefing._synthesise_notifications(_packs())
    assert len(events) > 0
    assert f"{len(events)} unread" in html


def test_notif_panel_renders_synthesised_events() -> None:
    html = render_mil_briefing.render_notif_panel(_packs())
    assert "NOTIFICATIONS" in html
    assert 'id="panel-notif"' in html
    assert 'data-anchor="btn-notif"' in html
    # At least one event should mention the v2 spine
    assert "Pulse v2 design spine shipped" in html
    # Chronicle curator-pending note (load-bearing engine-state signal)
    assert "Chronicle library awaiting curator review" in html


def test_canvas_guide_drawer_lists_all_three_slot_classes() -> None:
    """The drawer is the on-screen reference for the canvas-as-discipline
    lock. Must list all three slot classes + the decision flow."""
    html = render_mil_briefing.render_guide_drawer()
    assert 'id="panel-guide"' in html
    assert "DECLARED" in html and "COMPUTED" in html and "ATTACHED" in html
    # Decision-flow chips
    for step in ("DIAGNOSIS", "RISK", "VALUE", "ACTION TIER"):
        assert step in html, f"decision-flow drawer missing step {step}"
    # Methodology design-doc pointers in the footer
    assert "DIAGNOSIS_DESIGN.md" in html
    assert "RISK_DESIGN.md" in html
    assert "VALUE_DESIGN.md" in html


def test_settings_panel_shows_methodology_versions() -> None:
    html = render_mil_briefing.render_settings_panel(_packs())
    assert 'id="panel-settings"' in html
    assert "METHODOLOGY VERSIONS" in html
    # All three methodology versions should appear (engine loaded successfully)
    assert "Diagnosis" in html and "Risk" in html and "Value" in html
    assert "v0.1.0" in html


def test_settings_toggles_wire_to_body_classes() -> None:
    """The 3 display toggles must declare data-toggle-class so PANEL_JS
    can wire them to body class toggles."""
    html = render_mil_briefing.render_settings_panel(_packs())
    for cls in ("hide-v3-scoring", "hide-pack-badges", "hide-placement-matrix"):
        assert f'data-toggle-class="{cls}"' in html


def test_avatar_menu_links_to_both_project_boards() -> None:
    html = render_mil_briefing.render_avatar_menu()
    assert 'id="panel-avatar"' in html
    assert "HUSSAIN AHMED" in html
    # Both project boards linked
    assert "PULSE — engine" in html
    assert "HOL — Holter" in html
    assert "cjipro.atlassian.net" in html
    # Sister-repo references
    assert "cjipro/holter" in html
    assert "cjipro/mil_streamlit" in html
    assert "cjipro/taq-app" in html


def test_all_panels_ship_hidden_by_default() -> None:
    """Panels render with hidden attr — PANEL_JS removes it on toggle."""
    packs = _packs()
    for fn in (
        render_mil_briefing.render_notif_panel,
        render_mil_briefing.render_settings_panel,
    ):
        html = fn(packs)
        assert " hidden " in html or " hidden>" in html
    for fn in (
        render_mil_briefing.render_guide_drawer,
        render_mil_briefing.render_avatar_menu,
    ):
        html = fn()
        assert " hidden " in html or " hidden>" in html


def test_settings_toggle_targets_match_panel_id_markers() -> None:
    """The settings toggles target V3 panels via data-panel-id markers.
    Make sure the three target IDs actually appear on the rendered V3
    panels — otherwise toggles would silently fail."""
    packs = _packs()

    value_html = render_mil_briefing.render_value_scoring_panel(packs)
    assert 'data-panel-id="value-scoring"' in value_html

    risk_html = render_mil_briefing.render_risk_scoring_panel(packs)
    assert 'data-panel-id="risk-scoring"' in risk_html

    matrix_html = render_mil_briefing.render_placement_matrix(packs)
    assert 'data-panel-id="placement-matrix"' in matrix_html


def test_full_page_render_includes_all_four_panels_and_panel_js() -> None:
    render_mil_briefing._PACK_CELL_INDEX = None
    packs = _packs()
    html = render_mil_briefing.render_page(packs)
    # All four panel root elements present
    assert 'id="panel-notif"' in html
    assert 'id="panel-guide"' in html
    assert 'id="panel-settings"' in html
    assert 'id="panel-avatar"' in html
    # PANEL_JS wired in
    assert "function closeAll()" in html
    # Search overlay still wired (we shouldn't have broken phase 2)
    assert 'id="search-overlay"' in html


def test_search_button_still_works_with_existing_search_js() -> None:
    """Phase 2's SEARCH_JS targets `.topnav-icon[title^=\"Search\"]` — we
    changed <span> to <button> and the title still starts with 'Search',
    so the existing selector still resolves."""
    html = render_mil_briefing.render_topnav(_packs())
    # The button still has the title prefix SEARCH_JS expects
    assert 'title="Search packs (click or press /)"' in html
    # And it's a button now (not a span)
    assert '<button class="topnav-icon" id="btn-search"' in html
