# hodos_kernel — SPIKE (HODOS-4)

A throwaway-able prototype of the **Hodos** thesis: **one engine that manufactures
decision products from a declarative manifest.** A product (Pulse, Sonar,
telco-churn, …) is a `product.yaml`, not a bespoke codebase. *Decisions, not
dashboards* — the decision is the core object.

Grounded in the 2026-06-24 deep-research synthesis (decision-intelligence product
factory: Palantir Ontology, DMN, MCP adapters, neuro-symbolic dual-runtime, EU AI
Act Art. 12).

## Run it

```
py -m hodos_kernel.run_demo            # 2 products × 2 runtimes → output/*.html
py -m pytest hodos_kernel/tests -q     # tests
```

## The pipeline (product-agnostic)

```
sources(adapters) → canonicalize → detectors → decide → synthesize(runtime)
                  → DecisionLog (hash-chain) → surface (Holter-style HTML)
```

| Stage | Module | What the manifest controls |
|---|---|---|
| ingest-from-anywhere | `adapters.py` | which `SourceAdapter`(s) + config |
| one schema | `canonical.py` | field mapping → CanonicalRecord |
| detect (deterministic) | `detectors.py` | declarative threshold rules |
| **decide (first-class)** | `decision.py` | scoring weights, verdict thresholds, action template |
| selectable runtime | `synthesis.py` | `deterministic` (template) \| `llm` (stub) |
| surface | `surface.py` | title, altitudes |

## What it demonstrates (HODOS-4 acceptance)

1. **Product factory** — `kernel.run(manifest, runtime)`; the product is the manifest.
2. **Decision as a first-class object** — `Decision(inputs → verdict → recommended_action → outcome)` with an `outcome` write-back slot (the Palantir loop), hash-chained in a tamper-evident `DecisionLog` (lineage by design — the EU AI Act Art. 12 shape).
3. **Ingest from anywhere** — thin `SourceAdapter` boundary; two synthetic adapters with *different* row shapes prove the canonicaliser does real schema conversion. (Production: wrap an API/DB/MCP server behind the same `fetch()`.)
4. **Selectable runtime** — `deterministic` (hallucination-free template, the regulated default) vs `llm` (offline stub; production wires to `model_client`). **Governance property (tested): the runtime changes only the narrative — verdicts/scores are identical across modes.**
5. **Two products, one engine** — `pulse_friction.yaml` (journey friction) + `telco_churn.yaml` (a deliberately different vertical) from the same kernel; each runs in both runtimes.
6. **Holter-style surface** — config-driven HTML, laptop-first fixed cells.

## Boundaries / honesty

- **Isolated:** imports only `hodos_kernel.*` + stdlib + `yaml`. Does **not** touch live `mil/` or `pulse/` (Zero Entanglement intact).
- **Spike, not extraction:** this is the *deferred* Hodos engine extraction (DHH lock) explored as a throwaway to inform HODOS-2 — not production code.
- **Synthetic only:** one synthetic adapter per product; no real connectors, no real LLM calls, no storage/compute. Hodos is the decision layer *above* data, not a lakehouse.
- `output/*.html` is generated (gitignored) — `run_demo` rebuilds it.

## What a production version would add (the real HODOS-2 build list)

- MCP-expressible adapters (speak the standard boundary).
- Real `SynthesisProvider(llm)` wired to `model_client` with verbatim-grounding.
- A richer decision/DMN schema + real outcome write-back loop.
- Fairness convergence + the 21 governance principles threaded in (already exist in `pulse/`).
