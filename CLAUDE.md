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

**In progress:** KAN-011 v2.0 — Tracks A–E complete. Awaiting field population from human.
**Next after KAN-011:** KAN-16 — Create all Jira tickets

KAN-011 v2.0 tracks complete (2026-03-12):
- Track A: data_strategy_v2.md — complete data strategy v2.0 (commit 846a306)
- Track B: governance_principles.yaml v2.0 — 21 principles, table registry, substitution registry, 3-layer governance, 4 regulatory items (commit ba19e96)
- Track C: data_dictionary_master.yaml — skeleton 10 tables, HASH_PENDING_ORIGINAL (commit 8fb05ed)
- Track D: system_manifest.yaml — KAN-011 v2.0, 82 components, REG-001 to REG-004 (commit 6e0cf82)
- Track E: CLAUDE.md — data strategy v2.0 embedded (this commit)
- Track F: validate_KAN-011.py v2.0 — 16/16 PASS, 1 WARN_P4 informational (commit cce12bd)
- Track G: system_manifest.yaml final sync + HANDOVER.md (this commit)

Manifest hardening complete (2026-03-12):
- KAN-01G: permitted_storage_targets added, Tier 5 LOCKED_PHASE_2
- KAN-041: edge_aware_sampling recovery pattern added
- contracts/ma_d.yaml: KAN-020 skeleton created, write_inhibit=true
- adoption_hooks: Slack/Teams placeholders added to global schema
- Infrastructure reality: Databricks onboarding, Snowflake live, ClickHouse POC

## Key Manifests

| File | Purpose |
|------|---------|
| `manifests/system_manifest.yaml` | 82 components, source of truth |
| `manifests/telemetry_spec.yaml` | Error spec — all pipelines must use |
| `manifests/graduated_trust_tiers.yaml` | Trust model, `law_for: narrative-agent, governance-agent` |
| `manifests/hypothesis_library.yaml` | 23 hypotheses — 16 APPROVED, 7 PENDING |
| `manifests/data_strategy_v2.md` | KAN-011 v2.0 — complete data strategy. Three names, hash strategy, two dictionaries, three-layer governance, regulatory framework. |
| `manifests/governance_principles.yaml` | 21 constitutional principles v2.0 — WARN_NOT_FAIL, table registry, substitution registry, REG-001–004 |
| `manifests/data_dictionary_master.yaml` | KAN-011 — master source, 10 tables, HASH_PENDING_ORIGINAL, never read directly by humans or agents |

## Model Config

- **Default:** `qwen2.5-coder:14b` via Ollama at `http://localhost:11434` — use for all standard tasks
- **Reserve Sonnet (`claude-sonnet-4-6`) for:** exceptions only (see routing rules below)
- **Weekly Sonnet limit running low — conserve**

## Model Routing Rules — Updated 2026-03-12

**DEFAULT: Qwen** (qwen2.5-coder:14b at http://localhost:11434)

Use Qwen for:
- YAML edits and field population
- Single-file scripts and validators
- Jira/GitLab API calls
- Commit and validation runs
- Any clearly isolated, well-defined task

Switch to Sonnet ONLY when:
- Qwen fails to resolve after one attempt
- Multi-manifest logic spanning 3+ files
- Anthropic API calls required (build_from_manifest.py)
- Explicitly instructed by Hussain

## Programme Principles

1. Every Friday: something deployed, board moved, technical problem solved
2. Manifest is source of truth — Jira is a view, never the source
3. Audit before architecture
4. Semantic telemetry on every failure
5. Build for future agents — all config machine-readable YAML
6. One command to run everything: `python run_daily.py --date YYYY-MM-DD`
7. AI is easy to demo. It is hard to ship. Day 90 is a shipping proof, not a demo.

## Governance Principles (The 21) — agent_names

P1:  pii_mask_never_ignore
P2:  triple_name_raw_friendly_agent
P3:  dict_human_gold_agent_context
P4:  raw_name_sealed_never_surface
P5:  client_identity_sealed_taq_only
P6:  data_observability_accuracy_rectify
P7:  human_loop_audit_escalate_override
P8:  agent_memory_persist_and_learn
P9:  field_version_history_aware
P10: purpose_bound_least_privilege
P11: agent_identity_lifecycle_accountable
P12: memory_tenant_isolated_wipe_on_move
P13: adversarial_guard_redteam_circuit
P14: decision_glass_box_tamper_evident
P15: agent_handoff_authenticated_logged
P16: consent_realtime_minimise_on_withdraw
P17: validate_independent_tevv_fallback
P18: artifact_retain_delete_hold
P19: vendor_sbom_registered_exit_ready
P20: outcome_harm_monitor_circuit_break
P21: fairness_protected_chars_mandatory

## Critical Rules

- Principle violations are WARN not ERROR — builds never fail on principle checks
- WARN_P codes emitted with principle reference, severity, and audit_logged flag
- P4 — raw field names never printed, logged, or passed to any agent under any circumstance
- P5 — TAQ Bank is the only client name that may appear in any output

## Critical Rules — DATA STRATEGY v2.0

- Original table and field names NEVER enter any file, log, prompt, or output.
  Only HMAC-SHA256 hashes stored. Hashes generated outside codebase by
  original system only. Never by Claude Code. Never by any script here.

- Source hashes stored in data_dictionary_master.yaml ONLY. Never in human
  dictionary, agentic dictionary, code, logs, prompts, dashboards, or reports.

- Substitution registry is active and mandatory:
  * Any reference to original client name → replace with Habib Bank
  * Any reference to BMB → replace with APP
  * Only TAQ Bank ever surfaces as organisational name

- Principle violations are WARN not ERROR. Builds never fail on principle
  checks. Violations logged permanently to provenance system. Must be resolved
  or formally overridden before next release. No third option.

- DPIA required before live customer data is processed. Four regulatory open
  items (REG-001 through REG-004) tracked in system_manifest.yaml.

- Table naming convention: human name (plain English) + agentic name (initials)
  Raw: {Channel}_{Type}_Raw | Ref: {Domain}_Ref | Derived: {Channel}_{Type}_Session
  Dim: {Domain}_Dim | Output: {Domain}_Output

- Table contracts are intentionally lean. Mandatory core always present.
  Conditional fields only where materially relevant. Nothing silently omitted —
  non-applicable markers recorded in applicability register as Not Applicable.

- Two dictionaries generated from one master source:
  * data_dictionary_human.yaml — gold fields only, human names, no hashes
  * data_dictionary_agentic.yaml — all fields, agentic names, context-rich
  * data_dictionary_master.yaml — single source, never read directly
