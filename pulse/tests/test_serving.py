"""Tests for the PULSE-127 serving layer (friction marts + DuckDB read)."""

from __future__ import annotations

from pulse.serving import read
from pulse.serving.marts import build_session_friction, write_session_friction

_TARGET_SCREENS = {
    "loans.apply.step3",
    "international.beneficiary.setup",
    "cards.credit.apply.eligibility",
    "investments.premier.portfolio.overview",
}

_ROW_KEYS = {
    "session_id", "cell_id", "screen_id", "journey", "target_signature",
    "kind", "should_fire", "fired", "signature_id", "confidence",
    "root_cause", "time_to_detect_seconds", "cohort_tags", "suppressed_by",
    "method",
}


def test_build_row_shape():
    rows = build_session_friction(sessions_per_cell=20, negative_pool_size=10)
    assert rows
    assert _ROW_KEYS <= set(rows[0])


def test_cell10_engineered_negative_never_fires():
    # cell 10 (long dwell on Premier portfolio = interest) is suppressed by the
    # negative_class_discriminator — its positive-slot sessions must NOT fire.
    rows = build_session_friction(sessions_per_cell=40, negative_pool_size=10)
    cell10 = [r for r in rows if r["cell_id"] == "10" and r["kind"] == "positive"]
    assert cell10
    assert all(not r["fired"] for r in cell10)
    assert all(r["suppressed_by"] for r in cell10)


def test_negative_screen_pool_never_fires():
    # Screen-scoping: sessions on non-target screens cannot fire.
    rows = build_session_friction(sessions_per_cell=20, negative_pool_size=30)
    neg = [r for r in rows if r["cell_id"] == "negative_screens"]
    assert neg
    assert all(not r["fired"] for r in neg)


def test_read_summary_invariants():
    write_session_friction(sessions_per_cell=50, negative_pool_size=30)
    s = read.summary()
    assert s["total_sessions"] > 0
    assert s["friction_sessions"] <= s["total_sessions"]
    assert 0.0 <= s["fire_rate"] <= 1.0


def test_read_friction_by_journey_covers_targets():
    write_session_friction(sessions_per_cell=50, negative_pool_size=30)
    rows = read.friction_by_journey()
    assert _TARGET_SCREENS <= {r["screen_id"] for r in rows}
    assert all(0.0 <= r["fire_rate"] <= 1.0 for r in rows)


def test_read_friction_by_cohort_nonempty():
    write_session_friction(sessions_per_cell=50, negative_pool_size=30)
    rows = read.friction_by_cohort()
    assert rows
    assert "over_50" in {r["cohort"] for r in rows}


def test_read_sessions_for_screen_drill():
    write_session_friction(sessions_per_cell=50, negative_pool_size=30)
    rows = read.sessions_for_screen("loans.apply.step3", limit=5)
    assert rows
    assert len(rows) <= 5
    assert all("session_id" in r for r in rows)
