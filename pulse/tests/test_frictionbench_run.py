"""Full FrictionBench run harness over the detection runtime (PULSE-126).

Asserts the 12-cell run produces a high macro-average, zero false positives
(in-cell + negative-screen), and passes the cell-10 acid test — on the
deterministic synthetic stand-in corpus. Reproducible.
"""

from __future__ import annotations

from pulse.detection.frictionbench_run import (
    CELLS,
    generate_corpus,
    run_frictionbench,
)


def test_twelve_cells_defined() -> None:
    assert len(CELLS) == 12
    # cell 10 is the engineered negative
    cell10 = next(c for c in CELLS if c[0] == 10)
    assert cell10[3] == "negative"
    assert cell10[1] == "investments.premier.portfolio.overview"
    assert cell10[2] == "dwell_after_error"


def test_full_run_scores_high_with_zero_false_positives() -> None:
    r = run_frictionbench(sessions_per_cell=100, negative_pool_size=60)
    assert set(r.per_cell_aggregate) == {c[0] for c in CELLS}
    assert all(agg > 0.9 for agg in r.per_cell_aggregate.values())
    assert r.macro_average > 0.95
    assert r.in_cell_false_positives == 0
    assert r.negative_screen_false_positives == 0
    # no penalty applied → penalised == macro
    assert r.penalised_score == r.macro_average


def test_cell10_acid_test_passes() -> None:
    """The load-bearing negative: discriminator suppresses, nothing fires."""
    r = run_frictionbench(sessions_per_cell=100, negative_pool_size=60)
    assert r.cell10_fired_count == 0
    assert r.cell10_aggregate > 0.9
    assert r.cell10_passed is True


def test_run_is_reproducible() -> None:
    a = run_frictionbench(sessions_per_cell=80, negative_pool_size=40)
    b = run_frictionbench(sessions_per_cell=80, negative_pool_size=40)
    assert a == b


def test_corpus_mix_ratios() -> None:
    cell_sessions, negative_pool = generate_corpus(sessions_per_cell=100, negative_pool_size=60)
    assert len(cell_sessions) == 12
    # 100 sessions per cell, ~65/25/10 split
    assert all(len(items) == 100 for items in cell_sessions.values())
    assert len(negative_pool) == 60
    # negative pool is on non-target screens
    target_screens = {c[1] for c in CELLS}
    assert all(sess.screen_id not in target_screens for sess, _ in negative_pool)


def test_render_is_ascii_safe() -> None:
    r = run_frictionbench(sessions_per_cell=40, negative_pool_size=20)
    out = r.render()
    out.encode("cp1252")  # must not raise (Windows stdout safety)
    assert "Macro-average" in out
    assert "Cell-10 acid test" in out
    assert "PASS" in out
