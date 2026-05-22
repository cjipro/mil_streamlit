"""CJI Pulse engine — serving API (FastAPI).

The engine's HTTP boundary: read-only friction + journey queries over the marts.
This is the surface holter's front-end will eventually consume over HTTP (the
frontend<->engine split) — the engine owns it; holter never imports `pulse`
directly. Read-side only: no engine logic here, it queries the Parquet marts.

Endpoints:
    GET /healthz                       liveness + whether the MA_S pipeline has run
    GET /friction/summary              overall friction posture (session_friction mart)
    GET /friction/by-journey           per (journey x signature) aggregates
    GET /friction/by-cohort            cohort cuts (fairness lens)
    GET /friction/screen/{screen_id}   per-session drill for one screen
    GET /journeys/daily                daily_journey_mart (the MA_D->MA_S pipeline)

Run locally:
    uvicorn pulse.serving.api:app --port 8800
    # or: py -m pulse.serving.api

Note: uvicorn is the runtime ASGI server and sits in the APPROVED_LIBRARIES.md
t-z gap (pending bank-env confirmation). The app itself is fastapi + pydantic +
starlette (all approved) and is fully testable via fastapi.testclient without
uvicorn. The `/friction/*` endpoints self-materialise their (detection-corpus)
mart on first call; `/journeys/daily` requires `pulse.pipeline.run` to have built
MA_S first and returns 503 with a hint until then.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from pulse.serving import read
from pulse.serving.journey_mart import read_daily_journey

MA_S_DIR = Path(__file__).resolve().parents[2] / "dist" / "ma_s"

app = FastAPI(
    title="CJI Pulse Engine API",
    version="0.1.0",
    description="Read-only friction + journey serving layer over the Pulse marts. "
    "Owned by while-sleeping; consumed by the holter front-end over HTTP.",
)


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "service": "pulse-engine-api",
        "ma_s_pipeline_ran": (MA_S_DIR / "_MANIFEST.json").exists(),
    }


@app.get("/friction/summary")
def friction_summary() -> dict:
    return read.summary()


@app.get("/friction/by-journey")
def friction_by_journey() -> list[dict]:
    return read.friction_by_journey()


@app.get("/friction/by-cohort")
def friction_by_cohort() -> list[dict]:
    return read.friction_by_cohort()


@app.get("/friction/screen/{screen_id}")
def friction_screen(screen_id: str, limit: int = 50) -> list[dict]:
    return read.sessions_for_screen(screen_id, limit=limit)


@app.get("/journeys/daily")
def journeys_daily() -> list[dict]:
    if not (MA_S_DIR / "_MANIFEST.json").exists():
        raise HTTPException(
            status_code=503,
            detail="MA_S not built yet — run `py -m pulse.pipeline.run` first.",
        )
    return read_daily_journey()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8800)


if __name__ == "__main__":
    main()
