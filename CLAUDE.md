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
- MIL-1: Constitutional Docs — MIL_SCHEMA.yaml, CHRONICLE.md, SOVEREIGN_BRIEF.md (BUILT — 2026-03-28)
- MIL-2: Config + Bootstrap — apps_config.yaml, mil_findings.json (BUILT — 2026-03-28)
- MIL-3: Validator + CLAUDE.md — Zero Entanglement enforcement (BUILT — 2026-03-28)
- MIL-4: Harvester Stack — voice_intelligence_agent.py, 9 sources (BUILT — 2026-03-28, commit 6fbf4cb)
- MIL-5: Jax Filter + Rating Velocity Monitor (BUILT — 2026-03-28, commit 6fbf4cb)
- MIL-6: HDFS Storage Layer — dual-write, port 9871 (BUILT — 2026-03-28)
- MIL-7: Teacher Agent + Synthetic Engine — run_teacher.py wrapper (BUILT + CLOSED — 2026-04-02, commits fb74936/47c9aad)
- MIL-8: Research Trigger + MIL Agent — CAC + RAG, research_trigger.py Step 4a (BUILT + CLOSED — 2026-03-30/2026-04-02)
- MIL-9: Command Dashboard + Scheduler — mil/command/app.py, mil/scheduler.py, app/pages/07_mil.py (BUILT + CLOSED — 2026-04-02, commit 46d18ee)
- MIL-10: Publish + Domain — publish.py, cjipro.com/briefing (BUILT + CLOSED — 2026-04-02)

## MIL Pipeline State — 2026-04-02 (updated)

### Infrastructure
- **docker-compose.yml**: mil-namenode (port 9871) + mil-datanode (ports 9864/9866) LIVE
  - Zero Entanglement: MIL HDFS sovereign on 9871. CJI Pulse HDFS on 9870. Never shared.
  - WebHDFS 2-step PUT confirmed working: NameNode 9871 → DataNode 9864 redirect chain
  - HDFS volumes: C:/Users/hussa/hdfs-volumes/mil-namenode + mil-datanode
- **ARCH-001**: Qwen-14B decommissioned from MIL enrichment. Claude Haiku is now primary enrichment model.
- **ARCH-002**: qwen3:14b evaluated for enrichment (2026-04-03). 20-record blind test vs Haiku baseline: schema compliance 100%, issue_type agreement 90%, severity agreement 95%. DISQUALIFIED for enrichment — downgraded a P0 blocking issue to P2. P0 accuracy is non-negotiable for MIL. Haiku retained for enrichment. qwen3 approved for exec alert synthesis (Box 3) — pending implementation in briefing_data.py.

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
- Current state: **8/8 VAULTED** at 20260403_170009 — all claude-haiku-4-5-20251001
  - app_store_barclays_enriched.json: VAULTED
  - app_store_lloyds_enriched.json: VAULTED
  - app_store_monzo_enriched.json: VAULTED
  - app_store_natwest_enriched.json: VAULTED (new — 2026-04-03)
  - app_store_revolut_enriched.json: VAULTED (new — 2026-04-03)
  - google_play_barclays_enriched.json: VAULTED
  - google_play_natwest_enriched.json: VAULTED
  - google_play_revolut_enriched.json: VAULTED

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
  4a. Research Trigger — flags P0/P1 weak-anchor findings → mil/data/research_queue.jsonl
  4b. Vault — vault_sync.py, re-vaults on record count or model change, HDFS 9871
  5. Publish — publish.py, briefing_data.py, GitHub Pages push -> cjipro.com/briefing
  6. Log Run — appends to mil/data/daily_run_log.jsonl, reports M1 streak

Flags:
  `--dry-run`    fetch + enrich only, skip inference + publish
  `--skip-fetch` skip fetch + enrich, re-run inference + publish only

Human is ONLY required for: governance review (CHR entries), M2 countersign, Jira ticket closure.

### MIL Jira — Kanban Board

**Phase 0 — COMPLETE**
- MIL-1 through MIL-10: ALL BUILT + CLOSED (2026-04-02)

**Phase 1 — Queued (all To Do, gated on M1 closure unless noted)**
- MIL-11: Config-driven model routing — model_routing.yaml + get_model() utility (3–4h)
- MIL-12: Vane Trajectory Chart — mil/command/components/vane_chart.py (2–3h)
- MIL-13: Inference Cards — mil/command/components/inference_cards.py (2–3h)
- MIL-14: Clark Protocol + Scheduler — P1 escalation, auto-downgrade, APScheduler (4–5h, depends on MIL-12/13)
- MIL-15: Exit Strategy Button — click_log.jsonl, Phase 2 demand evidence (1–2h, depends on MIL-13)
- MIL-16: Teacher Autopsies (live run) — Sonnet API execution of run_teacher.py (1–2h, gated on API credit top-up, NOT M1)

