"""Detection runtime over the real MA_D->MA_S pipeline sessions (the unified path).

Verifies the detector fires on the generator's planted friction across all four
v1 target screens, that the read layer then serves this pipeline-derived mart, and
that it stays screen-scoped to the four targets (no leakage onto other journeys).
"""

from __future__ import annotations

import duckdb

from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.serving import read
from pulse.serving.marts import PIPELINE_SESSION_FRICTION_PARQUET
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d

_TARGETS = {
    "loans.apply.step3",
    "international.beneficiary.setup",
    "cards.credit.apply.eligibility",
    "investments.premier.portfolio.overview",
}


def _fired_by_signature() -> dict[str, int]:
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT target_signature, sum(fired::int) "
            "FROM read_parquet(?) GROUP BY 1",
            [str(PIPELINE_SESSION_FRICTION_PARQUET)],
        ).fetchall()
    finally:
        con.close()
    return {sig: int(n or 0) for sig, n in rows}


def test_all_three_signatures_fire_over_pipeline(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=600, seed=11, friction_rate=0.5))
    write_ma_d(events, tmp_path / "ma_d")
    manifest = build_pipeline_session_friction(tmp_path / "ma_d")

    assert manifest["fired"] > 0
    assert manifest["source_snapshot_id"] is not None

    fired = _fired_by_signature()
    assert fired.get("dwell_after_error", 0) > 0
    assert fired.get("multi_back_press", 0) > 0
    assert fired.get("abandon_before_submit", 0) > 0


def test_read_layer_prefers_pipeline_mart(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=400, seed=5, friction_rate=0.5))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")

    s = read.summary()
    assert s["screens"] == 4          # exactly the four friction-target screens
    assert s["total_sessions"] > 0

    rows = read.friction_by_journey()
    # deepened journeys mean abandon now clears its prior-step precondition everywhere
    assert any(
        r["signature"] == "abandon_before_submit" and r["friction_sessions"] > 0
        for r in rows
    )


def test_detector_is_screen_scoped_to_targets(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=300, seed=3, friction_rate=0.4))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")

    con = duckdb.connect()
    try:
        screens = {
            r[0]
            for r in con.execute(
                "SELECT DISTINCT screen_id FROM read_parquet(?)",
                [str(PIPELINE_SESSION_FRICTION_PARQUET)],
            ).fetchall()
        }
    finally:
        con.close()
    assert screens <= _TARGETS
