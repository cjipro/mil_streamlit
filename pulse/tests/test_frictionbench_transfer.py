"""
pulse/tests/test_frictionbench_transfer.py — PULSE-143.

Synthetic-to-real transfer evaluation: gap classification + TOST equivalence.
The statistics are validated here; the real corpus is the (deliberately) missing
input — exercised via the "unavailable" path.

Run: py -m pytest pulse/tests/test_frictionbench_transfer.py -v
"""
from __future__ import annotations

import pytest

from pulse.frictionbench.transfer import (
    EPSILON,
    classify_gap,
    compute_gap,
    evaluate_transfer,
    tost_equivalence,
)


# ---- gap + flag ---------------------------------------------------------

@pytest.mark.parametrize("gap,flag", [
    (0.00, "well_transferred"),
    (0.05, "well_transferred"),
    (0.10, "mild_overfit"),
    (0.15, "mild_overfit"),
    (0.25, "synthetic_overfitted"),
    (0.30, "synthetic_overfitted"),
    (0.45, "severe_overfit"),
    (-0.40, "severe_overfit"),       # magnitude-based: large negative still flags
])
def test_classify_gap_thresholds(gap, flag):
    assert classify_gap(gap) == flag


def test_compute_gap_is_signed():
    g = compute_gap(0.95, 0.90)
    assert g["synthetic_real_gap"] == 0.05
    assert g["flag"] == "well_transferred"
    g2 = compute_gap(0.95, 0.50)
    assert g2["synthetic_real_gap"] == 0.45
    assert g2["flag"] == "severe_overfit"


# ---- TOST ---------------------------------------------------------------

def test_unavailable_when_real_corpus_empty():
    res = tost_equivalence([0.9] * 12, [])
    assert res.status == "unavailable"
    assert res.equivalent is None
    assert res.n_real == 0


def test_insufficient_n_below_two():
    res = tost_equivalence([0.9, 0.9], [0.9])
    assert res.status == "insufficient_n"
    assert res.equivalent is None


def test_equivalent_when_samples_close():
    # two tight samples ~0.90 vs ~0.905 — well inside ±0.05
    syn = [0.90, 0.91, 0.89, 0.90, 0.92, 0.88, 0.90, 0.91]
    real = [0.90, 0.89, 0.91, 0.90, 0.88, 0.92, 0.90, 0.90]
    res = tost_equivalence(syn, real)
    assert res.status == "reported"
    assert res.equivalent is True
    assert res.badge == "equivalent_within_5pp"
    assert res.p_value < res.alpha


def test_not_equivalent_when_gap_large():
    syn = [0.95, 0.96, 0.94, 0.95, 0.96, 0.94, 0.95, 0.95]
    real = [0.55, 0.54, 0.56, 0.55, 0.53, 0.57, 0.55, 0.55]   # ~0.40 below
    res = tost_equivalence(syn, real)
    assert res.status == "reported"
    assert res.equivalent is False
    assert res.badge is None
    assert res.p_value >= res.alpha


def test_zero_variance_decided_on_point_difference():
    eq = tost_equivalence([0.90] * 5, [0.92] * 5)      # |diff|=0.02 < 0.05
    assert eq.equivalent is True
    assert eq.method == "degenerate_zero_variance"
    neq = tost_equivalence([0.90] * 5, [0.80] * 5)     # |diff|=0.10 >= 0.05
    assert neq.equivalent is False


def test_meets_min_n_flag():
    from pulse.frictionbench.transfer import MIN_N
    syn = [0.9] * 12
    real_small = [0.9 + (i % 3) * 0.001 for i in range(10)]
    real_big = [0.9 + (i % 3) * 0.001 for i in range(MIN_N)]
    assert tost_equivalence(syn, real_small).meets_min_n is False
    assert tost_equivalence(syn, real_big).meets_min_n is True


# ---- top-level report ---------------------------------------------------

def test_evaluate_transfer_unavailable_path_is_honest():
    rep = evaluate_transfer([0.9] * 12, real_example_scores=None)
    assert rep["real_set_reporting"]["status"] == "unavailable"
    assert rep["synthetic_score"] == 0.9
    assert rep["synthetic_real_gap"] is None        # NOT fabricated
    assert rep["flag"] is None
    assert rep["tost"]["status"] == "unavailable"


def test_evaluate_transfer_reported_path():
    syn = [0.90, 0.91, 0.89, 0.90, 0.92, 0.88]
    real = [0.90, 0.89, 0.91, 0.90, 0.88, 0.92]
    rep = evaluate_transfer(syn, real_example_scores=real)
    assert rep["real_set_reporting"]["status"] == "reported"
    assert "synthetic_real_gap" in rep
    assert rep["tost"]["status"] == "reported"
    assert rep["flag"] == "well_transferred"


def test_as_dict_is_json_safe():
    res = tost_equivalence([0.90, 0.91, 0.89, 0.90], [0.90, 0.89, 0.91, 0.90])
    d = res.as_dict()
    import json
    json.dumps(d)        # must not raise
    assert d["epsilon"] == EPSILON


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
