# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

- **Project:** CJI Pulse + MIL / while-sleeping
- **Private project** — no employer references
- **Mission:** Daily customer journey intelligence (CJI Pulse) + sovereign market intelligence (MIL)
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

### Sprint 1 — CJI Pulse Foundation
- PULSE-10: GitLab repo (BUILT)
- PULSE-17: system_manifest.yaml (BUILT, commit 377a4be)
- PULSE-19: telemetry_spec.yaml (BUILT, commit 021a8a9)
- PULSE-1G: graduated_trust_tiers.yaml (BUILT, commit d630986)
- PULSE-1H: hypothesis_library.yaml (BUILT, commit dd89e32) — **28 hypotheses** (16 APPROVED + 5 NPS APPROVED + 7 PENDING H_RES)
- PULSE-13: audit_findings.yaml (BUILT, commit fe492e2)
- PULSE-18: build_from_manifest.py (BUILT, commit bb47a21)
- PULSE-12: Docker environment (BUILT)
- PULSE-11: Living Data Dictionary (IN_PROGRESS — tracks A–G complete, awaiting master dict field population from Hussain)

**In progress:** PULSE-11 v2.0 — blocked on Hussain populating 6 pending tables in data_dictionary_master.yaml.
**Next after PULSE-11:** PULSE-16 — Create all Jira tickets

### Sprint 2 — MIL Phase 0 (Active from 2026-03-28)
- PULSE-2A: MIL_SCHEMA.yaml (BUILT — 2026-03-28)
- PULSE-2B: mil/CHRONICLE.md — 3 entries drafted, REVIEW REQUIRED by Hussain
- PULSE-2C: SOVEREIGN_BRIEF.md (BUILT — 2026-03-28)
- PULSE-2D: apps_config.yaml + mil_findings.json bootstrap (BUILT — 2026-03-28)
- PULSE-2E: Build validator + CLAUDE.md clean-up (IN_PROGRESS)
- PULSE-2F: voice_intelligence_agent.py (NOT_STARTED — Week 2)
- PULSE-2G: jax_synthetic_filter.py + rating_velocity_monitor.py (NOT_STARTED — Week 2)
- PULSE-2H: teacher_agent.py + synthetic_engine.py + research_trigger.py + mil_agent.py (NOT_STARTED — Week 3)
- PULSE-2I: Command dashboard + scheduler.py + adapter shim (NOT_STARTED — Week 4)
- PULSE-2J: publish.py (NOT_STARTED — Week 4)

## MIL — Market Intelligence Layer

### What MIL Is

Sovereign Early Warning System built on 100% public market signals. Air-gapped from internal systems. Monitors 6 competitor apps: NatWest, Lloyds, HSBC, Monzo, Revolut, Barclays.

### MIL Zero Entanglement — HARD RULE

```
No file under mil/ may import from pulse/, poc/, app/, dags/, or any internal module.
No file outside mil/ may import from mil/ directly.
Permitted crossing: read mil/outputs/mil_findings.json only.
Violation: fails build validator (hard failure, not a warning).
```

Enforced by: `py scripts/validate_mil_import_rule.py`

### MIL — P5 Does Not Apply

MIL processes exclusively public market data. No internal customer data, no telemetry, no PII.

**MIL public data exception:** Competitors appear by their real public names in all MIL files, outputs, CHRONICLE entries, configs, training pairs, and published briefings. Barclays is Barclays. No masking required or applied in any mil/ file.

TAQ Bank (the client) does not appear in MIL because the client is not a monitored competitor — not because of P5. P5 applies to CJI Pulse internal systems only.

### MIL Constitutional Documents

| File | Purpose |
|------|---------|
| `mil/CHRONICLE.md` | Immutable banking failure ledger — TSB 2018, Lloyds 2025, HSBC 2025. Separate from root CHRONICLE.md. |
| `mil/MIL_SCHEMA.yaml` | Canonical schema for all MIL findings, sources, CAC formula, failure modes |
| `mil/SOVEREIGN_BRIEF.md` | Trust manifesto — Article Zero, Air-Gap, Blind Spot Register, Human Operating Model |
| `mil/config/apps_config.yaml` | Full signal stack — 10 sources, 5 competitors, trust weights |
| `mil/outputs/mil_findings.json` | THE ONLY EXIT POINT — sole data crossing from MIL to CJI Pulse |

### MIL Model Routing

- **Qwen (local):** All YAML/Markdown generation, signal classification, narrative generation, MIL inference (CAC + RAG), Adversarial Attacker evaluation
- **Sonnet (Claude API):** Teacher autopsies only — TSB, Lloyds, HSBC deep causal analysis + synthetic instruction pair generation
- **RTX 5070 Ti:** QLoRA fine-tuning — POST-DAY 30 ONLY, gated on 5 conditions

### MIL Dashboard

MIL pages register as pages 07+ in the existing Streamlit app (port 8501). Thin adapter at `app/pages/07_mil.py` — routing shim only, no MIL logic. Calls into `mil/command/app.py`.

## CJI Pulse — Previous Session Notes

