"""Run the detection runtime over the pipeline's own sessions (PULSE-126 + PULSE-34).

Unifies the two friction substrates: instead of `/friction/*` serving the
detection-corpus fixture (`pulse.serving.marts.write_session_friction`), this runs
the *same* detection runtime over the **real MA_D → MA_S pipeline sessions** and
emits a drop-in `session_friction` mart from them.

How it works:
  - Reconstruct canonical-event sessions from the MA_D Parquet (grouped by
    session_id, ordered by sequence_no).
  - For each friction-target screen a session visited, build a screen-scoped
    `Session` (the detector keys on a single screen) carrying that screen's events
    plus session-level `features` derived here (the MA_S layer's job): dwell on the
    step, prior steps completed, whether it submitted.
  - Compute per-screen `ScreenBaseline`s from the pipeline itself (dwell mean/std
    over non-error dwells — the rolling-baseline idea, computed from data).
  - Run all three packs (the 12-cell hypotheses, reused from frictionbench_run so
    the engine keeps ONE hypothesis definition) over each (session, target) and
    record the detection.

`dwell_after_error` and `multi_back_press` detect purely from the event sequence;
`abandon_before_submit` fires where the journey supplies the prior-step precondition
and abstains elsewhere (honest — richer MA_S features are a follow-up).

Run:  py -m pulse.pipeline.detect_sessions --ma-d dist/ma_d
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

import pulse.detection.methods  # noqa: F401 — registers the analytic methods
from pulse.detection.detect import ScreenBaseline, Session, run_detection
from pulse.detection.frictionbench_run import CELLS, _SCREENS, _SIGNATURES, _hypothesis_for
from pulse.serving.marts import (
    MARTS_DIR,
    PIPELINE_SESSION_FRICTION_PARQUET,
    SESSION_FRICTION_SCHEMA,
    journey_label,
)

_DEFAULT_MA_D = Path(__file__).resolve().parents[2] / "dist" / "ma_d"
_CELL_BY = {(screen, sig): cid for cid, screen, sig, _ in CELLS}


def _load_sessions(ma_d_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Reconstruct canonical-event sessions from MA_D Parquet, ordered by sequence_no."""
    glob = str(Path(ma_d_dir) / "**" / "*.parquet")
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT session_id, cohort_tags, screen_id, sequence_no, event_type, "
            "event_ts, payload_json "
            "FROM read_parquet(?, hive_partitioning = true) "
            "ORDER BY session_id, sequence_no",
            [glob],
        ).fetchall()
    finally:
        con.close()

    sessions: dict[str, dict[str, Any]] = defaultdict(lambda: {"cohort": (), "events": []})
    for sid, cohort, screen, seq, etype, ts, payload_json in rows:
        s = sessions[sid]
        s["cohort"] = tuple(cohort) if cohort else ()
        s["events"].append({
            "identity": {"session_id": sid},
            "context": {"sequence_no": seq, "screen_id": screen},
            "event": {"event_type": etype, "event_ts": ts, "payload": json.loads(payload_json)},
        })
    return sessions


def _screen_baselines(sessions: dict[str, dict[str, Any]]) -> dict[str, ScreenBaseline]:
    """Per-screen dwell baseline, ROBUST to friction outliers.

    Friction dwells (post-error long dwells, abandonment dwells) are a minority on
    each screen but are large; mean/std would let them inflate the baseline and mask
    the very anomalies we detect. Median + MAD (scaled to a Gaussian sigma by 1.4826)
    track the normal-dwell bulk and ignore the outliers — so a planted 60s dwell still
    z-scores as anomalous against a ~14s normal baseline."""
    per_screen: dict[str, list[float]] = defaultdict(list)
    for s in sessions.values():
        for e in s["events"]:
            if e["event"]["event_type"] != "dwell":
                continue
            d = e["event"]["payload"].get("duration_seconds")
            if d is not None:
                per_screen[e["context"]["screen_id"]].append(float(d))

    out: dict[str, ScreenBaseline] = {}
    for scr, vals in per_screen.items():
        if len(vals) >= 4:
            med = statistics.median(vals)
            mad = statistics.median([abs(v - med) for v in vals])
            std = max(1.4826 * mad, 1.0)
            out[scr] = ScreenBaseline(scr, "dwell_seconds", med, std, len(vals))
        else:
            out[scr] = ScreenBaseline(scr, "dwell_seconds", 20.0, 5.0, len(vals))
    return out


