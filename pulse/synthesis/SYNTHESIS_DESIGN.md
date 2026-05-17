# Pulse synthesis — design

**Filed under PULSE-89.**

## v1 stance

The synthesis layer is **deterministic**. Every output Pulse produces is a
function of:

- the inputs named in its lineage row
- the template version
- the decision-pack version
- the pipeline version
- the config hash

No model. No sampling. Same inputs → same output, byte-identical, forever.

This is what makes audit defensibility cheap: an FCA reviewer can re-derive
any Pulse output from the inputs the audit bundle names. There is no
"the model said X today and Y tomorrow" failure mode because there is no
model.

## Interface

See `base.py`. Three types:

- `SynthesisProvider` (ABC) — declares `synthesise(question_class, analytic_outputs, templates) -> SynthesisResult`
- `TemplateSynthesisProvider` — the v1 implementation, `synthesis_mode = DETERMINISTIC`
- `SynthesisMode` enum — `DETERMINISTIC | LLM_AUGMENTED`

The `LLM_AUGMENTED` value EXISTS in the enum but no provider class declares
it at v1. Any decision-pack declaring `synthesis_mode: llm_augmented` will
fail to resolve at engine startup — there is no provider class to instantiate.

## What's NOT shipped in v1

- No `pulse/synthesis/llm.py` file
- No `LLMSynthesisProvider` class
- No abstract scaffold for LLM providers
- No "LLM provider TODO" comment in the codebase
- No flag, no config key, no environment variable that toggles LLM mode

This is deliberate. Krishna's panel point on dormant-flag audit liability
applies directly: a flag that "would" enable LLM if set is a liability
regulators ask about. The honest answer to *"does Pulse use LLMs?"* is
*"no, and enabling LLM use would require shipping a new artifact and
governance sign-off."*

## v2 enablement path

Enabling LLM-augmented synthesis is a 4-step ship:

1. **Implementation.** Write `pulse/synthesis/llm.py` with class
   `LLMSynthesisProvider(SynthesisProvider)`, `synthesis_mode = LLM_AUGMENTED`,
   `synthesise()` calling out to a vendor model.
2. **Decision-pack.** Ship a decision pack with `synthesis_mode: llm_augmented`
   in its `metadata.yaml`. Existing packs are unaffected (they remain
   `synthesis_mode: deterministic`).
3. **FrictionBench LLM-track submission.** Per PULSE-88 the LLM track has
   its own gates: separate scoring board, separate reproducibility
   requirements, separate cost-per-investigation reporting.
4. **Governance review.** Security + audit + regulatory sign-off explicitly
   recorded against the new pack version. Reviewers should be able to point
   at the commit that introduced LLM use and the commit that approved it.

This satisfies Chip's "extensibility without dormant-flag risk" concern:
the architecture is open to LLMs, but the path is a deliberate ship, not
a configuration toggle.

## Decision-pack resolution

```
pack metadata.yaml
       │
       │  synthesis_mode: deterministic
       ▼
engine looks for SynthesisProvider subclass
where SynthesisProvider.synthesis_mode == DETERMINISTIC
       │
       │  exactly one match: TemplateSynthesisProvider
       ▼
engine instantiates TemplateSynthesisProvider
       │
       ▼
provider.synthesise(...) produces SynthesisResult
       │
       ▼
lineage row written: operation=synthesise, artifact_hash=result.artifact_hash
```

`pulse.decision_packs.validate_metadata()` rejects v1 packs with
`synthesis_mode != deterministic` — see `pulse/decision_packs/`.
