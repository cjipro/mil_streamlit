"""Serving API tests — exercise the FastAPI engine boundary via TestClient.

No uvicorn needed: TestClient drives the ASGI app directly. Covers liveness, the
self-materialising /friction/* endpoints, and /journeys/daily before vs after the
MA_D->MA_S pipeline has run.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pulse.pipeline.run import run_pipeline
from pulse.serving.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "pulse_version" in body
    assert "synthesis_modes_declared" in body


def test_friction_endpoints_self_materialise():
    # read.py lazily builds the detection-corpus mart, so these work with no pipeline run.
    r = client.get("/friction/summary")
    assert r.status_code == 200
    assert r.json()["total_sessions"] > 0

    r = client.get("/friction/by-journey")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) > 0
    assert {"journey", "signature", "fire_rate"} <= set(rows[0])

    r = client.get("/friction/by-cohort")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_journeys_daily_after_pipeline_run():
    # Build the MA_S spine, then the endpoint serves the daily_journey_mart.
    result = run_pipeline(n_sessions=80, seed=7)
    assert result["sessions"] == 80

    r = client.get("/journeys/daily")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) > 0
    # every session lands in exactly one (journey, day) bucket
    assert sum(x["sessions"] for x in rows) == 80
    assert {"journey_id", "event_date", "sessions", "abandonment_rate"} <= set(rows[0])
