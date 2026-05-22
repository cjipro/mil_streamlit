"""CHRONICLE candidate flow — high-stakes findings proposed for curation.

Verifies candidates are proposed for exactly the high-stakes set (top regulatory
exposure or a fairness-escalated disparity claim), that a candidate is an honest
curation work-item (no fabricated enforcement / public sources), that the seed
library yields no verified precedent yet, and that decisions carry the chronicle fields.
"""

from __future__ import annotations

from pulse.decision import build_decisions, read_chronicle_candidates, read_decisions
from pulse.decision.chronicle import chronicle_library, verified_precedents
from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.pipeline.sessionise import sessionise
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d


def _build(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=600, seed=9, friction_rate=0.5))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")
    sessionise(tmp_path / "ma_d", tmp_path / "ma_s")
    return build_decisions(ma_s_dir=tmp_path / "ma_s")


def test_high_stakes_findings_become_candidates(tmp_path):
    manifest = _build(tmp_path)
    assert manifest["chronicle_candidates"] > 0
    cands = read_chronicle_candidates()
    assert len(cands) == manifest["chronicle_candidates"]

    decisions = read_decisions()
    expected = [
        d for d in decisions
        if d["risk_tier"] == "REGULATORY-FLAG" or d["fairness_independent_review"]
    ]
    assert len(cands) == len(expected)


def test_candidate_is_a_curation_work_item_not_an_entry(tmp_path):
    _build(tmp_path)
    cands = read_chronicle_candidates()
    assert cands
    for c in cands:
        # honest boundary (Article Zero): never a fabricated enforcement entry
        assert c["enforcement_action"] is None
        assert c["public_sources"] == []
        assert c["verification_status"] == "pending_human_review"
        # carries the matchable pattern + evidence + lineage anchor for the curator
        assert set(c["friction_pattern"]) == {
            "signature_id", "journey_category", "screen_class", "severity",
        }
        assert c["proposed_from"]["lineage_id"]
        assert c["curator_actions_required"]


def test_seed_library_has_no_verified_precedent():
    assert chronicle_library()  # library loads (10 seed entries)
    # seed entries all ship pending_human_review -> matcher returns no verified precedent
    assert verified_precedents(
        signature_id="dwell_after_error",
        screen_class="credit_application",
        severity="P0",
    ) == []


def test_decisions_carry_chronicle_fields(tmp_path):
    _build(tmp_path)
    rows = read_decisions()
    assert all("chronicle_candidate" in r and "chronicle_matches" in r for r in rows)
    assert any(r["chronicle_candidate"] for r in rows)
