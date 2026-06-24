# Hodos — Architecture

**Status: DRAFT (HODOS-2).** Grounded in the running reference implementation
(`hodos_kernel/`, HODOS-4 spike) and the 2026-06-24 decision-intelligence
research synthesis. Sections marked ⚑ depend on unresolved HODOS-1 strategic
decisions (license / trademark / CHRONICLE split / partner model /
hosted-vs-fork) and are provisional until those land.

Companion docs: [`HODOS_NAMING.md`](HODOS_NAMING.md) (CJI/Hodos boundary),
[`GOVERNANCE.md`](GOVERNANCE.md), [`CONTRIBUTING.md`](CONTRIBUTING.md),
[`LICENSE`](LICENSE) (Apache 2.0).

---

## 1. What Hodos is

**Hodos is an engine for manufacturing decision products.** A *decision product*
ingests data, detects what matters, and emits **decisions** — not dashboards.
CJI Sonar, CJI Pulse, and a telco-churn sentinel are all the same engine with
different configuration.

- **CJI** is a specific closed application of Hodos (UK retail banking; the
  CHRONICLE failure ledger; brand marks). Hosted, proprietary.
- **Hodos** is the general open-source engine (Apache 2.0) that powers CJI and
  is runnable by anyone for any vertical.

Public narrative: *"CJI is powered by Hodos."* The engine is being distilled
*out of* CJI as patterns stabilise (not pre-abstracted — see §13).

**Anti-positioning (load-bearing):** Hodos is **not** a data platform
(Databricks/Snowflake) and not a BI/dashboard tool. It is the **governed
decision-intelligence layer that sits *above* data** — it consumes from a
lakehouse/warehouse/API and produces auditable decisions. Storage and compute
are explicitly out of scope.

## 2. Design principles

1. **Decisions, not dashboards.** The unit of output is a `Decision` object
   (§6), not a chart a human must interpret.
2. **Selectable runtime.** Every product runs on a *deterministic* path
   (classical ML + statistics + templates — explainable, hallucination-free) or
   an *LLM-augmented* path, chosen per product/run. The runtime changes the
   *explanation*, never the *decision* (§7).
3. **Governed by design.** Lineage, audit, and fairness are threaded through
   the pipeline, not bolted on — the shape EU AI Act Art. 12 requires (§8).
4. **Fork-first.** Every boundary is an interface a fork can implement. The
   test for any line of code: *"would a fork have to do this, or is it
   CJI-specific?"* (§11).
5. **Products are config.** A new product is a declarative manifest, not a
   bespoke codebase (§3).

## 3. The kernel: one engine, many products

A product is a declarative manifest (`product.yaml`). The engine is a fixed,
product-agnostic pipeline that the manifest configures:

```
            product.yaml  (the product IS this file)
                  │
   sources ──► canonicalize ──► detect ──► decide ──► synthesize ──► surface
  (adapters)     (one schema)  (rules/ML) (Decision) (runtime sel.)  (Holter)
                  │                                    │
                  └──────────── lineage / audit / fairness ───────────┘
                                 (hash-chained, every hop)
```

The reference implementation is `hodos_kernel/` (HODOS-4): `kernel.run(manifest,
runtime)` produces a Pulse-like friction product *and* a telco-churn product
from the same code — only the manifest differs. The manifest's five blocks map
1:1 to pipeline stages:

| Manifest block | Stage | Module (spike) |
|---|---|---|
| `sources` | ingest | `adapters.py` |
| `canonical` | normalize to one schema | `canonical.py` |
| `detectors` | flag signals (declarative rules / ML) | `detectors.py` |
| `decision` | score, verdict, recommended action | `decision.py` |
| `synthesis` | narrate (deterministic \| llm) | `synthesis.py` |
| `surface` | render | `surface.py` |

## 4. Pipeline stages (NOT an "agent swarm")

> **Reframe (MIL-185, locked 2026-06-24):** earlier drafts called this "a swarm
> of 10 agents." That framing is retired. Hodos is a **governed deterministic
> pipeline of stages** — there is no agent loop, tool-use planning, inter-agent
> messaging, or autonomy budget at runtime. The word "agents" is reserved for a
> future option (§13) and may only be claimed once a genuine agent loop ships.
> "Governed deterministic pipeline" is the stronger, due-diligence-survivable
> story for regulated buyers anyway.

CJI MIL realises these stages as ten functions; any Hodos application implements
the same shape:

| Stage | Role | Interface |
|---|---|---|
| Harvester | pull from sources | `SourceAdapter` (§5) |
| Enricher | classify/annotate raw records | enrichment fn (runtime-selectable) |
| Canonicalizer | map to canonical schema | manifest `canonical` mapping |
| Detector | emit signals from canonical records | declarative detector specs |
| Decider | signals → `Decision` objects | scoring + thresholds (§6) |
| Synthesizer | decision → narrative | `SynthesisProvider` (§7) |
| Briefer/Surface | render to a surface | `SurfaceRenderer` |
| Verifier | check claims are grounded | verifier (fail-flagged) |
| Auditor | hash-chain the lineage | `DecisionLog` (§6) |
| Drifter | monitor output/fairness drift | monitor hooks |

