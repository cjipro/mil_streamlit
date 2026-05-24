"""HOL-6 MLOps Console wiring — the SYNTHESIS-MODE GOVERNANCE pane reads the REAL
synthesis_mode from pack metadata and shows the honest v1 attestation state, not a
fabricated mix of LLM_AUGMENTED packs + invented MRM reviewers / certifications.

This is the procurement gate's load-bearing truth: on a deterministic-locked v1
runtime the LLM_AUGMENTED count MUST be 0, and a procurement surface must not
assert governance (named reviewers, "certified") that never happened.

The other three panes (drift / fairness over-time / per-pack lineage verifier)
stay stubbed by design — they need run-history or a built decision-lineage chain
that a single-snapshot engine doesn't produce. Fabricating them would be the very
thing this pane exists to prevent. Out of scope here, not oversight.

Run:  python -m pytest holter/tests/test_mlops_wiring.py -q
"""

from __future__ import annotations

from holter.preview import render_mlops as M
from holter.preview._shared import discover_packs

_RUNNABLE = "loans_apply_step3__dwell_after_error"

# Content the stub fabricated that must never appear on a procurement gate.
_FABRICATED = ["J. Patel", "S. Khan", "MRM-A", "MRM-B",
               "independently_assessed", "certified"]


def _pack(name: str) -> dict:
    return next(p for p in discover_packs() if p["meta"]["pack_name"] == name)


# ── synthesis_governance reads real metadata ──────────────────────────────────

def test_synthesis_governance_real_deterministic_pack():
    g = M.synthesis_governance(_pack(_RUNNABLE))
    assert g["synthesis_mode"] == "DETERMINISTIC"      # from metadata.yaml
    assert g["attestation"] == "attestation_pending"   # honest: awaiting MRM sign-off
    assert g["reviewer"] == "—"                         # no review fabricated
    assert g["reviewed_date"] == "—"
    assert g["is_actionable"] is True


def test_synthesis_governance_respects_metadata_llm_mode():
    # If a pack's metadata ever declares llm_augmented, the pane reflects it.
    g = M.synthesis_governance({"meta": {"synthesis_mode": "llm_augmented"}})
    assert g["synthesis_mode"] == "LLM_AUGMENTED"
    assert g["attestation"] == "self_declared"


def test_synthesis_governance_defaults_deterministic():
    g = M.synthesis_governance({"meta": {}})
    assert g["synthesis_mode"] == "DETERMINISTIC"


def test_all_v1_packs_are_deterministic():
    # The locked v1 runtime ships only TemplateSynthesisProvider — no pack may
    # read LLM_AUGMENTED, so the procurement gate's violation count is 0.
    packs = discover_packs()
    assert packs  # sanity
    modes = {M.synthesis_governance(p)["synthesis_mode"] for p in packs}
    assert modes == {"DETERMINISTIC"}


# ── rendered synthesis pane ───────────────────────────────────────────────────

def test_synthesis_pane_has_no_fabricated_governance():
    html = M.render_synthesis_pane(discover_packs())
    for fake in _FABRICATED:
        assert fake not in html
    assert "DETERMINISTIC" in html
    # HOL-83 reframe: MRM attestation governance removed — pane is provenance now.
    assert "SYNTHESIS PROVENANCE" in html
    assert "attestation" not in html


def test_synthesis_pane_llm_chip_reads_zero():
    html = M.render_synthesis_pane(discover_packs())
    # the LLM_AUGMENTED headline chip must show 0 on the deterministic-locked runtime
    assert ">0</span><span class=\"headline-chip-label\">LLM_AUGMENTED</span>" in html


def test_mlops_page_renders_without_error():
    html = M.render_page()
    assert "SYNTHESIS PROVENANCE" in html
    for fake in _FABRICATED:
        assert fake not in html
