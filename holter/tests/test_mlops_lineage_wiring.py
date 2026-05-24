"""HOL-74 — MLOps LINEAGE VERIFIER pane wired to the REAL global decision-run
hash-chain (pulse.decision.lineage.verify_decision_lineage), replacing the
fabricated per-pack VERIFIED/BROKEN table (which invented a ~10% breakage rate
over chains that never existed — the engine seals ONE chain per run, not one
per pack).

Three honest states are covered: VERIFIED (clean sealed run), NO RUN (no chain
sealed yet), BROKEN (real violations). The latter two are monkeypatched on the
report so the test doesn't depend on mart file state.

Run:  python -m pytest holter/tests/test_mlops_lineage_wiring.py -q
"""

from __future__ import annotations

from holter.preview import render_mlops as M
from holter.preview._shared import discover_packs
from pulse.pipeline.run import run_pipeline


def test_lineage_report_is_real_dict_after_pipeline_run():
    run_pipeline(n_sessions=60, seed=7)  # seals marts/decisions_lineage.jsonl
    r = M._lineage_report()
    assert "total_rows" in r and "ok" in r
    assert r["ok"] is True
    assert r["total_rows"] > 0


def test_lineage_pane_verified_after_run():
    run_pipeline(n_sessions=60, seed=7)
    html = M.render_lineage_pane(discover_packs())
    assert "VERIFIED" in html
    assert "DECISION-CHAIN INTEGRITY" in html
    # old fabricated per-pack framing is gone
    assert "CHAIN HEALTH" not in html
    assert "synthesis-pending packs excluded" not in html


def test_lineage_pane_no_run_state(monkeypatch):
    monkeypatch.setattr(
        M, "_lineage_report",
        lambda: {"ok": False, "reason": "no_lineage_log", "total_rows": 0, "violations": 0},
    )
    html = M.render_lineage_pane(discover_packs())
    assert "NO RUN" in html
    assert "pulse.pipeline.run" in html  # honest remediation, not a fabricated green


def test_lineage_pane_broken_state_lists_real_violations(monkeypatch):
    monkeypatch.setattr(
        M, "_lineage_report",
        lambda: {
            "ok": False,
            "total_rows": 5,
            "violations": [{"kind": "row-hash-mismatch", "lineage_id": "abc123def456"}],
            "head_row_hash": "deadbeef" * 8,
        },
    )
    html = M.render_lineage_pane(discover_packs())
    assert "BROKEN" in html
    assert "row-hash-mismatch" in html  # the real violation kind is surfaced


def test_lineage_pane_unavailable_is_failsoft(monkeypatch):
    # If the engine import/verify blows up, _lineage_report returns verify_error;
    # the pane must render a (non-green) state, never crash or fake VERIFIED.
    monkeypatch.setattr(
        M, "_lineage_report",
        lambda: {"ok": False, "reason": "verify_error", "total_rows": 0, "violations": 0},
    )
    html = M.render_lineage_pane(discover_packs())
    assert "VERIFIED" not in html
    assert "DECISION-CHAIN INTEGRITY" in html
