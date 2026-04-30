# Architecture

CJI is a single Python pipeline that runs once per day, plus a small set of Cloudflare Workers that fence the outputs behind partner authentication. This document describes how the engine thinks: the constitutional rules, the data flow, the model tiering, and the surfaces it renders.

For setup see [`GETTING_STARTED.md`](GETTING_STARTED.md). For day-to-day operation see [`RUNBOOK.md`](RUNBOOK.md).

---

## Constitutional rules

The engine is shaped by four hard constraints. Every component obeys them; the build validator fails on violation, not warns.

### Article Zero — calibrated honesty over fluent certainty

> *"This system shall prioritise the expression of its own ignorance over the delivery of any unverified certainty."*

Inferences trace to a verified `CHRONICLE` entry. Unverified fields are marked `[REVIEW REQUIRED]` and may not enter inference. When public data alone cannot confirm a claim, the system declares the **Designed Ceiling** rather than guessing.

### Zero Entanglement — sovereign engine boundary

The engine reads no internal-system module and writes no internal-system file. The only data crossing is `mil/outputs/mil_findings.json`, which downstream consumers may read.

```
No file under mil/ may import from internal modules.
No file outside mil/ may import from mil/ directly.
Permitted crossing: read mil/outputs/mil_findings.json only.
Violation: hard build-validator failure.
```

Enforced by `scripts/validate_mil_import_rule.py`.

### Verbatim quotes only

Customer voices in output are byte-exact lifts from source records. No paraphrasing, no clean-up, no synthesis. The locked Sonar PDB principles (`mil/notify/briefing_email.py`) and the Reckoner ask-mode verifier (`mil/chat/verifier.py`) both enforce this against generated prose.

### Append-only CHRONICLE

Existing entries are never amended. New entries append only. See [`CHRONICLE_POLICY.md`](CHRONICLE_POLICY.md).

---

## Pipeline shape

`run_daily.py` is the single entry point. The pipeline is 11 numbered steps:

```
1     Fetch          App Store + Google Play, paginated, dedup against existing
2     Enrich         Sonnet (default) — schema v3: issue_type, journey, severity, sentiment
3     Inference      mil_agent.py — CAC scoring + CHRONICLE-anchored embedding RAG
4a    Research       P0/P1 weak-anchor findings → research_queue.jsonl
4b    Vault          Push enriched records to HDFS (skipped if NameNode unreachable)
4c    Clark          Escalation tiering (CLARK-0..3) with Opus governance synthesis
4d    Benchmark      90-day rolling competitive benchmark + churn risk score
4e    Analytics DB   Rebuild mil_analytics.db (9 tables, DuckDB)
4f    Drift          Silent-Wall detector + future drift detectors
5     Publish V1     Legacy briefing — Box 1 source of truth for V2/V3/V4
5b    Publish V2     V1 + Vane chart, Inference Cards, Clark, Phase 2 demand
5c    Publish V3     V1 + Intelligence Brief, Churn, Commentary, Benchmarks
5d    Publish V4     Jinja2 V3 + FCA Provenance Chain (chronicle/signal/class/teacher version)
5e    Publish Sonar  Per-firm /sonar/{slug}/[date]/ — replaces /briefing-v4 long-term
6     Log            Append run row to daily_run_log.jsonl + Slack heartbeat
```

Steps 5b–5e read V1's `output/index.html` and patch sections on top. **V1 is load-bearing.** Retiring it requires migrating downstream renderers to render Box 1 directly from `briefing_data.py`.

---

## Data flow

### Input — six public sources

| Source | Trust weight | Method |
|---|---|---|
| App Store | 0.90 | iTunes RSS, paginated up to 250 reviews/source |
| Google Play | 0.90 | `google-play-scraper`, continuation token, up to 500/source |
| DownDetector | 0.95 | cloudscraper + Haiku narrative extraction |
| City A.M. + FT RSS | 0.90 | RSS, journalist-verified UK financial press |
| Reddit | 0.85 | Public JSON endpoints, no OAuth |
| YouTube | 0.75 | Comments + metadata via `yt-dlp` |

Three sources evaluated and excluded (Facebook poor ROI, Twitter/X cost, Glassdoor wrong domain). One deferred (Trustpilot legal risk).

### Storage — local + HDFS dual-write

| Local path | HDFS path | Purpose |
|---|---|---|
| `mil/data/historical/{source}/{competitor}/` | `/user/mil/historical/...` | Raw fetch output |
| `mil/data/historical/enriched/` | `/user/mil/enriched/` | Enriched records |
| `mil/outputs/mil_findings.json` | — | Inference results — the only exit point |
| `mil/vault/mil_vault.db` | — | DuckDB anchor log of HDFS writes |
| `mil_analytics.db` | — | Queryable read-side, rebuilt every run |

HDFS write is non-fatal — local is source of truth. The MIL HDFS instance (port 9871) is sovereign and never shares volumes or configuration with any other HDFS deployment.

### Output — `mil_findings.json` and four briefing surfaces

`mil_findings.json` is the canonical artefact: one entry per finding, with CAC score, Clark tier, CHRONICLE anchor, provenance chain, blind spots. Everything downstream — briefings, Sonar PDB email, Reckoner ask-mode — reads from it.

The four HTML briefing surfaces are layered:

```
V1 (publish.py)      —  Box 1/2/3, V1 is the canonical Box 1 source
V2 (publish_v2.py)   —  V1 + Vane chart, Inference Cards, Clark, Phase 2 demand
V3 (publish_v3.py)   —  V1 + Intelligence Brief (Box 3 replaced), Commentary
V4 (publish_v4.py)   —  Jinja2 V3 + FCA-grade Provenance Chain on every card
Sonar (5e)           —  Per-firm /sonar/{slug}/[date]/, parametric on subject
```

