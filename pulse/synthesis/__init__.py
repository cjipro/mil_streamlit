"""Pulse synthesis layer — converts analytic outputs into reader-facing artifacts.

v1 ships exactly one provider: TemplateSynthesisProvider (deterministic Jinja2).
There is NO LLMSynthesisProvider in v1 — no stub, no scaffold, no placeholder
file. See SYNTHESIS_DESIGN.md for the v2 enablement path.

Filed under PULSE-89.
"""

from pulse.synthesis.base import (
    AnalyticOutputs,
    SynthesisMode,
    SynthesisProvider,
    SynthesisResult,
    TemplateLibrary,
    TemplateSynthesisProvider,
)

__all__ = [
    "AnalyticOutputs",
    "SynthesisMode",
    "SynthesisProvider",
    "SynthesisResult",
    "TemplateLibrary",
    "TemplateSynthesisProvider",
]
