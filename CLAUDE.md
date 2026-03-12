# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

- **Project:** CJI Pulse / while-sleeping
- **Private project** — no employer references
- **Mission:** Daily customer journey intelligence platform
- **Day 90 vision:** "Customers experiencing difficulties on Step 3 of Loans journey, abandoning — likely 45+, likely vulnerable. In last 3 days 5 customers said App journey sucks."

## Environment Rules

- Windows machine — always use `py` not `python`
- Git Bash for git commands
- Claude Code for all development tasks
- Repo: `C:\Users\hussa\while-sleeping`

## Build Rules

- Manifest is source of truth — `system_manifest.yaml`
- Dual closure rule: validator passes AND human closes ticket in Jira UI manually
- Never close Jira tickets programmatically
- Always validate before committing
- Commit manifest status update after every ticket

## Current Sprint Status

Sprint 1 — 8 tickets BUILT, 1 IN_PROGRESS:
- KAN-10: GitLab repo (BUILT)
- KAN-17: system_manifest.yaml (BUILT, commit 377a4be)
- KAN-19: telemetry_spec.yaml (BUILT, commit 021a8a9)
- KAN-01G: graduated_trust_tiers.yaml (BUILT, commit d630986)
- KAN-01H: hypothesis_library.yaml (BUILT, commit dd89e32)
- KAN-13: audit_findings.yaml (BUILT, commit fe492e2)
- KAN-18: build_from_manifest.py (BUILT, commit bb47a21)
- KAN-12: Docker environment (BUILT)
- KAN-011: Living Data Dictionary (IN_PROGRESS — tracks 1A–1D complete, awaiting master dict population)

**In progress:** KAN-011 — Tracks 1A–1D complete. Awaiting Track 2 (human provides raw table records).
**Next after KAN-011:** KAN-16 — Create all Jira tickets

KAN-011 tracks complete (2026-03-12):
- Track 1A: system_manifest.yaml — KAN-011 updated, 4 components added, 21 principles registered (commit 8c5b904)
- Track 1B: CLAUDE.md — KAN-011 redefined, 21 principles embedded, warn-not-fail rule (commit f7d636c)
- Track 1C: manifests/governance_principles.yaml — 21 constitutional principles created (commit eace6c5)
- Track 1D: scripts/validate_principles.py + validate_KAN-011.py — PASS 6/6, 0 warnings (commit cf0d7fb)

Manifest hardening complete (2026-03-12):
- KAN-01G: permitted_storage_targets added, Tier 5 LOCKED_PHASE_2
- KAN-041: edge_aware_sampling recovery pattern added
- contracts/ma_d.yaml: KAN-020 skeleton created, write_inhibit=true
- adoption_hooks: Slack/Teams placeholders added to global schema
- Infrastructure reality: Databricks onboarding, Snowflake live, ClickHouse POC

## Key Manifests

| File | Purpose |
|------|---------|
| `manifests/system_manifest.yaml` | 77 components, source of truth |
| `manifests/telemetry_spec.yaml` | Error spec — all pipelines must use |
| `manifests/graduated_trust_tiers.yaml` | Trust model, `law_for: narrative-agent, governance-agent` |
| `manifests/hypothesis_library.yaml` | 23 hypotheses — 16 APPROVED, 7 PENDING |
| `manifests/governance_principles.yaml` | 21 constitutional principles — WARN_NOT_FAIL framework |
| `manifests/data_dictionary_master.yaml` | KAN-011 — Living Data Dictionary — constitutional foundation. Generates human + agentic dictionaries from single master source. Governed by 21 principles. |

## Model Config

- **Primary:** `claude-sonnet-4-6`
- **Local:** `qwen2.5-coder:14b` via Ollama at `http://localhost:11434`
- **Use local for:** yaml generation, file creation, validation scripts
- **Use Claude for:** architecture decisions, governance review, complex reasoning

## Model Routing Rules

- Use Sonnet (claude-sonnet-4-6) for: multi-file logic, CLI tools with flags,
  telemetry compliance, anything reading multiple manifests
- Use Qwen (local) for: simple YAML scaffolds, single-file templates,
  validation scripts under 50 lines
- Default to Sonnet when in doubt — switch to Qwen only for clearly simple tasks

## Programme Principles

1. Every Friday: something deployed, board moved, technical problem solved
2. Manifest is source of truth — Jira is a view, never the source
3. Audit before architecture
4. Semantic telemetry on every failure
5. Build for future agents — all config machine-readable YAML
6. One command to run everything: `python run_daily.py --date YYYY-MM-DD`
7. AI is easy to demo. It is hard to ship. Day 90 is a shipping proof, not a demo.

## Governance Principles (The 21)

P1: PII recorded, masked, never ignored
P2: Triple naming — raw (sealed), friendly (human), agent_name (agents)
P3: Two dictionaries — human gold, agentic context — from one master source
P4: Raw names sealed — stored for traceability, never surfaced at any price
P5: Client identity sealed — TAQ Bank is sponsor, all other client names sealed
P6: Observability — freshness, quality, lineage, usage tracked per field
P7: Human-in-the-loop instrumented — auditable, escalatable, overridable
P8: Knowledge persistence — agents learn, institutional memory survives
P9: Semantic versioning — field meanings versioned, historical analysis uses correct version
P10: Purpose limitation — agents access only fields permitted for their declared purpose
P11: Agent identity and lifecycle — sovereign identity, governed lifecycle, named human owner
P12: Memory compartmentalisation — tenant isolation, certified memory wipe on transition
P13: Adversarial resilience — Guardian Agent Layer, red teaming, circuit breakers
P14: Decision provenance — glass box, tamper-evident, 7-year retention
P15: Inter-agent contracts — authenticated, topology declared, handoffs logged
P16: Dynamic consent — real-time consent registry, field filtering, cross-border arbitration
P17: Independent validation and TEVV — staged to deployed gate, fallback tested
P18: Retention and legal hold — every artifact has retention class and deletion rule
P19: Third-party supply chain — SBOM, vendor registry, exit strategy
P20: Customer outcome guardrails — foreseeable harm monitoring, circuit breakers
P21: Fairness and bias mitigation — protected characteristics, fairness metrics mandatory

## Critical Rules

- Principle violations are WARN not ERROR — builds never fail on principle checks
- WARN_P codes emitted with principle reference, severity, and audit_logged flag
- P4 — raw field names never printed, logged, or passed to any agent under any circumstance
- P5 — TAQ Bank is the only client name that may appear in any output
