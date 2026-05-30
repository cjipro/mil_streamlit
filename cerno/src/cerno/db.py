"""DuckDB connection factory.

In-memory by default; file-backed if a path is given. Sets sensible
defaults (threads = available CPUs); operator can override via pragmas
after connect().
"""

from __future__ import annotations

import os

import duckdb


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection.

    `path` — file path for persistent storage, or None for in-memory.

    Returns a connection with `threads` set to the available CPU count.
    """
    con = duckdb.connect(path) if path else duckdb.connect()
    threads = max(1, (os.cpu_count() or 1))
    con.execute(f"PRAGMA threads={threads}")
    return con