V4 is the production target for client-facing distribution. The Sonar URL schema (`/sonar/{client_slug}/{date}/`) is multi-tenant and replaces `/briefing-v4` over time.

---

## Inference — CAC + CHRONICLE-anchored RAG

The Confidence-Adjusted Calibration formula:

```
C_mil = (alpha * Vol_sig + beta * Sim_hist) / (delta * Delta_tel + 1)

  Vol_sig   — weighted signal volume from the harvest window
  Sim_hist  — cosine similarity to nearest CHRONICLE entry (embedding)
  Delta_tel — telemetry delta (always 0 in MIL — sovereign engine has no internal access)

  alpha=0.40, beta=0.40, delta=0.20
```

Implemented in `mil/inference/cac.py` (independently testable). RAG layer in `mil/inference/rag.py` uses `all-MiniLM-L6-v2` embeddings against the CHRONICLE corpus, cached in-process.

A finding without a CHRONICLE anchor (cosine ≥ 0.30) does not reach production — it goes to `research_queue.jsonl` for governance review and possible new-CHRONICLE-entry proposal.

The `Delta_tel = 0` term encodes the engine's air-gap: even if the formula could improve with internal telemetry, the engine refuses to depend on it. This is a feature, not a limitation.

---

## Model routing — four tiers

Configuration: `mil/config/model_routing.yaml`. Always call `get_model(task)` — never hardcode model names.

| Tier | Models | Used for |
|---|---|---|
| **1 — Governance** | Opus 4.7 | CHR proposals, teacher autopsies, CLARK-3 escalation synthesis |
| **2 — Daily intelligence** | Sonnet 4.6 | Enrichment, commentary, exec alert (V3/V4 Box 3), churn narrative |
| **3 — Classification at scale** | Haiku 4.5, Refuel-8B | Intent classification, blind-spots / failure-mode tags, ask-mode verifier |
| **4 — Labour** | Qwen3 14B (local Ollama) | YAML, scripting, narrative generation when not classification |

The enrichment route was flipped Haiku → qwen3:14b → Sonnet 4.6 over the course of operations (ARCH-002, ARCH-004, ARCH-006). Cost ceiling at the Sonnet 4.6 setting is approximately $0.80/day at 200 records/day. Provider switching is a one-line YAML edit; the enrichment code is provider-aware.

A QLoRA-trained 4B specialist was attempted (MIL-25) and shelved — the trained model lost to the qwen3:14b baseline on held-out severity classification (83.3% vs 93.3%).

---

## Authentication and edge surfaces

The hosted reference instance fences all client-facing surfaces behind partner authentication. Three Cloudflare Workers split the responsibilities:

| Worker | Domain | Job |
|---|---|---|
| **edge-bouncer** | `cjipro.com/briefing*` | JWT cookie verification, route allowlist, redirect-to-login |
| **magic-link** | `login.cjipro.com` | WorkOS Magic Auth, allowlist gate, admin dashboard, audit log |
| **app-cjipro** | `app.cjipro.com` | Reckoner shell, Sonar dispatch, `/api/ask` reverse-proxy |

Authoritative session is a `__Secure-` cookie on `.cjipro.com`. The audit log (D1 `mil-auth-audit`) is hash-chained, daily-salted, and partner-exportable. The full cookie spec lives in `mil/auth/COOKIE_SPEC.md`.

The auth stack is part of the *hosted reference* configuration. A fork that wants its own deployment can either reuse the Cloudflare Workers (with its own WorkOS tenant) or front the engine with its own auth — the engine itself reads `mil_findings.json` and renders HTML; it does not enforce auth.

---

## Hosted reference vs forkable engine

The same code runs both. Configuration determines which:

| Concern | Hosted reference | Fork |
|---|---|---|
| Tenant identity | `mil/config/clients.yaml`, `tenant.yaml` | Own values |
| Subjects (firms monitored) | Six UK retail banks | Own list |
| CHRONICLE pack | `mil/CHRONICLE.md` (banking) | Own ledger or licensed pack |
| Brand surfaces | `cjipro.com`, `app.cjipro.com`, `login.cjipro.com` | Own domains |
| Auth provider | WorkOS | Own provider or none |
| Partner email distribution | SMTP via Gmail Send-as | Own SMTP / ESP |

The boundary between *engine* (open) and *hosted-reference instance configuration* (proprietary to the reference) is being drawn explicitly in ongoing work. See `mil/publish/adapters.py` `SENSITIVE_PATH_PATTERNS` for the current enforced boundary on what may be published to the public Pages repo.

---

## Constitutional documents

| File | Purpose |
|---|---|
| `mil/SOVEREIGN_BRIEF.md` | Trust manifesto — Article Zero, Air-Gap, Blind Spot Register, Human Operating Model |
| `mil/MIL_SCHEMA.yaml` | Canonical schema for findings, sources, CAC formula, failure modes |
| `mil/CHRONICLE.md` | Banking failure ledger — CHR-001..019, append-only |
| `mil/config/apps_config.yaml` | Active sources, competitors, trust weights |
| `mil/config/model_routing.yaml` | Four-tier model routing — every task names its tier |
| `mil/config/domain_taxonomy.yaml` | Issue types, journeys, severity gate (single source of truth) |

These are the load-bearing files. Editing any of them changes the engine's behaviour without code changes.
