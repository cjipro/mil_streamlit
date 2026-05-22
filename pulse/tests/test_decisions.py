"""Decision layer: Diagnosis + Risk + Value composed onto fired detections.

Builds the pipeline friction mart from generated MA_D, then verifies the scored
findings carry valid tiers, that the Action tier matches the Value x Risk 2x2,
that abandon findings carry recoverable volume, and that Diagnosis stays
NOT_ASSESSED until an assistance arm is supplied (then runs for real).
"""

from __future__ import annotations

from pulse.decision import build_decisions, score_findings
from pulse.diagnosis import JourneyArmObservation
from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.pipeline.sessionise import sessionise
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d

_RISK = {"NOMINAL", "WATCH", "ESCALATE", "REGULATORY-FLAG"}
_VALUE = {"NOMINAL", "WATCH", "SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"}
_ACTION = {"ACUTE", "REGULATORY-FLAG", "COMMERCIAL-OPPORTUNITY", "WATCH", "NOMINAL"}
_DIAGNOSES = {"SUPPORT_PROBLEM", "JOURNEY_PROBLEM", "BOTH", "INCONCLUSIVE"}


def _build_pipeline(tmp_path, *, seed=11, n=600, friction_rate=0.5):
    events, _ = generate(GeneratorConfig(n_sessions=n, seed=seed, friction_rate=friction_rate))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")   # writes the fixed friction mart
    sessionise(tmp_path / "ma_d", tmp_path / "ma_s")
    return tmp_path / "ma_s"


def test_decisions_have_valid_tiers_and_default_diagnosis(tmp_path):
    decisions = score_findings(ma_s_dir=_build_pipeline(tmp_path))
    assert len(decisions) > 0
    for d in decisions:
        assert d.risk_tier in _RISK
        assert d.value_tier in _VALUE
        assert d.action_tier in _ACTION
        assert d.severity in {"P0", "P1", "P2"}
        assert 0.0 <= d.fire_rate <= 1.0
        # synthetic pipeline is control-only — AI-placement diagnosis not assessable
        assert d.diagnosis == "NOT_ASSESSED"


def test_action_tier_matches_risk_value_2x2(tmp_path):
    for d in score_findings(ma_s_dir=_build_pipeline(tmp_path)):
        high_r = d.risk_tier in {"ESCALATE", "REGULATORY-FLAG"}
        high_v = d.value_tier in {"SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"}
        if high_r and high_v:
            assert d.action_tier == "ACUTE"
        elif high_r:
            assert d.action_tier == "REGULATORY-FLAG"
        elif high_v:
            assert d.action_tier == "COMMERCIAL-OPPORTUNITY"


def test_abandon_findings_carry_recoverable_volume(tmp_path):
    abandon = [
        d for d in score_findings(ma_s_dir=_build_pipeline(tmp_path))
        if d.signature == "abandon_before_submit"
    ]
    assert abandon, "expected abandon_before_submit findings"
    # abandoned sessions are recoverable completions if the friction is removed
    assert all(
        d.recoverable_sessions_per_week and d.recoverable_sessions_per_week > 0
        for d in abandon
    )


def test_diagnosis_runs_when_assistance_arm_supplied(tmp_path):
    ma_s = _build_pipeline(tmp_path)
    journeys = {d.journey_id for d in score_findings(ma_s_dir=ma_s)}
    arms = {j: JourneyArmObservation(n_sessions=300, success_rate=0.9) for j in journeys}
    scored = score_findings(ma_s_dir=ma_s, assistance_arms=arms)
    assert all(d.diagnosis in _DIAGNOSES for d in scored)


def test_build_decisions_writes_mart(tmp_path):
    manifest = build_decisions(ma_s_dir=_build_pipeline(tmp_path))
    assert manifest["row_count"] > 0
    assert manifest["deployment_id"] == "synthetic-taq"
    assert sum(manifest["action_tier_counts"].values()) == manifest["row_count"]


def test_completing_friction_carries_friction_time_value(tmp_path):
    """dwell/back_press sessions complete (recoverable_sessions ~ 0), but the friction
    time they cost is now surfaced as recoverable_friction_minutes — the value nuance."""
    decisions = score_findings(ma_s_dir=_build_pipeline(tmp_path))
    completing = [
        d for d in decisions
        if d.signature in ("dwell_after_error", "multi_back_press")
        and not d.recoverable_sessions_per_month
    ]
    assert completing, "expected completing-despite-friction findings"
    assert any(
        d.recoverable_friction_minutes_per_month and d.recoverable_friction_minutes_per_month > 0
        for d in completing
    )