def _derive_features(events: list[dict], target: str) -> dict[str, Any]:
    """Session-level features the methods read (MA_S layer's responsibility)."""
    order: list[str] = [e["context"]["screen_id"] for e in events]
    first_idx = order.index(target) if target in order else 0

    # distinct screens visited before the target -> step1..stepN tokens
    prior, seen = [], set()
    for scr in order[:first_idx]:
        if scr not in seen:
            seen.add(scr)
            prior.append(scr)
    prior_steps = [f"step{i + 1}" for i in range(len(prior))]

    dwells = [
        e["event"]["payload"].get("duration_seconds")
        for e in events
        if e["context"]["screen_id"] == target and e["event"]["event_type"] == "dwell"
    ]
    time_on_step = max((d for d in dwells if d is not None), default=None)

    submitted = any(("confirm" in s or "trade" in s) for s in order[first_idx:])
    return {
        "prior_steps_completed": prior_steps,
        "time_on_step_seconds": time_on_step,
        "submit_clicked": submitted,
    }


def _row(target: str, sig: str, sess: Session, det, cell_id: int) -> dict[str, Any]:
    return {
        "session_id": sess.session_id,
        "cell_id": str(cell_id),
        "screen_id": target,
        "journey": journey_label(target),
        "target_signature": sig,
        "kind": "pipeline",          # real pipeline session (no synthetic ground-truth label)
        "should_fire": None,         # ground truth not carried in the pipeline mart
        "fired": bool(det.fired),
        "signature_id": det.signature_id,
        "confidence": float(det.confidence) if det.confidence is not None else None,
        "root_cause": det.root_cause,
        "time_to_detect_seconds": det.time_to_detect_seconds,
        "cohort_tags": list(sess.cohort_tags),
        "suppressed_by": list(det.suppressed_by),
        "method": det.method,
    }


def build_pipeline_session_friction(ma_d_dir: str | Path = _DEFAULT_MA_D) -> dict[str, Any]:
    """Run the detection runtime over the pipeline's MA_D sessions; write the mart."""
    sessions = _load_sessions(ma_d_dir)
    baselines = _screen_baselines(sessions)

    rows: list[dict[str, Any]] = []
    for sid, s in sessions.items():
        events = s["events"]
        cohort = s["cohort"]
        screens = {e["context"]["screen_id"] for e in events}
        for target in _SCREENS:                       # the four v1 friction-target screens
            if target not in screens:
                continue
            target_events = tuple(e for e in events if e["context"]["screen_id"] == target)
            feats = _derive_features(events, target)
            baseline = baselines.get(target, ScreenBaseline(target, "dwell_seconds", 20.0, 5.0, 0))
            sess = Session(sid, target, cohort, target_events, feats)
            for sig in _SIGNATURES:
                cell_id = _CELL_BY[(target, sig)]
                det = run_detection(
                    hypothesis=_hypothesis_for(cell_id, target, sig),
                    session=sess,
                    baseline=baseline,
                )
                rows.append(_row(target, sig, sess, det, cell_id))

    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=SESSION_FRICTION_SCHEMA)
    pq.write_table(table, PIPELINE_SESSION_FRICTION_PARQUET)

    fired = sum(1 for r in rows if r["fired"])
    snapshot_id = _source_snapshot(Path(ma_d_dir))
    manifest = {
        "mart": "session_friction_pipeline",
        "grain": "one row per (session, target_screen, signature)",
        "row_count": len(rows),
        "fired": fired,
        "sessions_scored": len({r["session_id"] for r in rows}),
        "source_layer": "ma_d",
        "source_snapshot_id": snapshot_id,
        "parquet": str(PIPELINE_SESSION_FRICTION_PARQUET),
    }
    (MARTS_DIR / "session_friction_pipeline._MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def _source_snapshot(ma_d_dir: Path) -> str | None:
    mf = ma_d_dir / "_MANIFEST.json"
    if not mf.exists():
        return None
    return json.loads(mf.read_text(encoding="utf-8")).get("snapshot_id")


def main() -> None:
    p = argparse.ArgumentParser(description="Run detection runtime over pipeline sessions")
    p.add_argument("--ma-d", type=str, default=str(_DEFAULT_MA_D))
    args = p.parse_args()
    print(json.dumps(build_pipeline_session_friction(args.ma_d), indent=2))


if __name__ == "__main__":
    main()
