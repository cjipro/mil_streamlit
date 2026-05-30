"""Tests for cerno.db — DuckDB connection factory."""

from __future__ import annotations

from pathlib import Path

from cerno.db import connect


def test_in_memory_connection_executes_simple_query() -> None:
    con = connect()
    try:
        result = con.execute("SELECT 42 AS answer").fetchone()
        assert result == (42,)
    finally:
        con.close()


def test_file_backed_persistence(tmp_path: Path) -> None:
    db_path = tmp_path / "cerno.duckdb"

    con1 = connect(str(db_path))
    con1.execute("CREATE TABLE t (x INTEGER)")
    con1.execute("INSERT INTO t VALUES (1), (2), (3)")
    con1.close()

    con2 = connect(str(db_path))
    try:
        result = con2.execute("SELECT SUM(x) FROM t").fetchone()
        assert result == (6,)
    finally:
        con2.close()


def test_threads_pragma_set() -> None:
    con = connect()
    try:
        # PRAGMA was set; the value should be a positive int.
        row = con.execute("SELECT current_setting('threads')").fetchone()
        assert int(row[0]) >= 1
    finally:
        con.close()
