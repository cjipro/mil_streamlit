"""PULSE-95: example_pack content renders cleanly through the provider.

Loads the hand-authored Cause `AnalyticOutputs` fixture + the three Cause altitude
templates and renders them via `TemplateSynthesisProvider`. The provider uses
`StrictUndefined`, so a missing variable would RAISE — a clean render is positive
proof the fixture satisfies every template's variable contract. Determinism is
asserted on the artifact hash.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pulse.synthesis.base import (
    AnalyticOutputs,
    SynthesisMode,
    TemplateLibrary,
    TemplateSynthesisProvider,
)

_PACK = Path(__file__).resolve().parents[1] / "decision_packs" / "example_pack"
_TEMPLATES = _PACK / "templates"
_FIXTURE = _PACK / "fixtures" / "analytic_outputs" / "cause.yaml"
_ALTITUDES = ("bank", "journey", "signal")


def _fixture() -> AnalyticOutputs:
    d = yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))
    return AnalyticOutputs(question_class=d["question_class"], payload=d["payload"])


def _render(altitudes):
    ao = _fixture()
    lib = TemplateLibrary(
        name="journey_friction",
        version="1.1.0",
        templates={a: (_TEMPLATES / f"cause__{a}.md.j2").read_text(encoding="utf-8") for a in altitudes},
    )
    return TemplateSynthesisProvider().synthesise(
        question_class="cause", analytic_outputs=ao, templates=lib
    )


def test_fixture_is_cause_class():
    assert _fixture().question_class == "cause"


@pytest.mark.parametrize("altitude,marker", [
    ("bank", "Bank altitude"),
    ("journey", "Journey altitude"),
    ("signal", "Signal altitude"),
])
def test_each_altitude_renders(altitude, marker):
    r = _render([altitude])
    assert marker in r.artifact_text
    assert r.synthesis_mode == SynthesisMode.DETERMINISTIC
    assert len(r.artifact_hash) == 64


def test_narrative_altitudes_name_the_screen():
    # bank + journey reference screen_id; signal is method/evidence-shaped and does not.
    for altitude in ("bank", "journey"):
        assert "loans.apply.step3" in _render([altitude]).artifact_text


def test_three_altitude_single_surface_concatenates():
    r = _render(_ALTITUDES)
    for marker in ("Bank altitude", "Journey altitude", "Signal altitude"):
        assert marker in r.artifact_text


def test_render_is_deterministic():
    a = _render(_ALTITUDES)
    b = _render(_ALTITUDES)
    assert a.artifact_text == b.artifact_text and a.artifact_hash == b.artifact_hash
