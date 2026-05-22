"""Pipeline tests: synthetic MA_D generator -> MA_S sessionisation -> daily_journey_mart.

Covers the data-pipeline phases owned by while-sleeping (PULSE-28 / PULSE-34 /
PULSE-39, engine relocated under PULSE-128):
  - generator is deterministic for a fixed seed and emits schema-valid canonical events
  - sessionisation yields exactly one MA_S row per session, with entry/exit screens
    ordered by sequence_no (the canonical ordering rule, not event_ts)
  - the mart carries the upstream MA_S snapshot id (cross-box lineage)
"""

from __future__ import annotations

import duckdb

from pulse.pipeline.sessionise import sessionise
from pulse.schema.validate import validate
from pulse.serving.journey_mart import build_daily_journey_mart, read_daily_journey
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d

CFG = GeneratorConfig(n_sessions=120, seed=42, friction_rate=0.4)


def test_generator_is_deterministic_and_schema_valid(tmp_path):
    ev1, labels1 = generate(CFG)
    ev2, labels2 = generate(CFG)

    # Content is reproducible for a fixed seed (ids are RNG-derived, not uuid4).
    assert labels1 == labels2
    assert sorted(e["envelope"]["source_event_id"] for e in ev1) == \
        sorted(e["envelope"]["source_event_id"] for e in ev2)

    # Every canonical event validates against the schema (ingest validated already;
    # assert explicitly as a regression guard).
    for e in ev1:
        validate(e)

    # Snapshot is content-keyed -> stable across runs.
    m1 = write_ma_d(ev1, tmp_path / "a")
    m2 = write_ma_d(ev2, tmp_path / "b")
    assert m1["snapshot_id"] == m2["snapshot_id"]
    assert m1["row_count"] == len(ev1) > 0
    assert len(labels1) == CFG.n_sessions


def test_sessionise_one_row_per_session_ordered_by_sequence(tmp_path):
    ev, labels = generate(CFG)
    write_ma_d(ev, tmp_path / "ma_d")
    manifest = sessionise(tmp_path / "ma_d", tmp_path / "ma_s")

    # One MA_S row per session, and the lineage points back at the MA_D snapshot.
    assert manifest["row_count"] == len(labels)
    assert manifest["source_snapshot_id"] is not None

    # Expected entry/exit screens straight from MA_D, ordered by sequence_no.
    by_session: dict[str, list[tuple[int, str]]] = {}
    for e in ev:
        by_session.setdefault(e["identity"]["session_id"], []).append(
            (e["context"]["sequence_no"], e["context"]["screen_id"])
        )
    expected = {sid: (min(v)[1], max(v)[1]) for sid, v in by_session.items()}

    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT session_id, entry_screen, exit_screen, n_events "
            "FROM read_parquet(?, hive_partitioning = true)",
            [str(tmp_path / "ma_s" / "**" / "*.parquet")],
        ).fetchall()
    finally:
        con.close()

    assert len(rows) == len(labels)
    for session_id, entry_screen, exit_screen, n_events in rows:
        assert (entry_screen, exit_screen) == expected[session_id]
        assert n_events == len(by_session[session_id])


def test_daily_journey_mart_lineage_and_totals(tmp_path):
    ev, labels = generate(CFG)
    write_ma_d(ev, tmp_path / "ma_d")
    s_manifest = sessionise(tmp_path / "ma_d", tmp_path / "ma_s")
    m = build_daily_journey_mart(tmp_path / "ma_s")

    # Cross-box consistency: mart stamps the MA_S snapshot it was built from.
    assert m["source_snapshot_id"] == s_manifest["snapshot_id"]
    assert m["row_count"] > 0

    rows = read_daily_journey()
    # Every session lands in exactly one (journey, day) bucket.
    assert sum(r["sessions"] for r in rows) == len(labels)
    # Outcome split is exhaustive per row.
    for r in rows:
        assert r["completed"] + r["abandoned"] + r["dropped"] == r["sessions"]
