# CJI — Customer Journey Intelligence

> **Decisions, not dashboards.**
> *Anecdote → Aggregate → Awareness → Action.*

CJI is a sovereign intelligence engine that turns public customer signal — app reviews, outage reports, news, social — into ranked decision artefacts. It is built around an immutable failure ledger (CHRONICLE), a Confidence-Adjusted Calibration formula (CAC), and a strict honesty constraint (Article Zero: prefer expressed ignorance to unverified certainty).

The reference instance runs at [cjipro.com](https://cjipro.com), monitoring six UK retail banking apps. The engine itself is sector-agnostic — taxonomy, CHRONICLE entries, and competitor lists are configuration, not code.

---

## The four products

| Product | Job | Surface |
|---|---|---|
| **CJI Reckoner** | Industry intelligence — AI-surfaced cohort patterns | `app.cjipro.com/reckoner` |
| **CJI Sonar** | Daily firm briefing — client-specific PDB | `app.cjipro.com/sonar/{client}/{date}/` |
| **CJI Pulse** | Live insight — almost-real-time, observation not intervention | `app.cjipro.com/pulse` |
| **CJI Lever** | Tailored decision framework — Autonomous / Guided / Customer-led | `app.cjipro.com/lever` |

Underneath: **CJI Chronicle** — the public failure ledger that anchors every inference. *Sonar listens. Reckoner reckons. Pulse senses. Lever moves.*

---

## What this repository contains

The full CJI engine — pipeline, inference, briefing renderers, edge auth, ops scripts. The hosted reference instance and a forkable copy of the engine share the same codebase; configuration controls which tenant, taxonomy, and CHRONICLE pack you operate against.

```
mil/                          # the engine
  config/                     # taxonomy, model routing, tenant, clients
  harvester/                  # public-signal collectors (App Store, Google Play, etc.)
  inference/                  # CAC scoring + CHRONICLE-anchored RAG
  publish/                    # briefing renderers (V1–V4) + Sonar URL schema
  notify/                     # daily PDB email distribution
  auth/                       # Cloudflare Workers — edge bouncer, magic-link, app shell
  chat/                       # Reckoner ask-mode synthesis pipeline
  CHRONICLE.md                # banking failure ledger (CHR-001..019)
ops/                          # runbooks, Cloudflare wrapper, smoke scripts
run_daily.py                  # one-command pipeline
```

---

## How to read this repo

| If you are… | Start here |
|---|---|
| Trying CJI on your own data | [`GETTING_STARTED.md`](GETTING_STARTED.md) |
| Understanding how the system thinks | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Operating a live instance | [`RUNBOOK.md`](RUNBOOK.md) |
| Contributing or studying the failure ledger | [`CHRONICLE_POLICY.md`](CHRONICLE_POLICY.md) |
| Working on the codebase as the maintainer | `CLAUDE.md` (internal-only — not part of the open documentation) |

---

## Constitutional rules

These do not change.

- **Article Zero** — every inference traces to a verified CHRONICLE entry. Unverified fields are marked `[REVIEW REQUIRED]` and never enter inference.
- **Zero Entanglement** — the engine never imports from internal systems; the only data crossing is `mil/outputs/mil_findings.json`.
- **Verbatim quotes only** — customer voices are never paraphrased in output.
- **Designed Ceiling** — when public data alone cannot confirm a claim, the system says so explicitly rather than fabricating certainty.
- **Append-only ledger** — CHRONICLE entries are never amended.

See [`mil/SOVEREIGN_BRIEF.md`](mil/SOVEREIGN_BRIEF.md) for the full constitutional charter.

---

## Status

The reference instance is live with 10,000+ enriched records across six UK retail banks, 19 CHRONICLE entries, and a 30-day continuous-run streak. Daily run output renders to four briefing surfaces (V1–V4) plus the per-firm Sonar PDB at `/sonar/{client}/{date}/`.

The open documentation set you are reading is the entry point for prospective forkers, partners, and contributors. License terms, trademark policy, and the CHRONICLE distribution model are governance decisions in flight — not yet declared here.

---

*Build the honest version, not the impressive one.*
