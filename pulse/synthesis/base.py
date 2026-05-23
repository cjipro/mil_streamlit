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
    """v1 deterministic implementation (PULSE-94). Hydrates Jinja2 templates. Zero LLM inference.

    Renders every template in the supplied `TemplateLibrary` (sorted by name for
    determinism) with the analytic outputs' `payload` as the render context,
    concatenating the results into one artifact — so a caller passing the three
    altitude templates (bank/journey/signal) gets the three-altitude single
    surface, and a caller passing one gets that one. No altitude param is needed
    on the signature: the library's contents select what renders.

    Deterministic by construction: `StrictUndefined` (a missing payload key fails
    loud, never renders a blank), `autoescape=False` (markdown output), no time /
    random globals. Same (payload + templates) → byte-identical artifact + hash.
    """

    synthesis_mode: ClassVar[SynthesisMode] = SynthesisMode.DETERMINISTIC

    def synthesise(
        self,
        question_class: str,
        analytic_outputs: AnalyticOutputs,
        templates: TemplateLibrary,
    ) -> SynthesisResult:
        import hashlib

        from jinja2 import Environment, StrictUndefined  # approved: Jinja2==3.1.4 (PULSE-94)

        if not templates.templates:
            raise ValueError(
                "TemplateSynthesisProvider.synthesise: TemplateLibrary has no templates to render"
            )

        env = Environment(
            autoescape=False,           # markdown output, not HTML
            undefined=StrictUndefined,  # missing payload key → loud failure, never silent blank
            keep_trailing_newline=True,
        )
        context = dict(analytic_outputs.payload)
        sections = [
            env.from_string(templates.templates[name]).render(**context)
            for name in sorted(templates.templates)  # deterministic order
        ]
        artifact_text = "\n\n".join(sections)
        artifact_hash = hashlib.sha256(artifact_text.encode("utf-8")).hexdigest()

        return SynthesisResult(
            artifact_text=artifact_text,
            artifact_hash=artifact_hash,
            template_version=templates.version,
            synthesis_mode=SynthesisMode.DETERMINISTIC,
            provider_class=type(self).__name__,
        )
