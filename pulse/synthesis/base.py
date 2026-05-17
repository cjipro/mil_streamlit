"""SynthesisProvider interface + v1 deterministic skeleton.

Per ticket: the interface IS defined; the LLM implementation is NOT. Enabling
LLM-augmented synthesis in v2 requires a new shipped artifact, a new
decision-pack declaring `synthesis_mode: llm_augmented`, FrictionBench LLM
track scoring, AND explicit governance review. It is not a config flip.

Filed under PULSE-89.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar


class SynthesisMode(str, Enum):
    """Closed enum at v1. `LLM_AUGMENTED` exists in the type but no provider implements it."""

    DETERMINISTIC = "deterministic"
    LLM_AUGMENTED = "llm_augmented"


@dataclass(frozen=True)
class AnalyticOutputs:
    """Inputs handed to the synthesis provider — outputs from the analytics layer.

    Concrete shape varies by question class; treated as opaque mapping by the
    synthesis layer at v1. Tightened in the pipeline-impl ticket.
    """

    question_class: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TemplateLibrary:
    """Reference to the template set the provider may use. Loaded by the engine.

    Concrete file-layout + Jinja2 environment configuration handled in the
    template-impl ticket. v1 contract: it's a dict-of-templates-by-name.
    """

    name: str
    version: str
    templates: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SynthesisResult:
    """Output of synthesise(): the rendered artifact plus provenance stamps."""

    artifact_text: str
    artifact_hash: str  # SHA-256 of artifact_text; used as lineage row's artifact_hash
    template_version: str
    synthesis_mode: SynthesisMode
    provider_class: str


class SynthesisProvider(ABC):
    """Abstract base. Engine instantiates exactly one provider per decision-pack.

    The pack's metadata.yaml declares `synthesis_mode`; the engine matches
    that against `synthesis_mode` ClassVar on each registered provider class
    and instantiates the unique match. v1 has only one registered class
    (`TemplateSynthesisProvider`); any pack declaring `llm_augmented` will
    fail to resolve and the engine refuses to run that pack.
    """

    synthesis_mode: ClassVar[SynthesisMode]  # subclass MUST set

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "synthesis_mode"):
            raise TypeError(
                f"{cls.__name__}: SynthesisProvider subclass must set `synthesis_mode` ClassVar"
            )

    @abstractmethod
    def synthesise(
        self,
        question_class: str,
        analytic_outputs: AnalyticOutputs,
        templates: TemplateLibrary,
    ) -> SynthesisResult:
        """Render the analytic outputs into a reader-facing artifact."""


class TemplateSynthesisProvider(SynthesisProvider):
    """v1 deterministic implementation. Hydrates Jinja2 templates. Zero LLM inference.

    Skeleton at PULSE-89; full Jinja2 implementation is a downstream ticket.
    Body raises NotImplementedError with a clear pointer so the engine fails
    loudly rather than silently shipping unrendered placeholders.
    """

    synthesis_mode: ClassVar[SynthesisMode] = SynthesisMode.DETERMINISTIC

    def synthesise(
        self,
        question_class: str,
        analytic_outputs: AnalyticOutputs,
        templates: TemplateLibrary,
    ) -> SynthesisResult:
        raise NotImplementedError(
            "TemplateSynthesisProvider.synthesise is a PULSE-89 skeleton. "
            "Full Jinja2 rendering lands in a separate ticket once the analytics "
            "layer + template library file format are decided."
        )
