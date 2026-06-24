"""
hodos_kernel/tests/test_kernel.py — HODOS-4 spike.

Run: py -m pytest hodos_kernel/tests/test_kernel.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hodos_kernel.decision import DecisionLog, decide
from hodos_kernel.detectors import Signal
from hodos_kernel.kernel import run
from hodos_kernel.synthesis import get_provider

_PRODUCTS = Path(__file__).parent.parent / "products"
_PULSE = _PRODUCTS / "pulse_friction.yaml"
_TELCO = _PRODUCTS / "telco_churn.yaml"


def test_pulse_product_runs_end_to_end():
    pr = run(_PULSE, "deterministic")
    assert pr.product == "pulse_friction"
    assert pr.records > 0 and pr.signals > 0
    assert pr.decisions
    # the high-friction-by-design journey should surface as ACT
    top = pr.decisions[0]
    assert top.verdict == "ACT"
    assert "loans.apply.step3" in {d.subject for d in pr.decisions}


def test_two_products_one_engine_differ():
    pulse = run(_PULSE, "deterministic")
    telco = run(_TELCO, "deterministic")
    assert pulse.product != telco.product
    # different taxonomies entirely
    assert {d.subject for d in pulse.decisions}.isdisjoint({d.subject for d in telco.decisions})
    # telco's churn-by-design segment surfaces
    assert "mobile_payg" in {d.subject for d in telco.decisions}


def test_runtime_changes_narrative_not_decision():
    """The governance property: selectable runtime alters explanation, not verdict."""
    det = run(_PULSE, "deterministic")
    llm = run(_PULSE, "llm")
    assert [d.core() for d in det.decisions] == [d.core() for d in llm.decisions]   # identical decisions
    # but narratives differ + are tagged
    assert det.decisions[0].narrative != llm.decisions[0].narrative
    assert llm.decisions[0].narrative.startswith("[llm]")
    assert not det.decisions[0].narrative.startswith("[llm]")


def test_decision_log_hash_chain_verifies_and_detects_tamper():
    pr = run(_TELCO, "deterministic")
    assert pr.log.verify() is True
    # tamper with a logged decision → chain must break
    pr.log.rows[0]["decision"]["verdict"] = "IGNORE"
    assert pr.log.verify() is False


def test_decide_is_pure_threshold_logic():
    sigs = [Signal("e1", "g", "d", "lbl", "high", "x") for _ in range(3)]
    spec = {"thresholds": {"act": 9, "watch": 4},
            "score": {"weights": {"high": 3}}, "action_template": "{group}:{score}"}
    [d] = decide("p", sigs, spec)
    assert d.score == 9 and d.verdict == "ACT"
    spec["thresholds"] = {"act": 100, "watch": 4}
    [d2] = decide("p", sigs, spec)
    assert d2.verdict == "WATCH"


def test_provider_selection():
    assert get_provider("deterministic").mode == "deterministic"
    assert get_provider("llm").mode == "llm"
    with pytest.raises(ValueError):
        get_provider("quantum")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
