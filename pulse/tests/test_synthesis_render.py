"""Integration: Phase-1 analytics payload hydrates the REAL journey template via
the deterministic provider (PULSE-94 + PULSE-96).

This is the positive proof that `AnalyticOutputs.payload` actually satisfies the
pack's `journey.md.j2` contract: the provider uses `StrictUndefined`, so a missing
template variable would RAISE — a clean render means every variable the template
references is present in the payload. (The hand-authored `samples/journey.md` is
NOT a value oracle — its comma-formatted numbers like `1,847` cannot come from
`{{ int }}` — so we render the real template with real synthetic data instead of
chasing a false byte-match.)
"""

from __future__ import annotations

from pathlib import Path

from pulse.analytics.cause import build_analytic_outputs
from pulse.synthesis.base import (
    SynthesisMode,
    TemplateLibrary,
    TemplateSynthesisProvider,
)

_PACK = "loans_apply_step3__dwell_after_error"
_REPO = Path(__file__).resolve().parents[2]
_JOURNEY_TMPL = _REPO / "pulse" / "decision_packs" / _PACK / "templates" / "journey.md.j2"


def _synthesise():
    out = build_analytic_outputs(_PACK, sessions_per_cell=40)
    lib = TemplateLibrary(
        name=_PACK,
        version="1.0.0",
        templates={"journey": _JOURNEY_TMPL.read_text(encoding="utf-8")},
    )
    result = TemplateSynthesisProvider().synthesise(
        question_class="cause", analytic_outputs=out, templates=lib
    )
    return out, result


def test_phase1_payload_hydrates_real_journey_template():
    out, result = _synthesise()
    # StrictUndefined would have raised on any missing var — a non-empty render proves
    # the payload key set satisfies journey.md.j2 (decision #4 of the plan).
    assert result.artifact_text.strip()
    assert out.payload["screen_id"] in result.artifact_text
    assert out.payload["signature_id"] in result.artifact_text
    assert result.synthesis_mode == SynthesisMode.DETERMINISTIC
    assert len(result.artifact_hash) == 64


def test_render_is_deterministic():
    _, a = _synthesise()
    _, b = _synthesise()
    assert a.artifact_text == b.artifact_text
    assert a.artifact_hash == b.artifact_hash
