"""Lineage hash-chain through the decision mart — re-derivable + tamper-evident.

Builds the full pipeline + decisions, then verifies the lineage chain covers every
decision, that each decision mart row carries its anchor, and that mutating a row's
content is caught by the verifier.
"""

from __future__ import annotations

import json

from pulse.decision import build_decisions, read_decisions, verify_decision_lineage
from pulse.decision.lineage import DECISIONS_LINEAGE_LOG
from pulse.lineage.verifier import verify_chain
from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.pipeline.sessionise import sessionise
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d


def _build(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=500, seed=9, friction_rate=0.5))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")
    sessionise(tmp_path / "ma_d", tmp_path / "ma_s")
    return build_decisions(ma_s_dir=tmp_path / "ma_s")


def test_decision_lineage_chain_verifies(tmp_path):
    manifest = _build(tmp_path)
    assert manifest["lineage_verified"] is True

    report = verify_decision_lineage()
    assert report["ok"] is True
    assert report["violations"] == []
    # 3 stage rows (ingest MA_D + analyse MA_S + analyse friction) + one per decision
    assert report["total_rows"] == 3 + manifest["row_count"]


def test_every_decision_row_carries_its_anchor(tmp_path):
    _build(tmp_path)
    rows = read_decisions()
    assert rows
    for r in rows:
        assert r["lineage_id"]
        assert r["lineage_row_hash"]


def test_tampering_a_decision_breaks_the_chain(tmp_path):
    _build(tmp_path)
    log = [
        json.loads(line)
        for line in DECISIONS_LINEAGE_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # mutate a decision row's content after it was hashed -> row_hash no longer matches
    log[-1]["artifact_hash"] = "tampered"
    report = verify_chain(log)
    assert not report.ok
    assert any(v.kind == "row-hash-mismatch" for v in report.violations)
