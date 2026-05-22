"""MA_D -> MA_S sessionisation (PULSE-34).

Reads the canonical MA_D event layer (Hive-partitioned Parquet) and produces the
MA_S session-grain fact layer: one row per session, ordered authoritatively by
`sequence_no` (NOT event_ts — the canonical schema rule, since network delivery
may reorder). DuckDB does the aggregation; output is Parquet partitioned by
journey_id. Supersedes the HDFS-CSV `poc/sessionise.py` proof of concept.

Run:
    py -m pulse.pipeline.sessionise --ma-d dist/ma_d --out dist/ma_s
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

# Session-grain aggregation. arg_min/arg_max over sequence_no give the
# authoritative entry/exit screen (ordering rule: sequence_no, not event_ts).
_MA_S_SQL = """
WITH ev AS (
    SELECT
        session_id, subject_id, journey_id, journey_category, cohort_tags,
        screen_id, sequence_no, event_type, payload_json,
        strptime(event_ts, '%Y-%m-%dT%H:%M:%SZ') AS event_ts
    FROM read_parquet($glob, hive_partitioning = true)
)
SELECT
    session_id,
    any_value(subject_id)                                        AS subject_id,
    any_value(journey_id)                                        AS journey_id,
    any_value(journey_category)                                  AS journey_category,
    any_value(cohort_tags)                                       AS cohort_tags,
    arg_min(screen_id, sequence_no)                              AS entry_screen,
    arg_max(screen_id, sequence_no)                              AS exit_screen,
    count(*)                                                     AS n_events,
    count(DISTINCT screen_id)                                    AS distinct_screens,
    min(event_ts)                                                AS started_ts,
    max(event_ts)                                                AS ended_ts,
    date_diff('second', min(event_ts), max(event_ts))           AS duration_seconds,
    count(*) FILTER (WHERE event_type = 'error')                 AS n_errors,
    count(*) FILTER (WHERE event_type = 'back_press')            AS n_back_press,
    count(*) FILTER (WHERE event_type = 'retry')                 AS n_retries,
    coalesce(max(
        CASE WHEN event_type = 'dwell'
             THEN TRY_CAST(json_extract(payload_json, '$.duration_seconds') AS DOUBLE)
        END), 0.0)                                               AS max_dwell_seconds,
    bool_or(event_type = 'error')                                AS had_error,
    (count(*) FILTER (WHERE event_type = 'back_press') >= 3)     AS multi_back_press,
    bool_or(event_type = 'nav_intent'
            AND json_extract_string(payload_json, '$.action') = 'exit') AS had_exit_intent,
    CASE
        WHEN bool_or(event_type = 'nav_intent'
                     AND json_extract_string(payload_json, '$.action') = 'exit')
             AND arg_max(screen_id, sequence_no) NOT LIKE '%confirm%'
             AND arg_max(screen_id, sequence_no) NOT LIKE '%trade%'
        THEN 'abandoned'
        WHEN arg_max(screen_id, sequence_no) LIKE '%confirm%'
             OR arg_max(screen_id, sequence_no) LIKE '%trade%'
        THEN 'completed'
        ELSE 'dropped'
    END                                                          AS outcome
FROM ev
GROUP BY session_id
"""


def sessionise(ma_d_dir: str | Path, out_dir: str | Path) -> dict[str, Any]:
    """Build MA_S from the MA_D layer. Returns a manifest carrying the source snapshot."""
    ma_d = Path(ma_d_dir)
    out = Path(out_dir)
    # Idempotent: clear any prior MA_S dataset so re-runs don't append/double rows.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    glob = str(ma_d / "**" / "*.parquet")
    con = duckdb.connect()
    try:
        # fetch_arrow_table() returns a pa.Table on both bank DuckDB 1.1.x and newer.
        table = con.execute(_MA_S_SQL, {"glob": glob}).fetch_arrow_table()
    finally:
        con.close()

    pq.write_to_dataset(table, root_path=str(out), partition_cols=["journey_id"])

    session_ids = table.column("session_id").to_pylist()
    snapshot_id = hashlib.sha256("".join(sorted(session_ids)).encode()).hexdigest()[:16]
    source_snapshot = _source_snapshot(ma_d)

    manifest = {
        "layer": "ma_s",
        "grain": "one row per session",
        "row_count": len(session_ids),
        "snapshot_id": snapshot_id,
        "source_layer": "ma_d",
        "source_snapshot_id": source_snapshot,
        "out_dir": str(out),
    }
    (out / "_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _source_snapshot(ma_d_dir: Path) -> str | None:
    """Read the upstream MA_D snapshot id for cross-layer lineage (PULSE-113 minimal)."""
    mf = ma_d_dir / "_MANIFEST.json"
    if not mf.exists():
        return None
    return json.loads(mf.read_text(encoding="utf-8")).get("snapshot_id")


def main() -> None:
    p = argparse.ArgumentParser(description="MA_D -> MA_S sessionisation (PULSE-34)")
    p.add_argument("--ma-d", type=str, default="dist/ma_d")
    p.add_argument("--out", type=str, default="dist/ma_s")
    args = p.parse_args()
    manifest = sessionise(args.ma_d, args.out)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
