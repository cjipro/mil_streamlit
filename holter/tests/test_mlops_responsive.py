"""HOL-79 — MLOps responsive grid (finishing the HOL-73 responsive pass).

The MLOps 4-pane grid uses the laptop-first uniform-cell model: panes stay
~560-620px and ADD columns as the viewport grows (2 at laptop → 3/4 on wide),
rather than 2 panes widening unboundedly. `auto-fill` (not `auto-fit`) keeps the
panes bounded when there are empty tracks on very wide monitors. Column behaviour
itself is verified in-browser; this guards the served CSS rule against regression.

Run:  python -m pytest holter/tests/test_mlops_responsive.py -q
"""

from __future__ import annotations

from holter.server import app


def _served(path: str) -> str:
    return app.test_client().get(path).get_data(as_text=True)


def test_mlops_grid_is_autofill_column_adding():
    css = _served("/mlops")
    assert "repeat(auto-fill, minmax(560px, 1fr))" in css


def test_old_mlops_grid_collapse_breakpoint_is_gone():
    # The superseded hard 1100px collapse for .mlops-grid must not return —
    # auto-fill now handles the single-column drop on its own. (Scoped to the
    # mlops-grid selector: other surfaces legitimately keep 1100px breakpoints.)
    css = _served("/mlops")
    assert "@media (max-width: 1100px) { .mlops-grid" not in css
