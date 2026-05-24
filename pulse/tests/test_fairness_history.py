"""Mixed-cohort corpus + per-run fairness history (PULSE-134).

Pins: the additive `mixed_cohorts`/`cohort_disparity` defaults leave the corpus
unchanged (580-test contract); mixed_cohorts gives within-cell cohort contrast so
assess_fairness is assessable; cohort_disparity drives demographic-parity down past
the 4/5ths band; backfill records a worsening-disparity fairness trend.
"""

from __future__ import annotations

from pulse.detection.frictionbench_run import CELLS, generate_corpus
from pulse.serving.run_history import (
    backfill_demo_history,
    compute_fairness_metrics,
    read_cell_metrics_history,
    read_fairness_history,
)

_POS_CELL = 1


def _by_cell(rows, cell_id):
    return next(r for r in rows if r["cell_id"] == cell_id)


# ── additive defaults preserve the single-cohort corpus ───────────────────────

def test_mixed_cohorts_default_off_unchanged():
    a, _ = generate_corpus(120, 30)
    b, _ = generate_corpus(120, 30, mixed_cohorts=False, cohort_disparity=0.0)
    for cid in a:
        assert sum(gt["should_fire"] for _, gt in a[cid]) == \
               sum(gt["should_fire"] for _, gt in b[cid])
        # single-cohort default: cell has one cohort tag (signature-derived)
        tags = {t for s, _ in a[cid] for t in s.cohort_tags}
        assert len(tags) <= 1


def test_mixed_cohorts_gives_two_well_populated_cohorts():
    cells, _ = generate_corpus(200, 0, mixed_cohorts=True)
    over = sum(1 for s, _ in cells[_POS_CELL] if "over_50" in s.cohort_tags)
    ref = len(cells[_POS_CELL]) - over
    assert over >= 5 and ref >= 5     # assess_fairness min_cohort satisfied
    assert abs(over - ref) <= 2        # ~50/50


def test_mixed_cohorts_does_not_flip_ground_truth():
    single, _ = generate_corpus(200, 0)
    mixed, _ = generate_corpus(200, 0, mixed_cohorts=True)
    for cid, *_ in CELLS:
        assert sum(gt["should_fire"] for _, gt in single[cid]) == \
               sum(gt["should_fire"] for _, gt in mixed[cid])


# ── fairness verdict ──────────────────────────────────────────────────────────

def test_fairness_clean_is_parity():
    f = _by_cell(compute_fairness_metrics(sessions_per_cell=200, cohort_disparity=0.0), _POS_CELL)
    assert f["assessed"] is True
    assert f["disparate_impact"] is False
    assert f["demographic_parity_ratio"] == 1.0


def test_fairness_disparity_flags_disparate_impact():
    clean = _by_cell(compute_fairness_metrics(sessions_per_cell=200, cohort_disparity=0.0), _POS_CELL)
    skewed = _by_cell(compute_fairness_metrics(sessions_per_cell=200, cohort_disparity=0.4), _POS_CELL)
    assert skewed["demographic_parity_ratio"] < clean["demographic_parity_ratio"]
    assert skewed["disparate_impact"] is True
    assert skewed["protected_rate"] < skewed["reference_rate"]


def test_fairness_deterministic():
    assert compute_fairness_metrics(sessions_per_cell=120, cohort_disparity=0.3) == \
           compute_fairness_metrics(sessions_per_cell=120, cohort_disparity=0.3)


# ── persistence: backfill records both detection + fairness trends ────────────

def test_backfill_records_worsening_fairness_trend(tmp_path):
    det = tmp_path / "det.jsonl"
    fair = tmp_path / "fair.jsonl"
    backfill_demo_history(days=10, sessions_per_cell=120, log_path=det, fairness_log_path=fair)
    assert det.exists() and fair.exists()
    series = read_cell_metrics_history(cell_id=_POS_CELL, log_path=fair)
    ratios = [r["demographic_parity_ratio"] for r in series]
    assert len(ratios) == 10
    assert ratios[-1] < ratios[0]     # disparity worsens across the window
    assert any(r["disparate_impact"] for r in series)  # crosses the 4/5ths band


def test_read_fairness_history_empty_default(tmp_path, monkeypatch):
    # read_fairness_history reads the default FAIRNESS_HISTORY_LOG; point it at an
    # empty tmp to assert the honest empty result.
    import pulse.serving.run_history as rh
    monkeypatch.setattr(rh, "FAIRNESS_HISTORY_LOG", tmp_path / "none.jsonl")
    assert read_fairness_history() == []
