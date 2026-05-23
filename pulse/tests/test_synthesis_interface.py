"""Tests for the SynthesisProvider interface.

Key invariants:
  - The ABC cannot be instantiated.
  - TemplateSynthesisProvider has synthesis_mode == DETERMINISTIC.
  - synthesise() raises NotImplementedError (skeleton at PULSE-89).
  - SynthesisMode enum has both DETERMINISTIC and LLM_AUGMENTED values.
  - NO LLMSynthesisProvider class exists in pulse.synthesis (architectural invariant).
"""

from __future__ import annotations

import pytest

import pulse.synthesis
from pulse.synthesis import (
    AnalyticOutputs,
    SynthesisMode,
    SynthesisProvider,
    TemplateLibrary,
    TemplateSynthesisProvider,
)


def test_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        SynthesisProvider()  # type: ignore[abstract]


def test_template_provider_mode_is_deterministic() -> None:
    assert TemplateSynthesisProvider.synthesis_mode == SynthesisMode.DETERMINISTIC


def test_template_provider_can_be_instantiated() -> None:
    provider = TemplateSynthesisProvider()
    assert provider.synthesis_mode == SynthesisMode.DETERMINISTIC


def _render(payload: dict, templates: dict, version: str = "1.2.3"):
    return TemplateSynthesisProvider().synthesise(
        question_class="cause",
        analytic_outputs=AnalyticOutputs(question_class="cause", payload=payload),
        templates=TemplateLibrary(name="t", version=version, templates=templates),
    )


def test_template_provider_synthesise_renders() -> None:
    """PULSE-94: the skeleton is replaced by a real deterministic Jinja2 render."""
    import hashlib

    result = _render({"name": "Holter", "n": 3}, {"journey": "Hello {{ name }} - {{ n }} signals"})
    assert result.artifact_text == "Hello Holter - 3 signals"
    assert result.synthesis_mode == SynthesisMode.DETERMINISTIC
    assert result.provider_class == "TemplateSynthesisProvider"
    assert result.template_version == "1.2.3"
    assert result.artifact_hash == hashlib.sha256(result.artifact_text.encode("utf-8")).hexdigest()


def test_synthesise_strict_undefined_fails_loud() -> None:
    """A missing payload key must raise, never render a silent blank."""
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):
        _render({"name": "Holter"}, {"journey": "{{ name }} {{ missing_key }}"})


def test_synthesise_is_deterministic() -> None:
    a = _render({"n": 7}, {"j": "n={{ n }}"})
    b = _render({"n": 7}, {"j": "n={{ n }}"})
    assert a.artifact_text == b.artifact_text and a.artifact_hash == b.artifact_hash


def test_synthesise_renders_all_templates_sorted_and_concatenated() -> None:
    result = _render({}, {"signal": "S", "bank": "B", "journey": "J"})
    assert result.artifact_text == "B\n\nJ\n\nS"  # sorted by template name


def test_synthesise_empty_library_raises() -> None:
    with pytest.raises(ValueError, match="no templates"):
        _render({"name": "x"}, {})


def test_synthesis_mode_enum_has_both_values() -> None:
    assert SynthesisMode.DETERMINISTIC.value == "deterministic"
    assert SynthesisMode.LLM_AUGMENTED.value == "llm_augmented"


def test_no_llm_synthesis_provider_class_exists() -> None:
    """The v1 architectural invariant: LLMSynthesisProvider MUST NOT exist."""
    forbidden_names = {"LLMSynthesisProvider", "llm", "LLM"}
    exported = set(pulse.synthesis.__all__)
    assert forbidden_names.isdisjoint(exported), (
        f"v1 must not export any LLM-related synthesis class. "
        f"Found: {forbidden_names & exported}"
    )


def test_no_llm_synthesis_module_file() -> None:
    """Belt-and-braces: no pulse/synthesis/llm.py file on disk."""
    from pathlib import Path

    synth_dir = Path(pulse.synthesis.__file__).parent
    forbidden = list(synth_dir.glob("llm*.py"))
    assert not forbidden, (
        f"v1 must not contain any pulse/synthesis/llm*.py file. "
        f"Found: {[p.name for p in forbidden]}"
    )


def test_subclass_without_synthesis_mode_raises() -> None:
    with pytest.raises(TypeError, match="synthesis_mode"):

        class BadProvider(SynthesisProvider):  # type: ignore[misc]
            # Deliberately omits synthesis_mode.
            def synthesise(self, question_class, analytic_outputs, templates):
                raise NotImplementedError


def test_subclass_with_synthesis_mode_works() -> None:
    """Confirms the gate isn't blocking legitimate subclasses (just LLM-shaped ones)."""

    class StubProvider(SynthesisProvider):
        synthesis_mode = SynthesisMode.DETERMINISTIC

        def synthesise(self, question_class, analytic_outputs, templates):
            from pulse.synthesis import SynthesisResult

            return SynthesisResult(
                artifact_text="stub",
                artifact_hash="0" * 64,
                template_version="0.0.0",
                synthesis_mode=SynthesisMode.DETERMINISTIC,
                provider_class="StubProvider",
            )

    StubProvider()  # instantiable
