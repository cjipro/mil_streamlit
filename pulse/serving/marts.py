"""Friction marts — materialise per-session detections to Parquet (PULSE-127).

Runs the detection runtime (PULSE-126) over the synthetic taq corpus and emits
ONE friction record per session: the session keyed to the detection produced by
its own FrictionBench cell's hypothesis. This is the "every session carries a
friction score" substrate the surfaces and the session-level analysis consume.

The corpus + per-cell hypotheses/baselines are reused from the detection
harness (`pulse.detection.frictionbench_run`) — a follow-up can promote those
generators to a public API; for now PULSE-127 imports them directly so there is
a single synthetic-corpus definition.

Output Parquet lands under ``dist/marts/`` (gitignored) — data is never
committed; only the code that regenerates it is.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pulse.detection.detect import Detection, Session, run_detection
from pulse.detection.frictionbench_run import (
    CELLS,
    _baseline_for,
    _hypothesis_for,
    generate_corpus,
)

REPO = Path(__file__).resolve().parents[2]
MARTS_DIR = REPO / "dist" / "marts"
SESSION_FRICTION_PARQUET = MARTS_DIR / "session_friction.parquet"

# Human-facing journey labels for the friction-target screens (the surfaces
# render these; the raw screen_id stays available for joins/drill).
_JOURNEY_LABELS = {
    "loans.apply.step3": "Loans · Apply · Step 3",
    "international.beneficiary.setup": "International · Beneficiary · Setup",
    "cards.credit.apply.eligibility": "Cards · Credit · Apply · Eligibility",
    "investments.premier.portfolio.overview": "Investments · Premier · Portfolio",
}

# Parquet schema — explicit so list<string> + nullable floats round-trip cleanly.
SESSION_FRICTION_SCHEMA = pa.schema([
    ("session_id", pa.string()),
    ("cell_id", pa.string()),
    ("screen_id", pa.string()),
    ("journey", pa.string()),
    ("target_signature", pa.string()),
    ("kind", pa.string()),                       # positive | negative | noise | negative_screen
    ("should_fire", pa.bool_()),                 # ground truth
    ("fired", pa.bool_()),                       # detection
    ("signature_id", pa.string()),               # null when not fired
    ("confidence", pa.float64()),                # P(friction), calibrated
    ("root_cause", pa.string()),
    ("time_to_detect_seconds", pa.float64()),
    ("cohort_tags", pa.list_(pa.string())),
    ("suppressed_by", pa.list_(pa.string())),
    ("method", pa.string()),
])


def journey_label(screen_id: str) -> str:
    return _JOURNEY_LABELS.get(screen_id, screen_id.split(".")[0].title())


def _kind_of(session_id: str) -> str:
    """Recover the corpus kind from the synthetic session id (``c{cell}-{kind}-{idx}``)."""
    parts = session_id.split("-")
    return parts[1] if len(parts) >= 3 else "unknown"


def _row(screen: str, signature: str, session: Session, gt: dict, det: Detection) -> dict:
    return {
        "session_id": session.session_id,
        "cell_id": gt["cell_id"],
        "screen_id": screen,
        "journey": journey_label(screen),
        "target_signature": signature,
        "kind": _kind_of(session.session_id),
        "should_fire": bool(gt["should_fire"]),
        "fired": bool(det.fired),
        "signature_id": det.signature_id,
        "confidence": float(det.confidence) if det.confidence is not None else None,
        "root_cause": det.root_cause,
        "time_to_detect_seconds": det.time_to_detect_seconds,
        "cohort_tags": list(session.cohort_tags),
        "suppressed_by": list(det.suppressed_by),
        "method": det.method,
    }


def build_session_friction(
    *, sessions_per_cell: int = 200, negative_pool_size: int = 120
) -> list[dict]:
    """Detector over the synthetic corpus → one friction record per session."""
    cell_sessions, negative_pool = generate_corpus(sessions_per_cell, negative_pool_size)

    rows: list[dict] = []
    for cell_id, screen, signature, _expect in CELLS:
        hyp = _hypothesis_for(cell_id, screen, signature)
        baseline = _baseline_for(signature, screen)
        for session, gt in cell_sessions[cell_id]:
            det = run_detection(hypothesis=hyp, session=session, baseline=baseline)
            rows.append(_row(screen, signature, session, gt, det))

    # Negative-screen pool: sessions on screens no pack owns. Screen-scoping
    # means every pack abstains, so these are friction-free by construction —
    # recorded so journey/volume totals include realistic non-friction traffic.
    for session, gt in negative_pool:
        rows.append({
            "session_id": session.session_id,
            "cell_id": "negative_screens",
            "screen_id": session.screen_id,
            "journey": journey_label(session.screen_id),
            "target_signature": "none",
            "kind": "negative_screen",
            "should_fire": False,
            "fired": False,
            "signature_id": None,
            "confidence": 0.0,
            "root_cause": None,
            "time_to_detect_seconds": None,
            "cohort_tags": [],
            "suppressed_by": [],
            "method": None,
        })
    return rows


def write_session_friction(
    *, sessions_per_cell: int = 200, negative_pool_size: int = 120
) -> Path:
    """Materialise the session-friction mart to Parquet. Returns the path."""
    rows = build_session_friction(
        sessions_per_cell=sessions_per_cell, negative_pool_size=negative_pool_size
    )
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=SESSION_FRICTION_SCHEMA)
    pq.write_table(table, SESSION_FRICTION_PARQUET)
    return SESSION_FRICTION_PARQUET


def main() -> None:
    path = write_session_friction()
    print(f"Wrote {path}  ({pq.read_metadata(path).num_rows:,} rows)")


if __name__ == "__main__":
    main()
