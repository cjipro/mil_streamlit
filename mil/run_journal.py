"""
mil/run_journal.py — MIL-186.

DuckDB-backed step-completion journal for the daily pipeline. Gives the
hand-rolled run_daily.py runner the *resume* half of durable execution
(double-fire is already prevented by the run_daily single-instance lockfile):

  • As a normal run progresses, each step is marked done/fail/skip here.
  • After a crash (BSOD, kill, power loss) mid-run, `py run_daily.py --resume`
    reads this journal, sees which steps already completed *today*, and runs
    only the remaining steps — no manual `--step 5c,5d,5e` archaeology.

This is the dependency-free fallback to a full durable-execution engine
(Temporal etc.): DuckDB is already on APPROVED_LIBRARIES and in the stack.
Everything here is fail-soft — a journal error must never break the pipeline,
so run_daily wraps all calls defensively.

Storage: mil/data/run_journal.db (gitignored, like the other *.db artifacts).
A `run_key` is the UTC date string — one logical daily run per key; a fresh
normal run resets that key's rows, a --resume run reads them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).resolve().parent / "data" / "run_journal.db"

# Canonical step order for resume — the isolated-capable step IDs in run order.
# (mirrors run_daily._VALID_STEPS; "3" is a dry-run marker, not a real step.)
STEP_ORDER: list[str] = ["1", "2", "4", "4a", "4b", "4c", "4d", "4e", "4f",
                         "5", "5b", "5c", "5d", "5e"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class RunJournal:
    """Append-only step journal. Per-call connections (no long-held handle) to
    avoid DuckDB file-lock contention — mirrors the chat SQL retriever pattern."""

    def __init__(self, db_path: Path | str = _DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        import duckdb
        return duckdb.connect(str(self.db_path))

    def _init_schema(self) -> None:
        con = self._connect()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS step_journal (
                    run_key  VARCHAR,
                    step_id  VARCHAR,
                    label    VARCHAR,
                    status   VARCHAR,   -- 'done' | 'fail' | 'skip'
                    detail   VARCHAR,
                    ts       VARCHAR
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS run_meta (
                    run_key   VARCHAR PRIMARY KEY,
                    started   VARCHAR,
                    finished  VARCHAR,
                    status    VARCHAR    -- 'running' | 'CLEAN' | 'PARTIAL' | 'FAILED'
                )
            """)
        finally:
            con.close()

    def start_run(self, run_key: str) -> None:
        """Begin a fresh normal run for run_key — clears any prior attempt's rows
        so a new full run never mistakes a crashed attempt's steps for done."""
        con = self._connect()
        try:
            con.execute("DELETE FROM step_journal WHERE run_key = ?", [run_key])
            con.execute("DELETE FROM run_meta WHERE run_key = ?", [run_key])
            con.execute(
                "INSERT INTO run_meta (run_key, started, finished, status) VALUES (?, ?, NULL, 'running')",
                [run_key, _now()],
            )
        finally:
            con.close()

    def mark(self, run_key: str, step_id: str, label: str, status: str, detail: str = "") -> None:
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO step_journal (run_key, step_id, label, status, detail, ts) VALUES (?, ?, ?, ?, ?, ?)",
                [run_key, step_id, label, status, str(detail)[:300], _now()],
            )
        finally:
            con.close()

    def completed_step_ids(self, run_key: str) -> set[str]:
        """Step IDs that reached status 'done' for run_key."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT DISTINCT step_id FROM step_journal WHERE run_key = ? AND status = 'done'",
                [run_key],
            ).fetchall()
            return {r[0] for r in rows}
        finally:
            con.close()

    def has_journal(self, run_key: str) -> bool:
        con = self._connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM run_meta WHERE run_key = ?", [run_key]).fetchone()[0]
            return bool(n)
        finally:
            con.close()

    def remaining_steps(self, run_key: str) -> list[str]:
        """Steps (in canonical order) not yet 'done' for run_key."""
        done = self.completed_step_ids(run_key)
        return [s for s in STEP_ORDER if s not in done]

    def finish_run(self, run_key: str, status: str) -> None:
        con = self._connect()
        try:
            con.execute(
                "UPDATE run_meta SET finished = ?, status = ? WHERE run_key = ?",
                [_now(), status, run_key],
            )
        finally:
            con.close()