Stages are pure where possible and composed deterministically; the orchestrator
is a workflow (durable, resumable), not an autonomous planner.

## 5. Adapter contracts (what a fork implements)

The boundaries a fork must satisfy. Each is a thin, versioned interface — the
"USB-C" pattern (research: MCP as the emerging standard). MIL-35 `PublishAdapter`
is the gold-standard model; the spike's `SourceAdapter` is the ingest analogue.

| Contract | Purpose | Reference |
|---|---|---|
| `SourceAdapter.fetch()` | ingest from any source (API/DB/file/stream) | `hodos_kernel/adapters.py` |
| `SynthesisProvider.narrate()` | deterministic \| LLM narration | `hodos_kernel/synthesis.py` |
| `PublishAdapter.publish()` | emit to any destination | `mil/publish/adapters.py` |
| `VaultBackend.write()` | persist canonical/enriched data | `mil/vault/backends.py` |
| `DetectorSpec` | declarative signal rule | manifest `detectors` |
| `SurfaceRenderer.render()` | product surface (UI/email/API) | `hodos_kernel/surface.py` |
| `ChroniclePack` | vertical failure-pattern library | §10 |

**Boundary discipline:** adapters carry a versioned envelope
(`contract_version`, `adapter_version`) and a recursive PII deny-list enforced at
the edge. ⚑ Whether these are exposed as **MCP servers** (so external agents/data
reach Hodos through the standard) is recommended (research §A) but gated on the
hosted-vs-fork decision (HODOS-1).

## 6. The Decision as a first-class object

Following the Palantir-ontology / DMN pattern (research), a decision is an
explicit object, not an emergent property of a chart:

```
Decision(
  subject,             # what the decision is about (journey / segment / …)
  verdict,             # ACT | WATCH | IGNORE   (deterministic from evidence)
  score,               # the ranked magnitude
  inputs,              # the evidence the verdict was computed from
  recommended_action,  # templated next-best-action
  outcome,             # write-back slot: pending | accepted | … (Palantir loop)
)
```

- **Decisions are runtime-independent.** `verdict`/`score`/`action` are computed
  deterministically from evidence; the synthesis runtime (§7) only writes the
  narrative. (Tested in the spike: deterministic and LLM runs produce identical
  `Decision.core()`.)
- **Write-back loop.** `outcome` closes the loop — a made decision and its result
  are recorded, mirroring Palantir's ontology write-back.
- **Lineage by design.** Decisions are appended to a `DecisionLog` — a SHA-256
  hash-chained, tamper-evident ledger (`row_hash = SHA256(decision_core ‖
  prev_hash)`, GENESIS anchor). This is the EU AI Act Art. 12 shape: logging in
  the core, reconstructable input→decision→action, not a bolt-on (§8).

This is a DMN-lite model. A fuller version would adopt OMG DMN's Decision
Requirements Diagram for multi-step decision composition (research §B; future).

## 7. Selectable runtime (deterministic ↔ LLM)

The neuro-symbolic dual-mode the research identifies as the only
regulated-suitable pattern, surfaced as a first-class toggle behind one
interface (`SynthesisProvider`):

| Mode | What it is | When |
|---|---|---|
| `deterministic` | templates over classical-ML/stats output; every word traces to a field; zero hallucination surface | regulated / high-stakes / procurement gate (the default) |
| `llm` | LLM-augmented narration, grounded in the decision's facts + verbatim rule | low-stakes, exploratory, public-data, richer prose |

**Invariant (governance-critical):** a provider writes only `Decision.narrative`.
It never alters the verdict, score, or action. So switching runtime cannot change
what the system *decides* — only how it *explains*. Enabling LLM mode for a
high-stakes product additionally requires a governance review and a synthesis-mode
declaration (the `SynthesisProvider` lock — no dormant LLM stub ships by default).

## 8. Governance & compliance

What makes Hodos procurement-passable in a regulated bank — and the research's
finding that the EU AI Act (fully applies **2 Aug 2026**) makes this *mandatory*,
turning Hodos's existing posture into a moat:

- **Lineage by design** — hash-chained `DecisionLog`; Art. 12 (logging in core),
  reconstructable per-decision provenance, retention-ready.
- **Human oversight by design** — decisions are proposals with evidence; a human
  can inspect inputs, override, or halt (Art. 14).
- **Fairness convergence** — high-stakes investigations must run ≥1
  statistical-power method AND ≥1 fairness-aware method (demographic parity /
  equalised odds / calibration-by-cohort), guarding against shared-cohort bias.
- **The 21 governance principles** (P1–P21) — PII masking, decision glass-box,
  agent identity/lifecycle, kill-switch for autonomous tiers, SBOM/exit. ⚑ Several
  are `PENDING_BUILD` as enforced controls (declared, not yet runtime-enforced) —
  closing that gap is a HODOS-2-follow-on.
- **FrictionBench** — the public benchmark substrate; synthetic-to-real transfer
  via TOST equivalence (`pulse/frictionbench/transfer/`) so headline scores
  aren't cited without the generalisation gap.
