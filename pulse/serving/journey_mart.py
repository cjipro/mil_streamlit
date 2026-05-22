"""daily_journey_mart (PULSE-39) — per (journey × day) aggregates over MA_S.

The first mart built from the **MA_S session layer** of the data pipeline
(generator → MA_D → MA_S → here), as opposed to ``marts.py`` which materialises
the detection-corpus session-friction substrate. One row per (journey_id × day):
volume, outcome split, abandonment, error/back-press incidence, durations.

Surfaces never read MA_S directly — they read this pre-aggregated mart. The mart
manifest stamps the upstream MA_S ``source_snapshot_id`` so a surface rendering
several marts can assert they share one snapshot (PULSE-113 cross-box
consistency, minimal form; full registry is PULSE-117).

Run:
    py -m pulse.serving.journey_mart --ma-s dist/ma_s
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from pulse.serving.marts import MARTS_DIR

DAILY_JOURNEY_MART_PARQUET = MARTS_DIR / "daily_journey_mart.parquet"
_DEFAULT_MA_S = Path(__file__).resolve().parents[2] / "dist" / "ma_s"

_DAILY_JOURNEY_SQL = """
WITH s AS (
    SELECT *, CAST(started_ts AS DATE) AS event_date
    FROM read_parquet($glob, hive_partitioning = true)
)
SELECT
    journey_id,
    any_value(journey_category)                                  AS journey_category,
    event_date,
    count(*)                                                     AS sessions,
    count(*) FILTER (WHERE outcome = 'completed')                AS completed,
    count(*) FILTER (WHERE outcome = 'abandoned')                AS abandoned,
    count(*) FILTER (WHERE outcome = 'dropped')                  AS dropped,
    round(avg(CASE WHEN outcome = 'abandoned' THEN 1.0 ELSE 0.0 END), 4) AS abandonment_rate,
    round(avg(duration_seconds), 1)                              AS mean_duration_seconds,
    count(*) FILTER (WHERE had_error)                            AS error_sessions,
    count(*) FILTER (WHERE multi_back_press)                     AS multi_back_press_sessions,
    round(avg(n_events), 1)                                      AS mean_events,
    round(avg(max_dwell_seconds), 1)                             AS mean_max_dwell_seconds
FROM s
GROUP BY journey_id, event_date
ORDER BY event_date, journey_id
"""


def build_daily_journey_mart(ma_s_dir: str | Path = _DEFAULT_MA_S) -> dict[str, Any]:
    """Aggregate MA_S into the daily_journey_mart Parquet. Returns a manifest."""
    ma_s = Path(ma_s_dir)
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    glob = str(ma_s / "**" / "*.parquet")

    con = duckdb.connect(database=":memory:")
    try:
        # fetch_arrow_table() returns a pa.Table on both bank DuckDB 1.1.x and
        # newer; .arrow() returns a RecordBatchReader on newer DuckDB.
        table = con.execute(_DAILY_JOURNEY_SQL, {"glob": glob}).fetch_arrow_table()
    finally:
        con.close()

    pq.write_table(table, DAILY_JOURNEY_MART_PARQUET)

    snapshot_id = _mart_snapshot(table)
    manifest = {
        "mart": "daily_journey_mart",
        "grain": "one row per (journey_id, event_date)",
        "row_count": table.num_rows,
        "snapshot_id": snapshot_id,
        "source_layer": "ma_s",
        "source_snapshot_id": _source_snapshot(ma_s),
        "parquet": str(DAILY_JOURNEY_MART_PARQUET),
    }
    (MARTS_DIR / "daily_journey_mart._MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def read_daily_journey() -> list[dict]:
    """Read the daily_journey_mart as JSON-serialisable rows (FastAPI-facing)."""
    if not DAILY_JOURNEY_MART_PARQUET.exists():
        build_daily_journey_mart()
    con = duckdb.connect(database=":memory:")
    try:
        cur = con.execute(
            "SELECT * FROM read_parquet(?) ORDER BY event_date, journey_id",
            [str(DAILY_JOURNEY_MART_PARQUET)],
        )
        cols = [c[0] for c in cur.description]
        return [_jsonable(dict(zip(cols, row))) for row in cur.fetchall()]
    finally:
        con.close()


def _jsonable(row: dict) -> dict:
    """Coerce DATE → ISO string so the row crosses the FastAPI boundary cleanly."""
    out = dict(row)
    if "event_date" in out and out["event_date"] is not None:
        out["event_date"] = str(out["event_date"])
    return out


def _mart_snapshot(table: Any) -> str:
    keys = [
        f"{j}|{d}"
        for j, d in zip(table.column("journey_id").to_pylist(),
                        table.column("event_date").to_pylist())
    ]
    return hashlib.sha256("".join(sorted(keys)).encode()).hexdigest()[:16]


def _source_snapshot(ma_s_dir: Path) -> str | None:
    mf = ma_s_dir / "_MANIFEST.json"
    if not mf.exists():
        return None
    return json.loads(mf.read_text(encoding="utf-8")).get("snapshot_id")


def main() -> None:
    p = argparse.ArgumentParser(description="Build daily_journey_mart (PULSE-39)")
    p.add_argument("--ma-s", type=str, default=str(_DEFAULT_MA_S))
    args = p.parse_args()
    manifest = build_daily_journey_mart(args.ma_s)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
