"""Friction read layer — DuckDB queries over the marts (PULSE-127).

The read API the FastAPI Platform API (HOL-5) serves to the Streamlit surfaces.
Pure read-side: no engine logic here — it queries the Parquet marts that
``marts.py`` materialised from the detection runtime. DuckDB reads Parquet
directly (zero-copy, pushdown), so this scales from the synthetic corpus to the
billion-row real_bank marts unchanged.

Every function returns plain ``list[dict]`` / ``dict`` (JSON-serialisable) so it
crosses the FastAPI boundary without a pandas dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from pulse.serving.marts import SESSION_FRICTION_PARQUET, write_session_friction


def _ensure_marts() -> Path:
    """Lazily materialise the mart if it isn't on disk yet (dev convenience)."""
    if not SESSION_FRICTION_PARQUET.exists():
        write_session_friction()
    return SESSION_FRICTION_PARQUET


def _rows(sql: str, params: list[Any] | None = None) -> list[dict]:
    """Run a query against the friction mart, return list[dict]."""
    path = _ensure_marts()
    con = duckdb.connect(database=":memory:")
    try:
        cur = con.execute(sql.replace("{mart}", "read_parquet(?)"), [str(path), *(params or [])])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def summary() -> dict:
    """Overall friction posture — totals across the corpus."""
    rows = _rows("""
        SELECT
            count(*)                                    AS total_sessions,
            sum(fired::INT)                             AS friction_sessions,
            round(avg(fired::INT), 4)                   AS fire_rate,
            count(DISTINCT screen_id)                   AS screens,
            count(DISTINCT journey)                     AS journeys
        FROM {mart}
    """)
    return rows[0] if rows else {}


def friction_by_journey() -> list[dict]:
    """Per (journey × target signature) friction aggregates — the feed data the
    Home queue + Workspace verdict are built from. Excludes the non-target
    negative-screen pool (no owning pack)."""
    return _rows("""
        SELECT
            journey,
            screen_id,
            target_signature                            AS signature,
            count(*)                                    AS sessions,
            sum(fired::INT)                             AS friction_sessions,
            round(avg(fired::INT), 4)                   AS fire_rate,
            round(avg(confidence) FILTER (WHERE fired), 4) AS mean_confidence
        FROM {mart}
        WHERE cell_id != 'negative_screens'
        GROUP BY journey, screen_id, target_signature
        ORDER BY friction_sessions DESC
    """)


def friction_by_cohort() -> list[dict]:
    """Cohort cuts over fired sessions — the fairness / vulnerability lens.
    UNNESTs the cohort_tags list so each tag is a row."""
    return _rows("""
        SELECT
            cohort,
            count(*)                                    AS friction_sessions,
            round(avg(confidence), 4)                   AS mean_confidence
        FROM (
            SELECT unnest(cohort_tags) AS cohort, confidence
            FROM {mart}
            WHERE fired
        )
        GROUP BY cohort
        ORDER BY friction_sessions DESC
    """)


def sessions_for_screen(screen_id: str, *, limit: int = 50) -> list[dict]:
    """Drill: individual session friction records for one screen (newest cap)."""
    return _rows("""
        SELECT session_id, kind, fired, signature_id, confidence,
               root_cause, cohort_tags, suppressed_by
        FROM {mart}
        WHERE screen_id = ?
        ORDER BY fired DESC, confidence DESC
        LIMIT ?
    """, [screen_id, limit])
