"""Tests for the PULSE-127 friction endpoints on the Platform API (HOL-5).

Calls the route handlers directly (returns Pydantic models) so no HTTP/httpx
dependency is needed — exercises the API ↔ serving-layer wiring.
"""

from __future__ import annotations

from pulse.serving.api import friction_by_cohort, friction_by_journey, friction_summary
from pulse.serving.marts import write_session_friction


def _seed():
    write_session_friction(sessions_per_cell=40, negative_pool_size=20)


def test_friction_summary_endpoint():
    _seed()
    s = friction_summary()
    assert s.total_sessions > 0
    assert s.friction_sessions <= s.total_sessions
    assert 0.0 <= s.fire_rate <= 1.0


def test_friction_by_journey_endpoint():
    _seed()
    rows = friction_by_journey()
    assert rows
    assert all(0.0 <= r.fire_rate <= 1.0 for r in rows)
    assert {"loans.apply.step3", "cards.credit.apply.eligibility"} <= {r.screen_id for r in rows}


def test_friction_by_cohort_endpoint():
    _seed()
    rows = friction_by_cohort()
    assert rows
    assert "over_50" in {r.cohort for r in rows}
