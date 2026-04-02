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

## JIRA PROJECTS — TWO SEPARATE SYSTEMS

### PULSE Project — CJI Pulse only
Site: cjipro.atlassian.net
Key: PULSE
Tickets: PULSE-1 through PULSE-83 (current)
Next ticket: PULSE-84
Board: Scrum
Scope: Internal customer journey intelligence only. PII present. Highly governed.

### MIL Project — MIL sovereign system only
Site: cjipro.atlassian.net
Key: MIL
Board: Kanban
URL: cjipro.atlassian.net/jira/software/projects/MIL/boards/35
Cloud ID: d9b829b8-66af-42de-bc53-a79515365742
Tickets: MIL-1 through MIL-6 (BUILT)
Next ticket: MIL-7
Scope: Public market intelligence only. No PII. Open governance.

### Hard Rule
Never create a PULSE ticket for MIL work.
Never create a MIL ticket for CJI Pulse work.
Claude Code creates MIL Jira tickets programmatically when instructed.
Hussain closes all tickets manually in Jira UI — never programmatically.
Dual closure rule applies to both projects: validator passes AND Hussain closes in UI.

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
- PULSE-2B: mil/CHRONICLE.md — CHR-001/002/003/004 + ARCH-001 logged (REVIEW REQUIRED by Hussain)
- PULSE-2C: SOVEREIGN_BRIEF.md (BUILT — 2026-03-28)
- PULSE-2D: apps_config.yaml + mil_findings.json bootstrap (BUILT — 2026-03-28)
- PULSE-2E: Build validator + CLAUDE.md clean-up (IN_PROGRESS)
- PULSE-2F: voice_intelligence_agent.py (NOT_STARTED — Week 2)
- PULSE-2G: jax_synthetic_filter.py + rating_velocity_monitor.py (NOT_STARTED — Week 2)
- PULSE-2H: teacher_agent.py + synthetic_engine.py + research_trigger.py (NOT_STARTED — Week 3)
- **mil_agent.py (MIL-8): BUILT — 2026-03-30** (see MIL Pipeline State below)
- PULSE-2I: Command dashboard + scheduler.py + adapter shim (NOT_STARTED — Week 4)
- PULSE-2J: publish.py (BUILT — Sonar briefing live at https://cjipro.com/briefing)

## MIL Pipeline State — 2026-04-01 (updated 20:43 UTC)

### Infrastructure
- **docker-compose.yml**: mil-namenode (port 9871) + mil-datanode (ports 9864/9866) LIVE
  - Zero Entanglement: MIL HDFS sovereign on 9871. CJI Pulse HDFS on 9870. Never shared.
  - WebHDFS 2-step PUT confirmed working: NameNode 9871 → DataNode 9864 redirect chain
  - HDFS volumes: C:/Users/hussa/hdfs-volumes/mil-namenode + mil-datanode
- **ARCH-001**: Qwen-14B decommissioned from MIL enrichment. Claude Haiku is now primary enrichment model.

### Enrichment Pipeline (enrich_sonnet.py — schema v3) ← ACTIVE
File: `mil/harvester/enrich_sonnet.py`
- Model: claude-haiku-4-5-20251001 via Anthropic API
- Batch size: 10 records per API call
- Schema v3 fields per record:
  - issue_type: 16 categories (App Not Opening, Login Failed, Payment Failed, etc.)
  - customer_journey: 9 categories (Log In, Make a Payment, Transfer Money, etc.)
  - sentiment_score: float -1.0 to 1.0
  - severity_class: P0 / P1 / P2 with severity gate in _normalise()
  - reasoning: one sentence
- **Severity gate**: P0/P1 only for blocking issues (App Not Opening, Login Failed, Payment Failed,
  Transfer Failed, Account Locked, App Crashing). Positive Feedback always P2.
- v3 skip logic: `_is_v3(r)` check — already-enriched records skipped, daily run < 1 second
- JSON repair pipeline: trim → json.loads → json_repair fallback → ENRICHMENT_FAILED
- **rsplit fix**: new source+competitor keys split on last `_` so `app_store_barclays` → source=`app_store`, competitor=`barclays`
- Old pipeline (qwen_enrichment.py schema v2) — superseded, do not use for new enrichment

### Vault (vault_sync.py)
File: `mil/vault/vault_sync.py`
- Reads from mil/data/historical/enriched/*.json
- Pushes to HDFS /user/mil/enriched/ via WebHDFS (port 9871)
- DuckDB anchor log: mil/vault/mil_vault.db (vault_anchor_log table)
- **DataNode hostname rewrite**: `hdfs_client.py` rewrites redirect URL from `mil-datanode:9864` → `localhost:9864` before DataNode PUT — fixes 403 after Docker restarts
- SKIPPED_WRONG_MODEL guard: blocks any file enriched with qwen model
- **_needs_vault()**: re-vaults when record count OR model changes (not just by filename)
- **Vault step wired into run_daily.py as Step 4b** (after inference, before publish)
- Current state: **6/6 VAULTED** at 20260401_194330 — all claude-haiku-4-5-20251001
  - app_store_barclays_enriched.json: 67 records VAULTED
  - app_store_lloyds_enriched.json: 532 records VAULTED
  - app_store_monzo_enriched.json: 524 records VAULTED
  - google_play_barclays_enriched.json: 651 records VAULTED
  - google_play_natwest_enriched.json: 612 records VAULTED
  - google_play_revolut_enriched.json: 698 records VAULTED
- Missing backfill: app_store/natwest + app_store/revolut (no raw data harvested yet)

### Inference Engine (mil_agent.py — MIL-8)
File: `mil/inference/mil_agent.py`
- CAC formula: C_mil = (alpha*Vol_sig + beta*Sim_hist) / (delta*Delta_tel + 1)
  - alpha=0.40, beta=0.40, delta=0.20 (not tuned before Day 30)
- RAG: keyword overlap against CHRONICLE entries (CHR-001/002 inference_approved only)
  - CHR-003: inference_approved=false (root cause unconfirmed)
  - CHR-004: inference_approved=false (Barclays enrichment awaiting Hussain review)
- Designed Ceiling: triggers when CAC > 0.45 AND delta_tel=0.0
  - Output: "To confirm this I require internal HDFS telemetry data. Request Phase 2."
- Refuel-8B called per finding for blind_spots + narrative + failure_mode
- Deterministic fallback if Refuel unavailable (Article Zero compliant)
- issue_type (v3) -> journey_id mapping in JOURNEY_MAP (updated from v2 journey_category)
- Current findings: **63 total** | 63 anchored | 0 unanchored | 22 Designed Ceiling

### Briefing Data Layer (briefing_data.py)
File: `mil/briefing_data.py`
- Fully dynamic: no hardcoded journey list
- get_briefing_data() returns complete dict for publish.py and dashboard
- Sentiment: avg star rating x20 (0-100), 7-day rolling window
- **Trend: real 3d/4d split per competitor** — anchor on latest review date, split -3 days,
  compare avg rating earlier 4d vs current 3d. WORSENING if delta > 5pts, IMPROVING if +5pts.
- Issue Score = Volume x Severity_Weight x Trend_Factor x CHRONICLE_Bonus
- Dual-lens output: issues_performance (what went wrong) + journey_performance (what customer tried)
- **Barclays baseline**: all-time avg from both app_store + google_play enriched files (651 records)
  - Current: score=89, baseline=90, delta=-1, trend=STABLE
- Executive alert: self-intelligence framing ("YOUR APP"), Sonnet synthesis of P0 reviews,
  conditional Chronicle match (keyword overlap >= 2), signal strength STRONG/MODERATE/EARLY SIGNAL
- Chronicle matching: CHR-001 (TSB 2018) and CHR-002 (Lloyds 2025) on issue_type overlap
- Top quote selection: P0 first, P1 fallback, 40+ chars, prefer 60-200 chars
- Current output (2026-04-01):
  - Barclays sentiment: 88.8/100, baseline 90, -1.2 vs baseline, STABLE
  - Competitor ticker: NatWest worst (64), Barclays 88.8

### Sonar Briefing — publish.py
File: `mil/publish/publish.py`
- Box 1 layout (top to bottom):
  1. Header: CJI SONAR — APP INTELLIGENCE
  2. Barclays sentiment card — label 15px, score pushed right with margin-left:auto
     (score, real 3d/4d trend, all-time Barclays baseline, delta vs baseline)
  3. Dual quote boxes — App Store (top) + Google Play (bottom), both Barclays only,
     P0 first with P1 fallback, 104px fixed height, star rating + source + date stamp footer
  4. Brand lines (15px): "Live signals from App Store, Google Play..." + "Historical failure patterns..."
  5. Version pills
  6. Footnote (10px, #3A6A7F): "Sentiment score: 7-day rolling avg · App Store & Google Play · Barclays only · star ratings inc. text-free reviews"
- Box 2 (Issues Status): Barclays only — issue_type counts, trend, P0/P1. Direct quote at bottom
  tied to top-ranked issue_type (P0->P1 fallback, de-duped vs Box 1 quotes, issue label in small caps)
- Box 3 (Executive Alert): Barclays only — self-intelligence framing ("YOUR APP"), Sonnet synthesis,
  Chronicle match conditional (CHR-001/CHR-002, intentional historical reference), YOUR CALL
- All three boxes confirmed Barclays-scoped
- Brand line font: 15px
- Note: cjipro.com behind Cloudflare — cache purge may be needed after deploy to see changes immediately

### Daily Pipeline — ONE COMMAND (fully agentic)
```
py run_daily.py
```
Steps (zero human intervention required):
  1. Fetch — App Store + Google Play, all active competitors, dedup against existing
  2. Enrich — Claude Haiku schema v3, skip already-enriched v3 records (< 1 second if nothing new)
  3. Inference — mil_agent.py CAC + RAG, Chronicle matching, Designed Ceiling
  4. Vault — vault_sync.py, re-vaults on record count or model change, HDFS 9871
  5. Publish — publish.py, briefing_data.py, GitHub Pages push -> cjipro.com/briefing

Flags:
  `--dry-run`    fetch + enrich only, skip inference + publish
  `--skip-fetch` skip fetch + enrich, re-run inference + publish only

Human is ONLY required for: governance review (CHR entries), M2 countersign, Jira ticket closure.

### MIL Jira — Kanban Board
- MIL-1 through MIL-6: BUILT (2026-03-28)
- MIL-7: Teacher Agent + Synthetic Engine — NOT_STARTED (requires Sonnet API, Hussain gate)
- MIL-8: mil_agent.py — **BUILT 2026-03-30** (commits 9f7ecc4, c3e35a7)
- MIL-9: Sonar Streamlit dashboard — BUILT (2026-03-31)
- Next MIL ticket: MIL-10

### Day 30 Success Metrics — Current State
- M1 (Signal Pipeline Live): Pipeline operational. run_daily.py: fetch → enrich → inference → vault → publish. IN_PROGRESS (need 5 consecutive clean days).
- M2 (One Validated Finding): NatWest J_SERVICE_01 CAC=0.652, CHR-001 anchor, PENDING Hussain countersign.
- M3 (Designed Ceiling Trigger): **DEMONSTRATED** — 12 active ceiling triggers.

### Pending Human Actions (Hussain)
- CHR-004: Review Barclays enrichment results, set inference_approved if satisfied
- CHR-003: Confirm HSBC root cause or leave inference_approved=false
- M2: Countersign NatWest J_SERVICE_01 finding to close M2
- app_store/natwest + app_store/revolut: backfill raw data still missing
- Jira: close MIL-8 + MIL-9 in UI (dual closure rule)
- Cloudflare: purge cache after each briefing deploy if changes not visible

## MIL — Market Intelligence Layer

### What MIL Is

Sovereign Early Warning System built on 100% public market signals. Air-gapped from internal systems. Monitors 6 competitor apps: NatWest, Lloyds, HSBC, Monzo, Revolut, Barclays.
**Current corpus: 3,084 enriched records across 6 files (schema v3, claude-haiku-4-5-20251001). Missing: app_store/natwest + app_store/revolut backfill.**

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

- **Refuel-8B (local):** Signal classification, journey attribution, MIL inference (CAC + RAG), Adversarial Attacker evaluation — `michaelborck/refuled:latest` at `http://127.0.0.1:11434/v1`
- **Qwen (local):** YAML/Markdown generation, narrative generation, non-inference scripting — `qwen2.5-coder:14b` at `http://127.0.0.1:11434`
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
| `mil/CHRONICLE.md` | **MIL banking failure ledger** — CHR-001 TSB 2018, CHR-002 Lloyds 2025, CHR-003 HSBC 2025, CHR-004 Barclays 2026, ARCH-001 |

## Model Routing — Updated 2026-03-29

**MIL inference now routes to Refuel-8B. Qwen remains default for all non-inference tasks. Conserve Sonnet tokens.**

**DEFAULT: Qwen** (qwen2.5-coder:14b at http://127.0.0.1:11434)

Use Qwen for:
- YAML edits and field population
- Single-file scripts and validators
- Jira/GitLab API calls
- Commit and validation runs
- MIL narrative generation (non-classification)
- Any clearly isolated, well-defined task

**MIL INFERENCE: Refuel-8B** (michaelborck/refuled:latest at http://127.0.0.1:11434/v1)

Use Refuel for:
- Signal classification (journey attribution, severity, keywords)
- MIL enrichment pipeline (`mil/harvester/qwen_enrichment.py`)
- CAC + RAG inference
- Adversarial Attacker evaluation

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
