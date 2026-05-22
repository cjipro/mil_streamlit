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


def test_template_provider_synthesise_is_skeleton() -> None:
    provider = TemplateSynthesisProvider()
    with pytest.raises(NotImplementedError, match="skeleton"):
        provider.synthesise(
            question_class="cause",
            analytic_outputs=AnalyticOutputs(question_class="cause"),
            templates=TemplateLibrary(name="test", version="0.1.0"),
        )


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
