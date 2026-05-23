"""HOL-3 Workspace wiring — the surface renders REAL synthesis analytics, not the
pre-PULSE-93 placeholders.

Before PULSE-93/96 shipped, the Workspace (`render_holter.py`) carried hardcoded
quality literals ("Confidence 0.82", "Designed ceiling 0.85"), a metadata-file sha
masquerading as the lineage badge, and a "Synthesis tier · awaiting PULSE-93
hydration" line. These tests pin that those are gone and that the boxes now read
the live `build_analytic_outputs` payload (confidence band/interval, Brier,
fairness flag, lineage anchor) via the `_shared` engine bridge.

Run:  python -m pytest holter/tests/test_workspace_wiring.py -q
"""

from __future__ import annotations

from holter.preview import render_holter as R
from holter.preview._shared import (
    analytics_quality_items,
    discover_packs,
    get_pack_analytics,
    lineage_anchor_short,
    short_hash,
)

_RUNNABLE = "loans_apply_step3__dwell_after_error"  # HYP + SAMPLES + META
_FIXTURE = "example_pack"                            # META only — not runnable, not discovered

# Placeholder strings that must NEVER reappear once the engine is wired.
_DEAD_PLACEHOLDERS = [
    "Confidence 0.82",
    "Designed ceiling 0.85",
    "Fairness attested",
    "Lineage anchored",
    "awaiting PULSE-93 hydration",
]


# ── engine bridge: fail-soft contract (mirrors get_pack_cell) ─────────────────

def test_get_pack_analytics_runnable_pack():
    out = get_pack_analytics(_RUNNABLE)
    assert out is not None
    assert out.question_class == "cause"
    assert len(out.payload["lineage_anchor"]) == 64  # sha256 hex


def test_get_pack_analytics_fixture_pack_is_none():
    # example_pack has no hypothesis.yaml → not runnable → fail-soft None.
    assert get_pack_analytics(_FIXTURE) is None


def test_get_pack_analytics_unknown_pack_is_none():
    assert get_pack_analytics("does-not-exist-pack") is None


# ── helpers ───────────────────────────────────────────────────────────────────

def test_lineage_anchor_short_matches_payload():
    out = get_pack_analytics(_RUNNABLE)
    assert lineage_anchor_short(_RUNNABLE) == short_hash(out.payload["lineage_anchor"])


def test_lineage_anchor_short_none_for_fixture():
    assert lineage_anchor_short(_FIXTURE) is None


def test_analytics_quality_items_are_real_not_literals():
    items = analytics_quality_items(_RUNNABLE)
    assert items is not None and len(items) == 4
    blob = " ".join(items)
    for dead in _DEAD_PLACEHOLDERS:
        assert dead not in blob
    assert items[0].startswith("Confidence ")
    assert items[1].startswith("Brier ")
    assert items[2].startswith("Fairness ")
    assert items[3].startswith("Lineage ")
    # the confidence item must carry a real band + interval, not a stub scalar
    assert any(band in items[0] for band in ("high", "medium", "low"))
    assert "[" in items[0] and "]" in items[0]


def test_analytics_quality_items_none_for_fixture():
    assert analytics_quality_items(_FIXTURE) is None


def test_quality_items_deterministic():
    assert analytics_quality_items(_RUNNABLE) == analytics_quality_items(_RUNNABLE)


# ── rendered surface: placeholders gone, real lineage badge present ───────────

def test_box1_renders_real_quality_strip_and_lineage_badge():
    packs = discover_packs()
    html = R.render_box1(packs, _RUNNABLE)
    for dead in _DEAD_PLACEHOLDERS:
        assert dead not in html
    # footer lineage badge is the REAL anchor, not the metadata-file sha
    assert f"lineage:{lineage_anchor_short(_RUNNABLE)}" in html


def test_box3_footer_carries_real_lineage_badge():
    packs = discover_packs()
    html = R.render_box3(packs, _RUNNABLE)
    assert f"lineage:{lineage_anchor_short(_RUNNABLE)}" in html
    assert "DuckDB time-series (stub)" not in html  # old dishonest label gone


def test_confidence_protocol_synthesis_is_live():
    packs = discover_packs()
    html = R.render_box_confidence_protocol(packs)
    assert "awaiting PULSE-93 hydration" not in html
    assert "Synthesis LIVE" in html


def test_full_page_has_no_dead_placeholders_and_carries_lineage():
    html = R.render_page()
    for dead in _DEAD_PLACEHOLDERS:
        assert dead not in html
    assert "lineage:" in html          # box footers
    assert "Synthesis LIVE" in html    # confidence protocol box
