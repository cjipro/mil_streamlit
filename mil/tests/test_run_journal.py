"""
mil/tests/test_run_journal.py — MIL-186.

Run journal that powers `run_daily.py --resume`. Validates the resume logic
deterministically (no pipeline run): marking, completed-set, remaining-in-order,
fresh-run reset, and finish.

Run: py -m pytest mil/tests/test_run_journal.py -v
"""
from __future__ import annotations

import pytest

from mil.run_journal import RunJournal, STEP_ORDER


@pytest.fixture
def journal(tmp_path):
    return RunJournal(db_path=tmp_path / "rj.db")


def test_fresh_run_has_no_completed_steps(journal):
    journal.start_run("2026-06-24")
    assert journal.has_journal("2026-06-24")
    assert journal.completed_step_ids("2026-06-24") == set()
    assert journal.remaining_steps("2026-06-24") == STEP_ORDER


def test_mark_done_tracked(journal):
    journal.start_run("D")
    journal.mark("D", "1", "1  Fetch", "done", "10 new")
    journal.mark("D", "4", "4  Inference", "done", "ok")
    assert journal.completed_step_ids("D") == {"1", "4"}


def test_only_done_counts_not_fail_or_skip(journal):
    journal.start_run("D")
    journal.mark("D", "4b", "4b Vault", "fail", "HDFS down")
    journal.mark("D", "1", "1  Fetch", "skip", "--skip-fetch")
    journal.mark("D", "4", "4  Inference", "done", "ok")
    assert journal.completed_step_ids("D") == {"4"}


def test_remaining_preserves_canonical_order(journal):
    journal.start_run("D")
    # complete a scattered subset
    for sid in ("1", "2", "4", "4a", "4b", "4c", "4d", "4e", "4f", "5", "5b"):
        journal.mark("D", sid, f"{sid} x", "done")
    assert journal.remaining_steps("D") == ["5c", "5d", "5e"]      # in order, the tail


def test_resume_scenario_crash_after_5b(journal):
    # Simulate a normal run that crashed after Step 5b: 5c/5d/5e never marked.
    journal.start_run("2026-06-24")
    for sid in STEP_ORDER[:STEP_ORDER.index("5c")]:
        journal.mark("2026-06-24", sid, f"{sid} x", "done")
    # what --resume would run:
    assert journal.remaining_steps("2026-06-24") == ["5c", "5d", "5e"]


def test_start_run_resets_prior_attempt(journal):
    journal.start_run("D")
    journal.mark("D", "1", "1 x", "done")
    assert journal.completed_step_ids("D") == {"1"}
    journal.start_run("D")                      # fresh attempt same day
    assert journal.completed_step_ids("D") == set()
    assert journal.remaining_steps("D") == STEP_ORDER


def test_finish_run_records_status(journal):
    journal.start_run("D")
    journal.finish_run("D", "CLEAN")
    # has_journal still true; finishing doesn't delete rows
    assert journal.has_journal("D")


def test_has_journal_false_for_unknown_key(journal):
    assert journal.has_journal("never-started") is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