PULSE-11 v2.0 tracks complete (2026-03-12):
- Track A: data_strategy_v2.md (commit 846a306)
- Track B: governance_principles.yaml v2.0 (commit ba19e96)
- Track C: data_dictionary_master.yaml — 23 tables, 17 with fields, 6 pending access
- Track D: system_manifest.yaml (commit 6e0cf82)
- Track E: CLAUDE.md (this file)
- Track F: validate_PULSE-11.py v2.0 — 16/16 PASS (commit cce12bd)
- Track G: system_manifest.yaml final sync + HANDOVER.md

Session 5 Part 2 (2026-03-12):
- AF-001 CLOSED WITH CAVEAT: OCR accepted as interim journey source
- AF-002 CLOSED WITH CAVEAT: DADTL.applicationversion 60-79% coverage
- AF-003 OPEN: REGS 622K false active registrations
- AF-004 OPEN: PII in OBRE atrb_val columns

## Visualization & Automation Layer — Phase 4 (2026-03-13)

| Component | Path | Purpose |
|-----------|------|---------|
| Streamlit app | `app/cji_app.py` | Glass layer — connects to HDFS NameNode at `http://namenode:9870` via WebHDFS |
| dbt project | `twin_refinery/` | Refinement layer — reads from `raw.maer_batch_01` in PostgreSQL |
| dbt profiles | `twin_refinery/profiles.yml` | Targets `postgresql:5432`, db=`cjipulse`, schema=`staging` |
| GitLab CI | `.gitlab-ci.yml` | Build → Test (HDFS compliance + governance) → Push |
| CI tests | `ci/test_hdfs_compliance.py` | HDFS file existence + schema + P4/P5 sample check |
| CI tests | `ci/test_governance_compliance.py` | Full CSV governance gate (P4 + P5 rules) |

### Governance Rules for dbt Models
- All staging models must filter `org_name = 'Habib Bank'` — no raw client names
- P4: `hmac_ref` column must always equal `HASH_PENDING_ORIGINAL` at staging layer
- Violations in dbt tests = pipeline blocked — not WARN, full FAIL

## Key Manifests

| File | Purpose |
|------|---------|
| `manifests/system_manifest.yaml` | Source of truth — all components |
| `manifests/telemetry_spec.yaml` | Error spec — all pipelines must use |
| `manifests/graduated_trust_tiers.yaml` | Trust model, `law_for: narrative-agent, governance-agent` |
| `manifests/hypothesis_library.yaml` | **28 hypotheses** — 21 APPROVED (incl. 5 NPS), 7 PENDING H_RES |
| `manifests/data_strategy_v2.md` | PULSE-11 v2.0 — complete data strategy |
| `manifests/governance_principles.yaml` | 21 constitutional principles v2.0 |
| `manifests/data_dictionary_master.yaml` | PULSE-11 — master source, never read directly |
| `CHRONICLE.md` | **Operational Lessons Learned** — port conflicts, HDFS lessons, Airflow 3.x rules |
| `mil/CHRONICLE.md` | **MIL banking failure ledger** — TSB 2018, Lloyds 2025, HSBC 2025 |

## Model Routing — Updated 2026-03-28

**Qwen hard rule expired 2026-03-18. Sonnet is now available. Preference remains Qwen-first — conserve Sonnet tokens.**

**DEFAULT: Qwen** (qwen2.5-coder:14b at http://localhost:11434)

Use Qwen for:
- YAML edits and field population
- Single-file scripts and validators
- Jira/GitLab API calls
- Commit and validation runs
- Signal classification and MIL narrative generation
- Any clearly isolated, well-defined task

Use Sonnet when:
- MIL Teacher autopsies (deep causal reasoning — explicitly required by plan)
- MIL synthetic instruction pair generation (500+ pairs — reasoning chain quality critical)
- Qwen fails after one attempt
- Multi-manifest logic spanning 3+ files
- Explicitly instructed by Hussain

## Programme Principles

1. Every Friday: something deployed, board moved, technical problem solved
2. Manifest is source of truth — Jira is a view, never the source
3. Audit before architecture
4. Semantic telemetry on every failure
5. Build for future agents — all config machine-readable YAML
6. One command to run everything: `python run_daily.py --date YYYY-MM-DD`
7. AI is easy to demo. It is hard to ship. Day 90 is a shipping proof, not a demo.
8. Build the honest version, not the impressive one. (MIL Article Zero)

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
P12: memory_tenant_isolated_wipe_on_merge
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
- P5 extension — applies to CJI Pulse internal systems only. MIL is exempt (public data, no PII). Barclays is Barclays in all MIL contexts.

## Critical Rules — DATA STRATEGY v2.0

- Original table and field names NEVER enter any file, log, prompt, or output.
  Only HMAC-SHA256 hashes stored. Hashes generated outside codebase by
  original system only. Never by Claude Code. Never by any script here.

- Source hashes stored in data_dictionary_master.yaml ONLY.

- Substitution registry is active and mandatory:
  * Any reference to original client name → replace with Habib Bank
  * Any reference to BMB → replace with APP
  * Only TAQ Bank ever surfaces as organisational name

- DPIA required before live customer data is processed. REG-001 through REG-004 open.

- Two dictionaries generated from one master source:
  * data_dictionary_human.yaml — gold fields only, human names, no hashes
  * data_dictionary_agentic.yaml — all fields, agentic names, context-rich
  * data_dictionary_master.yaml — single source, never read directly
