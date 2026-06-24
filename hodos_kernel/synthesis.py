"""
hodos_kernel.synthesis — selectable runtime behind one interface (HODOS-4 spike).

The neuro-symbolic dual-mode the research flagged, made a first-class toggle:

  • deterministic — template synthesis over the decision's own facts. No model,
    hallucination-free, every word traces to a field. The regulated default.
  • llm          — LLM-augmented narrative. (Offline STUB here: composes a
    richer analyst sentence deterministically from the same facts and tags it
    `[llm]`. Production wires this to mil.config.model_client — out of spike scope.)

CRITICAL GOVERNANCE PROPERTY: a provider only writes `decision.narrative`. It
NEVER changes the verdict, score, or recommended action — those are computed in
decision.decide(). So the runtime toggle changes the *explanation*, not the
*decision*. (Tested.)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from hodos_kernel.decision import Decision


class SynthesisProvider(ABC):
    mode: str = "base"

    @abstractmethod
    def narrate(self, decision: Decision, synthesis_cfg: dict[str, Any]) -> str:
        ...

    def apply(self, decisions: list[Decision], synthesis_cfg: dict[str, Any]) -> list[Decision]:
        for d in decisions:
            d.narrative = self.narrate(d, synthesis_cfg)
        return decisions


class TemplateSynthesisProvider(SynthesisProvider):
    """Deterministic. Fills a manifest template with decision facts only."""
    mode = "deterministic"

    def narrate(self, d: Decision, cfg: dict[str, Any]) -> str:
        tmpl = cfg.get("template",
                       "{verdict}: {subject} (score {score:g}). {recommended_action}")
        return tmpl.format(
            verdict=d.verdict, subject=d.subject, score=d.score,
            recommended_action=d.recommended_action,
            signal_count=d.inputs["signal_count"], entity_count=d.inputs["entity_count"],
            top_signal=d.inputs["top_signal"],
        )


class LLMSynthesisProvider(SynthesisProvider):
    """LLM-augmented (OFFLINE STUB for the spike — deterministic, no API call).

    Production: replace narrate() body with a model_client call whose prompt is
    grounded in decision.core() and forbidden from inventing facts (the verbatim
    rule). Tagged [llm] so it's never mistaken for the deterministic path."""
    mode = "llm"

    def narrate(self, d: Decision, cfg: dict[str, Any]) -> str:
        verb = {"ACT": "needs action now", "WATCH": "is worth watching",
                "IGNORE": "looks healthy"}[d.verdict]
        quote = d.inputs.get("sample_verbatim")
        quote_clause = f' One customer said: "{quote}".' if quote else ""
        return (
            f"[llm] {d.subject} {verb} — {d.inputs['signal_count']} signals across "
            f"{d.inputs['entity_count']} affected, dominated by '{d.inputs['top_signal']}'."
            f"{quote_clause} Recommended: {d.recommended_action}"
        )


def get_provider(runtime: str) -> SynthesisProvider:
    runtime = (runtime or "deterministic").lower()
    if runtime in ("deterministic", "template", "non_llm", "non-llm"):
        return TemplateSynthesisProvider()
    if runtime in ("llm", "llm_augmented", "llm-augmented"):
        return LLMSynthesisProvider()
    raise ValueError(f"unknown runtime '{runtime}' (use 'deterministic' or 'llm')")
