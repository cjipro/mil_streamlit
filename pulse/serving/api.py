"""CJI Pulse engine — Platform API (FastAPI). Unified under PULSE-129.

The single backend API for the Pulse engine. Originally HOL-5's Platform API
(typed/OpenAPI), now unified with the decision/audit/CHRONICLE serving endpoints.
The Streamlit UI imports the engine directly and does NOT use this API.

FastAPI app that emits
investigation packs, lineage attestations, and verification reports.
Consumed by other tools (Tableau, Databricks Apps, bank-internal portals)
and by Holter's own UI surfaces.

**v0 (HOL-5):**
- ``GET /health`` — engine status + auth wiring status + MCP flag state
- ``GET /investigations`` — list registered packs (real)
- ``GET /investigations/{pack_name}`` — pack metadata + SHA-256 lineage anchor (real)
- ``POST /lineage/verify`` — verify a chain of lineage rows (real; uses pulse.lineage.verifier)
- ``POST /investigations/{pack_name}/run`` — **501** Designed Ceiling (PULSE-93)
- ``GET /signals`` — **501** Designed Ceiling (PULSE-93)
- ``GET /openapi.json`` — auto-generated OpenAPI 3.x spec

**Auth scaffolding:** placeholder middleware adds an
``X-Pulse-Auth-Status: not-wired-v0`` response header. No actual auth
mechanism (WorkOS / bank SSO / mTLS) is wired in v0. The header makes
the gap legible to clients without silently mis-claiming security.

**MCP:** behind ``PULSE_MCP_ENABLED=true`` env var. No MCP endpoints
registered in v0 — the structure is here, full MCP exposure deferred to
v2 per Kozyrkov governance concern (no per-claim attestation, no
rate-limiting yet).

Run locally::

    py -m pip install -e .[ui]
    py -m pip install uvicorn  # pending APPROVED_LIBRARIES.md gap close
    uvicorn pulse.serving.api:app --reload --port 8800   (or: py -m pulse.serving.api)

Then visit http://localhost:8800/docs for the auto-generated Swagger UI.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from pulse.audit import build_audit_bundle
from pulse.decision import (
    read_chronicle_candidates,
    read_decisions,
    verify_decision_lineage,
)
from pulse.lineage.verifier import verify_chain
from pulse.serving import read as friction_read
from pulse.serving.journey_mart import read_daily_journey
from pulse.serving.marts import PIPELINE_SESSION_FRICTION_PARQUET
from pulse.synthesis.base import SynthesisMode

_REPO = Path(__file__).resolve().parents[2]
PACKS_DIR = _REPO / "pulse" / "decision_packs"
MA_S_DIR = _REPO / "dist" / "ma_s"
MCP_ENABLED = os.environ.get("PULSE_MCP_ENABLED", "false").lower() == "true"


# --------------------------------------------------------------------- Schemas

class HealthResponse(BaseModel):
    status: str = Field(description="'ok' if app is up.")
    pulse_version: str = Field(description="Installed pulse package version.")
    synthesis_modes_declared: list[str] = Field(
        description="Modes declared in the SynthesisMode enum. Note: v1 only "
        "registers a provider for `deterministic`. Packs declaring "
        "`llm_augmented` will fail to resolve at engine startup.",
    )
    mcp_enabled: bool = Field(
        description="True if PULSE_MCP_ENABLED=true. No MCP endpoints "
        "registered in v0 regardless.",
    )
    auth_status: str = Field(
        description="v0: 'not-wired'. Auth mechanism (WorkOS / bank SSO / "
        "mTLS) deferred per HOL-5 ticket.",
    )


class PackSummary(BaseModel):
    pack_name: str
    pack_version: str
    synthesis_mode: str
    attestation_status: str
    attestation_framework: str


class ComplianceAttestation(BaseModel):
    name: str
    status: str
    last_reviewed: str


class PackDetail(BaseModel):
    pack_name: str
    pack_version: str
    required_pulse_version: str
    synthesis_mode: str
    authors: list[str]
    license: str
    fairness_methods_required: bool
    compliance_attestations: list[ComplianceAttestation]
    description: str | None = None
    notes: str | None = None
    lineage_anchor_sha256: str = Field(
        description="SHA-256 of the pack's metadata.yaml file bytes. "
        "v0 lineage anchor — extends to full hash chain when PULSE-93 lands.",
    )


class VerifyRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(
        description="Lineage rows to verify, in chain order.",
    )


class VerifyViolation(BaseModel):
    kind: str
    lineage_id: str
    expected: str
    actual: str


class VerifyResponse(BaseModel):
    ok: bool
    total_rows: int
    violations: list[VerifyViolation]
    last_lineage_id: str | None
    last_row_hash: str | None


# Friction read layer (PULSE-127) — DuckDB marts served to the surfaces.

class FrictionSummary(BaseModel):
    total_sessions: int
    friction_sessions: int
    fire_rate: float = Field(description="Share of sessions the detector fired on (0..1).")
    screens: int
    journeys: int


class JourneyFriction(BaseModel):
    journey: str
    screen_id: str
    signature: str
    sessions: int
    friction_sessions: int
    fire_rate: float
    mean_confidence: float | None = None


class CohortFriction(BaseModel):
    cohort: str
    friction_sessions: int
    mean_confidence: float | None = None


# --------------------------------------------------------------------- Helpers

def _pulse_version() -> str:
    try:
        return importlib.metadata.version("pulse")
    except importlib.metadata.PackageNotFoundError:
        return "(not installed)"


def _load_pack(pack_name: str) -> tuple[dict, str]:
    """Load pack metadata + SHA-256 of the file bytes. 404 if not found."""
    pack_dir = PACKS_DIR / pack_name
    metadata_path = pack_dir / "metadata.yaml"
    if not metadata_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Pack '{pack_name}' not found in {PACKS_DIR}.",
        )
    raw_bytes = metadata_path.read_bytes()
    metadata = yaml.safe_load(raw_bytes.decode("utf-8"))
    pack_hash = hashlib.sha256(raw_bytes).hexdigest()
    return metadata, pack_hash


# --------------------------------------------------------------------- App

app = FastAPI(
    title="CJI Pulse Engine API",
    version="0.1.0",
    description=(
        "The single backend API for the Pulse engine (all backend APIs are Pulse). "
        "Read-side investigation packs, friction marts, decisions (Risk/Value/Diagnosis), "
        "lineage attestations, audit bundles, and CHRONICLE candidates. The Streamlit UI "
        "(holter/) imports the engine directly and does NOT use this API — it is for external "
        "consumers (Tableau, Databricks, bank portals). run + signals blocked on PULSE-93."
    ),
)


@app.middleware("http")
async def auth_status_header(request: Request, call_next):
    """Placeholder auth middleware. Adds X-Pulse-Auth-Status header to every
    response so clients can see auth is not wired in v0 without parsing docs.
    """
    response = await call_next(request)
    response.headers["X-Pulse-Auth-Status"] = "not-wired-v0"
    return response


# --------------------------------------------------------------------- Routes

@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        pulse_version=_pulse_version(),
        synthesis_modes_declared=[m.value for m in SynthesisMode],
        mcp_enabled=MCP_ENABLED,
        auth_status="not-wired-v0",
    )


@app.get(
    "/investigations",
    response_model=list[PackSummary],
    tags=["investigations"],
    summary="List registered investigation packs",
)
def list_investigations() -> list[PackSummary]:
    if not PACKS_DIR.exists():
        return []
    summaries: list[PackSummary] = []
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        metadata_path = pack_dir / "metadata.yaml"
        if not metadata_path.exists():
            continue
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        first = (metadata.get("compliance_attestations") or [{}])[0]
        summaries.append(
            PackSummary(
                pack_name=metadata.get("pack_name", pack_dir.name),
                pack_version=metadata.get("pack_version", "?"),
                synthesis_mode=metadata.get("synthesis_mode", "?"),
                attestation_status=first.get("status", "—"),
                attestation_framework=first.get("name", "—"),
            )
        )
    return summaries


@app.get(
    "/investigations/{pack_name}",
    response_model=PackDetail,
    tags=["investigations"],
    summary="Pack metadata + SHA-256 lineage anchor",
)
def get_investigation(pack_name: str) -> PackDetail:
    metadata, pack_hash = _load_pack(pack_name)
    return PackDetail(
        pack_name=metadata["pack_name"],
        pack_version=metadata["pack_version"],
        required_pulse_version=metadata["required_pulse_version"],
        synthesis_mode=metadata["synthesis_mode"],
        authors=metadata["authors"],
        license=metadata["license"],
        fairness_methods_required=metadata["fairness_methods_required"],
        compliance_attestations=[
            ComplianceAttestation(**a) for a in metadata["compliance_attestations"]
        ],
        description=metadata.get("description"),
        notes=metadata.get("notes"),
        lineage_anchor_sha256=pack_hash,
    )


@app.post(
    "/investigations/{pack_name}/run",
    tags=["investigations"],
    summary="Run an investigation (501 in v0 — Designed Ceiling)",
    status_code=501,
)
def run_investigation(pack_name: str) -> dict:
    # Confirm pack exists so the 501 isn't masking a 404.
    _load_pack(pack_name)
    raise HTTPException(
        status_code=501,
        detail={
            "error": "engine_synthesis_layer_interface_only",
            "blocker": "PULSE-93",
            "message": (
                "TemplateSynthesisProvider.synthesise raises NotImplementedError. "
                "Pack runner ships when PULSE-93 lands. Per Article Zero, this "
                "surface declares its own incompleteness rather than returning "
                "fabricated synthesis output."
            ),
        },
    )


@app.get(
    "/signals",
    tags=["signals"],
    summary="List current signal state (501 in v0 — Designed Ceiling)",
    status_code=501,
)
def list_signals() -> dict:
    raise HTTPException(
        status_code=501,
        detail={
            "error": "signal_state_service_not_implemented",
            "blocker": "PULSE-93",
            "message": (
                "No analytics layer ships in v1; signal state is not yet "
                "materialised. Endpoint reserved for v1+."
            ),
        },
    )


@app.post(
    "/lineage/verify",
    response_model=VerifyResponse,
    tags=["lineage"],
    summary="Verify a chain of lineage rows",
)
def verify_lineage(req: VerifyRequest) -> VerifyResponse:
    report = verify_chain(req.rows)
    return VerifyResponse(
        ok=report.ok,
        total_rows=report.total_rows,
        violations=[
            VerifyViolation(
                kind=v.kind,
                lineage_id=v.lineage_id,
                expected=v.expected,
                actual=v.actual,
            )
            for v in report.violations
        ],
        last_lineage_id=report.last_lineage_id,
        last_row_hash=report.last_row_hash,
    )


# ---------------------------------------------------------------- Friction (PULSE-127)
# Real read-side data: the DuckDB friction marts the Streamlit surfaces consume.
# Synthetic taq corpus locally; real_bank served the same way on the work machine.

@app.get(
    "/friction/summary",
    response_model=FrictionSummary,
    tags=["friction"],
    summary="Overall friction posture across the corpus",
)
def friction_summary() -> FrictionSummary:
    return FrictionSummary(**friction_read.summary())


@app.get(
    "/friction/by-journey",
    response_model=list[JourneyFriction],
    tags=["friction"],
    summary="Per-journey × signature friction aggregates",
)
def friction_by_journey() -> list[JourneyFriction]:
    return [JourneyFriction(**r) for r in friction_read.friction_by_journey()]


@app.get(
    "/friction/by-cohort",
    response_model=list[CohortFriction],
    tags=["friction"],
    summary="Cohort cuts over fired sessions (fairness / vulnerability lens)",
)
def friction_by_cohort() -> list[CohortFriction]:
    return [CohortFriction(**r) for r in friction_read.friction_by_cohort()]


# ------------------------------------------------ Decisions + pipeline (PULSE-129)
# The decision / lineage / audit / CHRONICLE serving layer built in while-sleeping,
# unified into this one engine API. JSON returns (the read functions shape these).

@app.get("/friction/screen/{screen_id}", tags=["friction"],
         summary="Per-session friction drill for one screen")
def friction_screen(screen_id: str, limit: int = 50) -> list[dict]:
    return friction_read.sessions_for_screen(screen_id, limit=limit)


@app.get("/journeys/daily", tags=["pipeline"],
         summary="daily_journey_mart (MA_D -> MA_S pipeline)")
def journeys_daily() -> list[dict]:
    if not (MA_S_DIR / "_MANIFEST.json").exists():
        raise HTTPException(
            status_code=503,
            detail="MA_S not built yet — run `py -m pulse.pipeline.run` first.",
        )
    return read_daily_journey()


@app.get("/decisions", tags=["decisions"],
         summary="Scored findings: Risk + Value + Diagnosis + Action tier")
def decisions() -> list[dict]:
    if not (MA_S_DIR / "_MANIFEST.json").exists() or not PIPELINE_SESSION_FRICTION_PARQUET.exists():
        raise HTTPException(
            status_code=503,
            detail="Pipeline not run yet — run `py -m pulse.pipeline.run` first.",
        )
    return read_decisions()


@app.get("/lineage/verify", tags=["lineage"],
         summary="Verify the decision lineage log on disk (tamper-evidence)")
def lineage_verify_log() -> dict:
    return verify_decision_lineage()


@app.get("/audit/{artifact_id}", tags=["audit"],
         summary="Re-derivation evidence bundle for a decision (artifact_id = lineage_id)")
def audit(artifact_id: str) -> dict:
    bundle = build_audit_bundle(artifact_id)
    if not bundle.get("found"):
        raise HTTPException(status_code=404, detail=f"unknown artifact_id: {artifact_id}")
    return bundle


@app.get("/chronicle/candidates", tags=["chronicle"],
         summary="CHRONICLE candidates proposed from high-stakes findings")
def chronicle_candidates() -> list[dict]:
    return read_chronicle_candidates()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8800)


if __name__ == "__main__":
    main()
