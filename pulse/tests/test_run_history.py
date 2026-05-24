"""Run-history persistence + controlled corpus drift (PULSE-133).

Pins: the additive `seed`/`drift_pct` defaults leave the corpus + metrics
unchanged (the 570-test determinism contract); drift degrades recall WITHOUT
flipping ground truth; record→read round-trips; backfill yields a real declining
trend.
"""

from __future__ import annotations

from pulse.detection.frictionbench_run import CELLS, generate_corpus
from pulse.serving.run_history import (
    backfill_demo_history,
    compute_cell_metrics,
    read_cell_metrics_history,
    record_run,
)

_POS_CELL = 1  # loans.apply.step3 × dwell_after_error (positive)


def _by_cell(rows, cell_id):
    return next(r for r in rows if r["cell_id"] == cell_id)


# ── additive defaults preserve today's behaviour ──────────────────────────────

def test_default_corpus_unchanged_by_new_kwargs():
    # seed=None, drift_pct=0.0 (defaults) must reproduce the no-kwarg corpus shape.
    a_cells, a_neg = generate_corpus(120, 30)
    b_cells, b_neg = generate_corpus(120, 30, seed=None, drift_pct=0.0)
    assert {c: len(v) for c, v in a_cells.items()} == {c: len(v) for c, v in b_cells.items()}
    # ground-truth should_fire counts identical (no degraded positives injected)
    for cid in a_cells:
        assert sum(gt["should_fire"] for _, gt in a_cells[cid]) == \
               sum(gt["should_fire"] for _, gt in b_cells[cid])


def test_clean_run_has_full_recall_and_no_gap():
    rows = compute_cell_metrics(sessions_per_cell=120, drift_pct=0.0)
    pos = _by_cell(rows, _POS_CELL)
    assert pos["detection_rate"] == 1.0      # all true positives detected
    assert pos["accuracy_gap"] == 0.0
    assert pos["false_positive_rate"] == 0.0


def test_compute_is_deterministic():
    assert compute_cell_metrics(sessions_per_cell=120, drift_pct=0.0) == \
           compute_cell_metrics(sessions_per_cell=120, drift_pct=0.0)


# ── drift degrades recall but not ground truth ────────────────────────────────

def test_drift_reduces_recall_monotonically():
    clean = _by_cell(compute_cell_metrics(sessions_per_cell=200, drift_pct=0.0), _POS_CELL)
    drifted = _by_cell(compute_cell_metrics(sessions_per_cell=200, drift_pct=0.4), _POS_CELL)
    assert drifted["detection_rate"] < clean["detection_rate"]
    assert drifted["accuracy_gap"] > clean["accuracy_gap"]


def test_drift_does_not_flip_ground_truth():
    clean, _ = generate_corpus(200, 0, drift_pct=0.0)
    drifted, _ = generate_corpus(200, 0, drift_pct=0.4)
    for cid, _screen, _sig, _expect in CELLS:
        n_clean = sum(gt["should_fire"] for _, gt in clean[cid])
        n_drift = sum(gt["should_fire"] for _, gt in drifted[cid])
        assert n_clean == n_drift  # degraded positives keep should_fire=True


def test_cell10_negative_never_degrades():
    drifted = _by_cell(compute_cell_metrics(sessions_per_cell=200, drift_pct=0.5), 10)
    assert drifted["ground_truth_class"] == "negative"
    assert drifted["false_positive_rate"] == 0.0  # stays the clean discriminator


# ── persistence: record / read / backfill ─────────────────────────────────────

def test_record_read_roundtrip(tmp_path):
    log = tmp_path / "hist.jsonl"
    rows = compute_cell_metrics(sessions_per_cell=60, drift_pct=0.0)
    assert record_run("2026-05-24T06:00:00Z", rows, log_path=log) == len(rows)
    back = read_cell_metrics_history(log_path=log)
    assert len(back) == len(rows)
    assert all(r["run_ts"] == "2026-05-24T06:00:00Z" for r in back)


def test_read_empty_when_no_log(tmp_path):
    assert read_cell_metrics_history(log_path=tmp_path / "nope.jsonl") == []


def test_backfill_yields_declining_trend(tmp_path):
    log = tmp_path / "hist.jsonl"
    n = backfill_demo_history(days=10, sessions_per_cell=120, log_path=log)
    assert n == 10 * len(CELLS)
    series = read_cell_metrics_history(cell_id=_POS_CELL, log_path=log)
    rates = [r["detection_rate"] for r in series]
    assert len(rates) == 10
    assert rates[-1] < rates[0]       # recall declines across the window (drift)
    assert len(set(rates)) > 1        # non-flat


def test_read_filters_by_cell_and_signature(tmp_path):
    log = tmp_path / "hist.jsonl"
    backfill_demo_history(days=3, sessions_per_cell=60, log_path=log)
    only = read_cell_metrics_history(cell_id=_POS_CELL, log_path=log)
    assert only and all(r["cell_id"] == _POS_CELL for r in only)
    by_sig = read_cell_metrics_history(signature="dwell_after_error", log_path=log)
    assert by_sig and all(r["signature_id"] == "dwell_after_error" for r in by_sig)