- **No-fabrication (Article Zero)** — verbatim quotes only; verifier fail-flagged
  (an unverified answer is never served as verified).

## 9. Reference applications

Three points prove generality (research: a "third caller" is what proves a
framework isn't just its first app):

| App | Vertical | Sources | Decision | Runtime | Status |
|---|---|---|---|---|---|
| **CJI Sonar** | public-signal banking intelligence | app reviews, DownDetector, Reddit, … | which competitor pattern to brief on | LLM (public data) | live (MIL) |
| **CJI Pulse** | internal journey friction | journey telemetry | which journey friction to act on | deterministic (regulated) | engine built |
| **Churn Sentinel** | telco retention (worked example) | account snapshots | which segment to run retention on | either | spike (`hodos_kernel/products/telco_churn.yaml`) |

The telco example is deliberately *unlike* banking — different source shape,
taxonomy, detectors, thresholds, action language — and falls out of the same
kernel as pure config. That is the platform thesis, demonstrated.

## 10. Vertical CHRONICLE pack model

The CHRONICLE (CJI's failure ledger) generalises to **per-vertical pattern
packs**: a `ChroniclePack` is a versioned, licensed set of failure patterns the
Decider/RAG layer anchors against (banking: CHR-001…; insurance: CHR-INS-001;
telco: CHR-TEL-001). ⚑ Whether packs are free, tiered, or partner-authored is a
HODOS-1 decision (CHRONICLE split + partner model). The *registry* of packs —
not any single pack — is the durable moat (research: vendor-supplied content
distribution failed for Sisu/Outlier; the registry is the asset).

## 11. Engine vs application boundary

The rule for every change: **"would a fork have to do this?"**

- **Hodos-bound** (engine, Apache 2.0): pipeline, adapter contracts, canonical
  schema, detector/decision/synthesis interfaces, FrictionBench, lineage,
  governance scaffolding, sample/synthetic data.
- **CJI-bound** (proprietary): real CHRONICLE entries, brand marks, partner data,
  hosted-instance config (Cloudflare/WorkOS/D1), real banking incident analyses.
- **Never crosses:** real proprietary/PII data → CJI only. Enforced at the file
  level by `mil/publish/adapters.py` `SENSITIVE_PATH_PATTERNS` and
  `scripts/check_public_repo_hygiene.py`.

## 12. Mapping to 2026 standards (what we steal)

From the research synthesis (2026-06-24):

- **Palantir Ontology** → the decision-write-back loop (§6). *Steal the loop;
  avoid the heavyweight/closed/consultant-gated delivery.*
- **DMN (OMG)** → the decision-as-object model (§6); adopt DRD for multi-step
  decisions later.
- **MCP / A2A** → express adapters as MCP servers; A2A signed Agent Cards if/when
  cross-agent coordination is real (§5). *Speak the lingua franca; don't reinvent
  it under house names.*
- **Neuro-symbolic** → the selectable runtime (§7); deterministic for
  mission-critical, LLM for perception/prose.
- **EU AI Act Art. 12/14, FCA** → lineage + oversight by design (§8) — already
  the architecture, now also the regulatory floor.
- **The gap** → no incumbent offers a *governed, sovereign, fork-able decision
  product factory*. Palantir is heavy/closed; Aera unprofitable; Sisu absorbed
  into Snowflake; augmented-analytics tools are dashboard-shaped and
  hallucination-prone. That gap is Hodos's wedge.

## 13. Build sequence & extraction discipline

**Do not big-bang build the engine.** Per the architecture-panel lock (DHH):
extract patterns that have *stabilised*, don't pre-abstract.

1. **Now:** the spike + this doc settle the *shape*. Resolve HODOS-1 (the five
   commercial decisions) — they determine §5/§10/⚑ sections.
2. **Accrete:** as CJI/MIL/Pulse patterns harden, route them into the kernel
   under clean interfaces (Vogels: external-grade API at the boundary from day
   one). Each stabilised pattern is a candidate extraction.
3. **Pull, don't push:** let a real second product (a new vertical, a licensee)
   pull the extraction forward — that's the "third caller" that proves generality.
4. **Agents only when earned:** a genuine agent loop (the Researcher:
   plan→retrieve→draft→self-critique with a step budget + audit) is a *future*
   option (§4), built only if the autonomy is worth the governance cost.

The failure modes this sequence avoids (all locked warnings): framework-eats-parent
(Hykes), framework-born-too-early (DHH), framework-without-a-second-caller
(Hashimoto), framework-without-external-grade-interfaces (Vogels).

## 14. Open questions (→ HODOS-1)

- License/trademark posture for the engine vs the CHRONICLE packs ⚑
- CHRONICLE split: free / tiered / partner-authored ⚑
- Partner model: contributor / pack-author / reseller ⚑
- Hosted reference instance vs forkable-only ⚑ (determines MCP-server exposure, §5)
- Enforced (not just declared) status for the `PENDING_BUILD` governance
  principles (P11/P15/P17) — agent identity, inter-stage auth, kill-switch.