**Source Activation — Queued (all To Do)**
- MIL-17: Source Activation: DownDetector — outage detection, 0.95 trust weight. INCLUDE. (2–3h)
- MIL-18: Source Activation: Financial Times + City A.M. — news signals, 0.90 trust weight. CityAM INCLUDE / FT DEFER (paywall). (3–4h)
- MIL-19: Source Activation: Reddit — narrative context, 0.85 trust weight. INCLUDE via free tier OAuth. (3–4h)
- MIL-20: Source Evaluation: Trustpilot — DEFERRED. Legal risk, ToS prohibits scraping, no public API. Re-evaluate Day 60.
- MIL-21: Source Evaluation: Facebook — EXCLUDED. Poor ROI, Graph API restricted, low signal quality.
- MIL-22: Source Activation: YouTube — comments + metadata, 0.75 trust weight. INCLUDE via Data API v3 (free). (2–3h)
- MIL-23: Source Evaluation: Twitter/X — EXCLUDED. Cost prohibitive ($200/mo minimum), unusable free tier.
- MIL-24: Source Evaluation: Glassdoor — EXCLUDED. Out of MIL scope (employee intelligence, not market intelligence).

**Revised Source Stack (6 active sources):**
| Source | Trust Weight | Status |
|--------|-------------|--------|
| App Store | 0.90 | LIVE |
| Google Play | 0.90 | LIVE |
| DownDetector | 0.95 | ACTIVATE (MIL-17) |
| City A.M. | 0.90 | ACTIVATE (MIL-18) |
| Reddit | 0.85 | ACTIVATE (MIL-19) |
| YouTube | 0.75 | ACTIVATE (MIL-22) |

Next ticket: MIL-25
Build order after M1: MIL-11 → MIL-12 → MIL-13 → MIL-15 → MIL-14. Source activation tickets can run in parallel.

### Day 30 Success Metrics — Current State
- M1 (Signal Pipeline Live): **Run #1 + Run #2 — 2026-04-03 CLEAN (same calendar day, streak 1/5). 3 more calendar days needed.** Tracker: mil/data/daily_run_log.jsonl
- M2 (One Validated Finding): **DONE** — NatWest MIL-F-20260402-047, CAC=0.652, CHR-001, COUNTERSIGNED 2026-04-02
- M3 (Designed Ceiling Trigger): **DONE** — 22 active ceiling triggers

### Pending Human Actions (Hussain)
- M1: run `py run_daily.py` daily — 3 more calendar days closes M1
- Top up Anthropic API credits (console.anthropic.com) — $5 covers 1–3 months. Unblocks: enrichment for new records + teacher autopsies
- Run `py run_teacher.py` after credits topped up (live Sonnet autopsies, one-time)
- MIL-11: implement ARCH-002 exec alert switch — change briefing_data.py to qwen3:14b via Ollama (after M1 closes)
- CHR-003: confirm HSBC root cause if source ever becomes available
- Cloudflare: purge cache after each briefing deploy if changes not visible

## MIL — Market Intelligence Layer

### What MIL Is

Sovereign Early Warning System built on 100% public market signals. Air-gapped from internal systems. Monitors 6 competitor apps (NatWest, Lloyds, HSBC, Monzo, Revolut, Barclays) across 6 signal sources: App Store (live), Google Play (live), DownDetector (MIL-17), City A.M. (MIL-18), Reddit (MIL-19), YouTube (MIL-22). Three sources evaluated and excluded: Facebook (poor ROI), Twitter/X (cost prohibitive), Glassdoor (wrong domain). One deferred: Trustpilot (legal risk). One deferred: FT (paywall).
**Current corpus: 3,587 enriched records across 8 files (schema v3, claude-haiku-4-5-20251001). app_store/natwest + app_store/revolut now live as of 2026-04-03.**

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

### MIL Model Routing — Updated 2026-04-03

- **Refuel-8B (local):** Signal classification, journey attribution, MIL inference (CAC + RAG), Adversarial Attacker evaluation — `michaelborck/refuled:latest` at `http://127.0.0.1:11434/v1`
- **Qwen 2.5-Coder (local):** YAML/Markdown generation, narrative generation, non-inference scripting — `qwen2.5-coder:14b` at `http://127.0.0.1:11434`
- **Qwen3 (local):** Executive alert synthesis (Box 3 in publish.py) ONLY — `qwen3:14b` at `http://127.0.0.1:11434`. Approved by ARCH-002. Not approved for enrichment. PENDING implementation in briefing_data.py.
- **Haiku (Claude API):** Enrichment ONLY — `claude-haiku-4-5-20251001`. Retained per ARCH-002. P0 severity accuracy critical.
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
| `mil/CHRONICLE.md` | **MIL banking failure ledger** — CHR-001 TSB 2018, CHR-002 Lloyds 2025, CHR-003 HSBC 2025, CHR-004 Barclays 2026, ARCH-001, ARCH-002 |

## Model Routing — Updated 2026-04-03

**MIL inference routes to Refuel-8B. Enrichment stays on Haiku (ARCH-002). Exec alert (Box 3) approved for qwen3:14b — pending implementation. Qwen 2.5-Coder remains default for non-inference tasks. Conserve Sonnet tokens.**

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
- MIL enrichment evaluation baseline (historical only — active enrichment is on Haiku via enrich_sonnet.py)
- CAC + RAG inference
- Adversarial Attacker evaluation

Use Sonnet when:
- MIL Teacher autopsies (deep causal reasoning — explicitly required by plan)
- MIL synthetic instruction pair generation (500+ pairs — reasoning chain quality critical)
- Qwen (2.5-Coder or qwen3) fails after one attempt on any task — general escalation path
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
