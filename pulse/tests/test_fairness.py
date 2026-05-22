"""Fairness lens — disparate impact measured + wired onto high-stakes findings.

Kernel tests (demographic_parity + chi_squared) then end-to-end: the generator
plants disproportionate friction on the vulnerable cohort, the decision layer runs
the fairness lens on high-stakes findings only, and the measured disparity reflects
the planted over-representation.
"""

from __future__ import annotations

from pulse.convergence.fairness import assess_fairness, chi_squared_2x2
from pulse.decision import score_findings
from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.pipeline.sessionise import sessionise
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d


def test_demographic_parity_flags_disparate_impact():
    r = assess_fairness(protected_fired=40, protected_total=100,
                        reference_fired=20, reference_total=100)
    assert r.assessed
    assert r.protected_rate == 0.4 and r.reference_rate == 0.2
    assert r.disparity_ratio == 2.0
    assert r.disparate_impact is True
    assert r.statistically_significant is True
    assert set(r.methods) == {"demographic_parity", "chi_squared"}


def test_no_disparity_when_rates_equal():
    r = assess_fairness(protected_fired=20, protected_total=100,
                        reference_fired=20, reference_total=100)
    assert r.assessed
    assert r.disparity_ratio == 1.0
    assert r.disparate_impact is False


def test_insufficient_cohort_not_assessed():
    r = assess_fairness(protected_fired=1, protected_total=3,
                        reference_fired=10, reference_total=100)
    assert not r.assessed


def test_chi_squared_zero_margin_returns_none():
    assert chi_squared_2x2(0, 0, 5, 5) == (None, None)


def _ma_s(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=800, seed=4, friction_rate=0.4))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")
    sessionise(tmp_path / "ma_d", tmp_path / "ma_s")
    return tmp_path / "ma_s"


def test_fairness_lens_gated_to_high_stakes(tmp_path):
    decisions = score_findings(ma_s_dir=_ma_s(tmp_path))
    high = [d for d in decisions if d.risk_tier in {"ESCALATE", "REGULATORY-FLAG"}]
    low = [d for d in decisions if d.risk_tier == "NOMINAL"]
    assert high, "expected high-stakes findings"
    # at least some high-stakes findings are fairness-assessed
    assert any(d.fairness_assessed for d in high)
    # low-stakes findings are never assessed (gated, per the convergence design)
    assert all(not d.fairness_assessed for d in low)


def test_vulnerable_cohort_over_representation_is_measured(tmp_path):
    decisions = score_findings(ma_s_dir=_ma_s(tmp_path))
    assessed = [d for d in decisions if d.fairness_assessed and d.fairness_disparity_ratio]
    assert assessed, "expected at least one fairness-assessed finding"
    # the generator boosts vulnerable friction 1.7x -> protected rate exceeds reference
    over = [d for d in assessed if d.fairness_disparity_ratio > 1.0]
    assert len(over) >= len(assessed) / 2
