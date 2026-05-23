"""End-to-end v1 — one investigation through every engine layer (PULSE-98).

The "v0.1.0 actually works end-to-end" test: it composes the slices each prior
PULSE ticket built in isolation and asserts they fit together —
  events → analytics (PULSE-96) → synthesise (PULSE-94) → lineage + synthesise row
  (PULSE-89/97) → audit bundle (PULSE-97) — plus the example_pack content (PULSE-95).

Reconciled to reality (the ticket prose names some symbols that never shipped):
  - analytics entry is `build_analytic_outputs` (Cause class), not `ScopePipeline.run`
  - the audit bundle is the canonical JSON `build_audit_bundle` (PULSE-97 resolution;
    the ZIP `generate_bundle` + CLI were deferred to a distribution ticket)
  - all 3 altitudes render from the PULSE-95 hand-authored fixture (it covers the
    bank/signal vars real analytics doesn't emit yet — PULSE-96 extension is the follow-up);
    real analytics drives the journey altitude (the live-data path)
  - DETERMINISM is asserted on the synthesis ARTIFACT (artifact_text + artifact_hash) —
    the re-derivation contract (AUDIT_QUERY_SPEC step 6) — NOT the whole bundle, whose
    lineage_ids/timestamps are run-unique by design
  - the sequence_no-vs-event_ts ordering rule is enforced upstream in run_detection
    (ordered_events) and covered by test_detection, so it is not re-tested here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from pulse.analytics.cause import build_analytic_outputs
from pulse.audit import build_audit_bundle
from pulse.decision.lineage import build_decision_lineage
from pulse.decision_packs.validate import DecisionPackMetadataError, validate_metadata
from pulse.synthesis.base import (
    AnalyticOutputs,
    SynthesisMode,
    TemplateLibrary,
    TemplateSynthesisProvider,
)

_REPO = Path(__file__).resolve().parents[2]
_PACKS = _REPO / "pulse" / "decision_packs"
_LOANS_PACK = "loans_apply_step3__dwell_after_error"
_LOANS_JOURNEY_TMPL = _PACKS / _LOANS_PACK / "templates" / "journey.md.j2"
_EXAMPLE = _PACKS / "example_pack"
_FIXTURE = _EXAMPLE / "fixtures" / "analytic_outputs" / "cause.yaml"
_KEY = ("loans.apply.step3", "dwell_after_error")
_ALTITUDES = ("bank", "journey", "signal")

_PROVIDER = TemplateSynthesisProvider()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class _Dec:
    """Minimal decision — PULSE-98 proves COMPOSITION; decision content is tested in test_decisions."""

    screen_id: str
    signature: str

    def as_dict(self):
        return {"screen_id": self.screen_id, "signature": self.signature, "action_tier": "ACT"}


def _journey_from_real_analytics():
    """events → analytics (PULSE-96) → synthesise the journey altitude (PULSE-94)."""
    ao = build_analytic_outputs(_LOANS_PACK, sessions_per_cell=40)
    lib = TemplateLibrary(_LOANS_PACK, "1.0.0", {"journey": _LOANS_JOURNEY_TMPL.read_text(encoding="utf-8")})
    return ao, _PROVIDER.synthesise("cause", ao, lib)


def _fixture_ao() -> AnalyticOutputs:
    d = yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))
    return AnalyticOutputs(question_class=d["question_class"], payload=d["payload"])


def test_e2e_events_to_investigation_and_audit_bundle():
    """Full composition: real analytics → synthesis → lineage (+synthesise row) → audit bundle."""
    _ao, result = _journey_from_real_analytics()
    assert result.artifact_text.strip()
    assert result.artifact_hash == _sha(result.artifact_text)
    assert result.synthesis_mode == SynthesisMode.DETERMINISTIC

    summary = build_decision_lineage(
        [_Dec(*_KEY)],
        ma_s_manifest={"snapshot_id": "ms-e2e"},
        friction_manifest={"source_snapshot_id": "md-e2e"},
        bank_policy={},
        synthesis_by_decision={_KEY: result},
    )
    assert summary["chain_verified"] is True
    s_lid, _ = summary["synthesis_anchor"][_KEY]

    bundle = build_audit_bundle(s_lid)
    assert bundle["found"] is True and bundle["chain_verified"] is True
    # canonical sections per AUDIT_BUNDLE_EXAMPLE.md
    for section in ("lineage_chain", "pipeline_versions", "template_versions",
                    "decision_pack_version", "synthesis_mode", "configs", "chain_verified"):
        assert section in bundle
    assert bundle["synthesis_mode"] == "deterministic"
    assert bundle["template_versions"] == {s_lid: result.template_version}
    # chain captures ingest + analytics + synthesis (>= 3 rows), ending at the brief
    chain = bundle["lineage_chain"]
    assert len(chain) >= 3
    assert chain[0]["operation"] == "ingest"
    assert chain[-1]["operation"] == "synthesise"
    assert chain[-1]["artifact_hash"] == result.artifact_hash


def test_e2e_three_altitudes_render_from_fixture():
    """All 3 altitudes produce distinct artifacts (the PULSE-95 fixture covers every var)."""
    ao = _fixture_ao()
    hashes = {}
    for alt in _ALTITUDES:
        tmpl = (_EXAMPLE / "templates" / f"cause__{alt}.md.j2").read_text(encoding="utf-8")
        r = _PROVIDER.synthesise("cause", ao, TemplateLibrary("example_pack", "1.1.0", {alt: tmpl}))
        assert r.artifact_text.strip()
        assert r.artifact_hash == _sha(r.artifact_text)
        hashes[alt] = r.artifact_hash
    assert len(set(hashes.values())) == 3  # three distinct altitude renders


def test_e2e_artifact_determinism():
    """Load-bearing audit property: same inputs → byte-identical artifact + hash."""
    _, a = _journey_from_real_analytics()
    _, b = _journey_from_real_analytics()
    assert a.artifact_text == b.artifact_text
    assert a.artifact_hash == b.artifact_hash


def test_negative_missing_template_fails_loud():
    with pytest.raises(ValueError):  # empty library → no artifact to fake
        _PROVIDER.synthesise("cause", _fixture_ao(), TemplateLibrary("x", "1.0.0", {}))


def test_negative_missing_variable_fails_loud():
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):  # StrictUndefined → never a silent blank
        _PROVIDER.synthesise(
            "cause", AnalyticOutputs("cause", {}), TemplateLibrary("x", "1.0.0", {"j": "{{ missing }}"})
        )


def test_negative_llm_augmented_pack_refused():
    meta = {
        "pack_name": "x", "pack_version": "1.0.0", "required_pulse_version": ">=1.0.0,<2.0.0",
        "synthesis_mode": "llm_augmented", "authors": ["x"], "license": "Apache-2.0",
        "fairness_methods_required": True, "compliance_attestations": [],
    }
    with pytest.raises(DecisionPackMetadataError, match="llm_augmented"):
        validate_metadata(meta)
