"""Audit bundle — re-derivation evidence walked back from a decision to ingest.

A decision's artifact_id is its lineage_id; the bundle resolves the full chain
(ingest MA_D -> analyse MA_S -> analyse friction -> analyse decision), surfaces the
version/config stamps, and reports chain integrity (tamper-evident).
"""

from __future__ import annotations

import json

from pulse.audit import build_audit_bundle
from pulse.decision import build_decisions, read_decisions
from pulse.decision.lineage import DECISIONS_LINEAGE_LOG
from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.pipeline.sessionise import sessionise
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d


def _build(tmp_path):
    events, _ = generate(GeneratorConfig(n_sessions=500, seed=9, friction_rate=0.5))
    write_ma_d(events, tmp_path / "ma_d")
    build_pipeline_session_friction(tmp_path / "ma_d")
    sessionise(tmp_path / "ma_d", tmp_path / "ma_s")
    build_decisions(ma_s_dir=tmp_path / "ma_s")


def test_bundle_walks_decision_back_to_ingest(tmp_path):
    _build(tmp_path)
    decision = read_decisions()[0]
    bundle = build_audit_bundle(decision["lineage_id"])

    assert bundle["found"] is True
    assert bundle["chain_verified"] is True
    assert bundle["synthesis_mode"] == "deterministic"
    assert bundle["decision_pack_version"]

    chain = bundle["lineage_chain"]
    # ingest MA_D -> analyse MA_S -> analyse friction -> analyse decision
    assert len(chain) == 4
    assert chain[0]["operation"] == "ingest"
    assert chain[0]["inputs"] == []
    assert chain[-1]["lineage_id"] == decision["lineage_id"]
    assert bundle["produced_at"] == chain[-1]["ts"]
    # each downstream row names its upstream input (re-derivation contract)
    for prev, nxt in zip(chain, chain[1:]):
        assert prev["lineage_id"] in nxt["inputs"]


def test_unknown_artifact_id_not_found(tmp_path):
    _build(tmp_path)
    assert build_audit_bundle("does-not-exist")["found"] is False


def test_tampered_log_surfaces_in_bundle(tmp_path):
    _build(tmp_path)
    decision = read_decisions()[0]
    rows = [
        json.loads(line)
        for line in DECISIONS_LINEAGE_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0]["artifact_hash"] = "tampered"
    DECISIONS_LINEAGE_LOG.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    bundle = build_audit_bundle(decision["lineage_id"])
    assert bundle["chain_verified"] is False
    assert bundle.get("violations")
