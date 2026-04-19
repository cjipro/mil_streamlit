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
Tickets: MIL-1 through MIL-33 (BUILT)
Next ticket: MIL-39
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

### Sprint 2 — MIL Phase 0 + Phase 1 (COMPLETE — 2026-04-05)

**Phase 0 — ALL BUILT + CLOSED**
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

**Phase 1 — ALL BUILT (2026-04-05, pending Hussain Jira closure)**
- MIL-11: Config-driven model routing — mil/config/model_routing.yaml + mil/config/get_model.py (BUILT — 2026-04-05)
- MIL-12: Vane Trajectory Chart — mil/command/components/vane_chart.py, 14-day Plotly (BUILT — 2026-04-05)
- MIL-13: Inference Cards — mil/command/components/inference_cards.py, top-N by CAC (BUILT — 2026-04-05)
- MIL-14: Clark Protocol + Scheduler — clark_protocol.py, clark_log.jsonl, APScheduler 06:30 UTC (BUILT — 2026-04-05)
- MIL-15: Exit Strategy Button — exit_strategy.py, click_log.jsonl, Phase 2 demand tracker (BUILT — 2026-04-05)
- MIL-16: Teacher Autopsies — 4 autopsies (CHR-001/002/003/004) + 550 pairs (450 fine-tune ready) (BUILT — 2026-04-04, validated 2026-04-05)
- MIL-17: Source Activation: DownDetector — collect_downdetector.py, cloudscraper + Haiku (BUILT — 2026-04-04)
- MIL-18: Source Activation: City A.M. + FT RSS — collect_cityam.py, both feeds live (BUILT — 2026-04-04)
- MIL-19: Source Activation: Reddit — collect_reddit.py, public JSON endpoints, 371 posts first run (BUILT — 2026-04-04)
- MIL-20: Trustpilot — DEFERRED (legal risk, ToS prohibits scraping). Re-evaluate Day 60.
- MIL-21: Facebook — EXCLUDED (poor ROI, Graph API restricted)
- MIL-22: Source Activation: YouTube — comments + metadata, 0.75 trust weight (BUILT — 2026-04-03, commit c2a0277)
- MIL-23: Twitter/X — EXCLUDED (cost prohibitive, $200/mo minimum)
- MIL-24: Glassdoor — EXCLUDED (employee intelligence, out of MIL scope)

**Sonar V2 — LIVE (2026-04-05)**
- File: `mil/publish/publish_v2.py`
- URL: https://cjipro.com/briefing-v2
- V1 at cjipro.com/briefing — actively maintained (not frozen)
- V2 extends V1 with: Vane Trajectory Chart (MIL-12), Inference Cards (MIL-13), Clark Protocol (MIL-14), Phase 2 Demand (MIL-15)
- All V2 sections use `.topbar-box` chrome — same width/padding as Box 1/2/3, mobile-optimised

**Sonar V3 — LIVE (2026-04-12, refined 2026-04-13)**
- File: `mil/publish/publish_v3.py`
- URL: https://cjipro.com/briefing-v3
- Loads V1 HTML, **replaces Box 3** (exec-alert-panel stripped via `_replace_box3()` div-depth counter), appends V3 intelligence sections before `</body>`. V1 and V2 untouched.
- **Box 3 = INTELLIGENCE BRIEF**: three prose sections with thin `#003A5C` dividers (Option A). The Situation (full Sonnet prose from top risk commentary box — from latest reviews, not Chronicle), Peer Comparison (deterministic: Barclays rate vs peer avg, best peer named, days, strength note), The Call (one sentence, Clark-tier-driven). One real P0/P1 review quote between Situation and Peer. No metric tiles.
- V3 intelligence sections below fold: Churn Risk Score / Analyst Commentary / Technical Benchmark / Service Benchmark / Intelligence Findings / Clark Protocol
- Local copy: mil/publish/output/index_v3.html
- Run: `py mil/publish/publish_v3.py`
- **publish_v3.py wired into run_daily.py as Step 5c** (after V2 publish, before log run)

**Next ticket: MIL-39**

**Phase A — Clone Foundation (IN PROGRESS 2026-04-19)**
- MIL-32: Taxonomy extraction — domain_taxonomy.yaml + taxonomy_loader.py (BUILT 2026-04-19)
- MIL-33: Circuit breaker — cached commentary fallback on provider failure (BUILT 2026-04-19)
- MIL-34: CHRONICLE YAML format — entries/CHR-XXX.yaml, loader reads dir (BUILT 2026-04-19)
- MIL-35: Publish adapter — BUILT 2026-04-19. `mil/publish/adapters.py` holds `PublishAdapter` base + `GitHubPagesAdapter`, `LocalAdapter`, `NullAdapter`. `mil/config/publish_config.yaml` selects adapter. `publish_v4.py` migrated to call `get_adapter().publish("briefing-v4/index.html", html)` — 70 lines of git-boilerplate replaced with 2. V1/V2/V3 still on legacy push (migrate when Clone operators need to retarget). Credentials (GITHUB_TOKEN, PUBLISH_REPO) stay in `.env`, never in YAML.
- MIL-36: Vault backend abstraction — BUILT 2026-04-19. `mil/vault/backends.py` holds `VaultBackend` base + `HDFSBackend` (thin wrapper around existing MILHDFSClient), `LocalBackend` (HDFS-style paths map to root_dir/<stripped>), `NullBackend`. `mil/config/vault_config.yaml` selects backend. `vault_sync.py` migrated to `get_backend()` — zero behaviour change when `adapter: hdfs` (default). Clone operators flip to `adapter: local` to run without an HDFS cluster. Run_daily.py Step 4b preflight is now backend-aware: TCP-checks port only for hdfs, no-ops for local/null.
- MIL-37: Data Egress Logger — data_egress_log.jsonl, every external API call logged (BUILT 2026-04-19)
- MIL-38: Notification layer — Slack adapter live; Autonomous Heartbeat live — STARTING ping at main() entry + CRASHED ping from outer exception handler at `__main__`, plus existing CLEAN/PARTIAL/FAILED completion ping (zero-finding runs included). Absence of a completion ping within ~30 min of STARTING = mid-pipeline crash; no STARTING at 06:30 UTC = cron didn't fire. (BUILT 2026-04-19)
- MIL-39: Jinja2 migration — BUILT 2026-04-19 as **Sonar V4 parallel briefing** at cjipro.com/briefing-v4. Same layout as V3 plus four-field Provenance Chain per Inference Card (chronicle_id / signal_ids / class_ver / teacher_ver — FCA Consumer Duty 2.0). V3 untouched on legacy f-string path for cutover window. Retire V3 only after V4 proves out 7+ clean days.
- MIL-48: Drift Detection Monitor — BUILT 2026-04-19. `mil/monitoring/drift_monitor.py` + `mil/config/drift_thresholds.yaml`. MVP ships Silent Wall detector with baseline-relative spike semantics: compares current 14-day window's silent-1-star ratio against a 30-day baseline preceding it; WARN at 2× baseline, HIGH at 3× (both require ≥3 silent reviews in the current window). Absolute-ratio fallback (50% WARN / 75% HIGH) covers cold-start deployments below `min_baseline_1star=10`. Alerts append to `mil/data/drift_log.jsonl`; HIGH escalates via Slack. Wired as run_daily.py **Step 4f** (non-fatal). Calibration helper: `py mil/monitoring/drift_monitor.py --baseline-report`. Current corpus: 0 alerts (largest spike = Monzo 5.56× but only 1 silent review, correctly filtered by sample-size guard). Extend with more detectors (fetch-volume, enrichment-failure, severity-distribution) as operational needs surface.

**Phase 2 — COMPLETE (2026-04-16)**
- MIL-25: QLoRA Gate Clearance — ALL 5 GATES CLEAR. Qwen3-4B trained, Gate 5 ACTIVE (BUILT 2026-04-05, COMPLETE 2026-04-19)
- MIL-26: ARCH-003 model routing — model_routing.yaml schema v1.1, four-tier Opus/Sonnet/Haiku/Qwen3 (BUILT 2026-04-12)
- MIL-27: Benchmark Engine + Persistence Log — mil/data/benchmark_engine.py, issue_persistence_log.jsonl (BUILT 2026-04-12)
- MIL-28: Commentary Engine — mil/publish/commentary_engine.py, Sonnet analyst prose per issue type (BUILT 2026-04-12)
- MIL-29: Briefing V3 — mil/publish/publish_v3.py, live at cjipro.com/briefing-v3 (BUILT 2026-04-12)
- MIL-30: Opus Governance Tier — CLARK-3 synthesis + CHR proposals upgraded to Opus (BUILT 2026-04-12)
- MIL-31: Barclays CHRONICLE Depth — CHR-017/018/019 approved, research agent --force flag, CHR_COVERAGE bypass for Barclays J_SERVICE_01 (BUILT 2026-04-16)

## MIL Pipeline State — 2026-04-18 (Phase 2 complete, MIL autonomous from 2026-04-20)

### Infrastructure
- **docker-compose.yml**: mil-namenode (port 9871) + mil-datanode (ports 9864/9866) LIVE
  - Zero Entanglement: MIL HDFS sovereign on 9871. CJI Pulse HDFS on 9870. Never shared.
  - WebHDFS 2-step PUT confirmed working: NameNode 9871 → DataNode 9864 redirect chain
  - HDFS volumes: C:/Users/hussa/hdfs-volumes/mil-namenode + mil-datanode
- **ARCH-001**: Qwen-14B decommissioned from MIL enrichment. Claude Haiku is now primary enrichment model.
- **ARCH-002**: qwen3:14b evaluated for enrichment (2026-04-03). 20-record blind test vs Haiku baseline: schema compliance 100%, issue_type agreement 90%, severity agreement 95%. DISQUALIFIED for enrichment — downgraded a P0 blocking issue to P2. P0 accuracy is non-negotiable for MIL. Haiku retained for enrichment. qwen3 approved for exec alert synthesis (Box 3) — **IMPLEMENTED 2026-04-05** in briefing_data.py via `_exec_alert_description()` using OpenAI-compat Ollama call + `get_model("exec_alert")`.
- **ARCH-003**: Four-tier model routing formalised (MIL-26, 2026-04-12). Tier 1 Opus: governs — CHR proposals, teacher autopsies, CLARK-3 synthesis. Tier 2 Sonnet: drives daily intelligence — commentary, exec alert V3, churn narrative. Tier 3 Haiku/Refuel-8B: classifies at scale. Tier 4 Qwen3: labour — YAML, Markdown, scripts. model_routing.yaml schema v1.1.

### Enrichment Pipeline (enrich_sonnet.py — schema v3) ← ACTIVE
File: `mil/harvester/enrich_sonnet.py`
- Model: **qwen3:14b via Ollama** (switched from Haiku — ARCH-004 2026-04-19, cost saving)
- Batch size: 10 records per API call
- Schema v3 fields per record:
  - issue_type: 16 categories — loaded from `mil/config/domain_taxonomy.yaml` (MIL-32)
  - customer_journey: 9 categories — loaded from `mil/config/domain_taxonomy.yaml` (MIL-32)
  - sentiment_score: float -1.0 to 1.0
  - severity_class: P0 / P1 / P2 with severity gate via `apply_severity_gate()` (MIL-32)
  - reasoning: one sentence
- **Taxonomy config (MIL-32 2026-04-19)**: issue types, journeys, severity gate all moved to `mil/config/domain_taxonomy.yaml`. Never hardcode taxonomy in pipeline files — import from `mil/config/taxonomy_loader.py`.
- **Severity gate**: `apply_severity_gate(issue, severity)` in taxonomy_loader — caps severity at `max_severity` per issue type defined in domain_taxonomy.yaml. Blocking issues (P0 permitted): App Not Opening, Login Failed, Payment Failed, Transfer Failed, Account Locked, App Crashing.
- **ARCH-004**: enrichment switched Haiku→qwen3:14b (Ollama local). Provider-aware client: Ollama uses OpenAI-compat endpoint. Anthropic path retained as fallback if routing changes back.
- v3 skip logic: `_is_v3(r)` check — already-enriched records skipped, daily run < 1 second
- JSON repair pipeline: trim → json.loads → json_repair fallback → ENRICHMENT_FAILED
- **rsplit fix**: new source+competitor keys split on last `_` so `app_store_barclays` → source=`app_store`, competitor=`barclays`
- **Dedup fix (2026-04-17)**: dedup upgraded from 80-char text prefix to SHA-256 hash of full content — prevents duplicate records if pipeline reruns same day
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
- **HDFS preflight (2026-04-17)**: run_daily.py Step 4b TCP-checks port 9871 before vault — skips and logs warning if NameNode unreachable (no silent failure)
- Current state: **12/12 VAULTED** — all claude-haiku-4-5-20251001 (2026-04-17)
  - app_store_barclays_enriched.json: VAULTED
  - app_store_lloyds_enriched.json: VAULTED
  - app_store_monzo_enriched.json: VAULTED
  - app_store_natwest_enriched.json: VAULTED
  - app_store_revolut_enriched.json: VAULTED
  - app_store_hsbc_enriched.json: VAULTED
  - google_play_barclays_enriched.json: VAULTED
  - google_play_natwest_enriched.json: VAULTED
  - google_play_revolut_enriched.json: VAULTED
  - google_play_hsbc_enriched.json: VAULTED
  - google_play_lloyds_enriched.json: VAULTED (new — 2026-04-17, package ID fixed)
  - google_play_monzo_enriched.json: VAULTED (new — 2026-04-17, package ID fixed)

### Inference Engine (mil_agent.py — MIL-8)
File: `mil/inference/mil_agent.py`
- CAC formula: C_mil = (alpha*Vol_sig + beta*Sim_hist) / (delta*Delta_tel + 1)
  - alpha=0.40, beta=0.40, delta=0.20 — sensitivity analysis run 2026-04-17 (MODERATE sensitivity, ±3 CLARK-3 swing across weight grid). Re-run at Day 60.
- **P0 gate (2026-04-17)**: MIN_CLUSTER_SIZE_P0 raised 1→2 — requires at least 2 P0 signals before a finding reaches production
- **RAG: embedding cosine similarity (2026-04-18)** — replaced keyword overlap with `all-MiniLM-L6-v2` sentence embeddings. CHR embeddings cached in `_CHR_EMBED_CACHE` at startup; each signal text encoded once, cosine sim computed against all 19 CHR vectors. Keyword overlap retained as fallback only.
  - sim_threshold recalibrated: 0.40 → **0.30** (keyword overlap 0.40 ≠ cosine 0.40; cosine 0.30 ≈ related domain — thresholds.yaml comment documents reasoning)
- **chronicle_loader.py (2026-04-18, hardened 2026-04-18)** — `mil/inference/chronicle_loader.py` dynamically loads all `inference_approved=true` entries from `mil/CHRONICLE.md`. CRLF-safe regex, malformed entries logged at WARNING (not silently skipped), startup assertion raises RuntimeError if fewer than 15 entries load. `@lru_cache(maxsize=1)` — read once per process.
  - CHR-001 through CHR-019 all active. CHR-001 magnet effect broken — distribution confirmed: CHR-003 22%, CHR-002 18%, CHR-005 18%, no single entry dominates.
- **CAC formula extracted (2026-04-18)**: `compute_cac()` + `compute_vol_sig()` → `mil/inference/cac.py`. Independently testable. mil_agent.py imports from cac.py.
- **RAG layer extracted (2026-04-18)**: `find_best_chronicle_match()` + embedding cache → `mil/inference/rag.py`. Independently testable. Accepts `chronicle_entries` as explicit param (no module-global dependency). mil_agent.py imports from rag.py.
- **finding_summary deterministic (2026-04-18)**: `f"{dominant_sev} signal cluster: {competitor} {journey_id}, {P0} P0 / {P1} P1 signals, anchor: {chronicle_id}."` — no LLM call for summary generation
- Refuel-8B called per finding for `blind_spots` + `failure_mode` only (not finding_summary)
- Deterministic fallback if Refuel unavailable (Article Zero compliant)
- issue_type (v3) -> journey_id mapping in JOURNEY_MAP (updated from v2 journey_category)
- **Current findings: 138 total | 100% anchored | 7 Designed Ceiling (2026-04-19, Run #35)**
- **blind_spots fix**: Refuel-8B returns blind_spots as string; coerced to list on ingest (2026-04-05)

### Analytics Database — mil_analytics.db (BUILT 2026-04-17, updated 2026-04-18)
File: `mil/analytics/build_analytics_db.py`
- Complete queryable analytics layer — 9 tables, rebuilt every run as Step 4e
- **Tables (as of Run #35, 2026-04-19):**
  - `reviews` — 7,418 enriched records across all 6 sources / 6 competitors
  - `findings` — 136 CAC findings (confidence_score, cac_components, chronicle_id, clark tier, ceiling flag)
  - `chr_entries` — 19 rows (CHR-001 to CHR-019)
  - `benchmark_history` — 240 rows, daily gap_pp / days_active / over_indexed per issue type
  - `daily_runs` — 34 rows, pipeline run log. Fields as of 2026-04-19: run, date, status, failed_steps, new_records, findings, p0_count, p1_count, chr_anchor_top3, clark_tier_max, m1_streak, churn_risk_score, churn_risk_trend
  - `clark_log` — 231 rows, full escalation / downgrade history with Opus synthesis
  - `vault_log` — 31 rows, mirror of mil_vault.db anchor log
  - `commentary` — 4 rows, Sonnet analyst prose per issue per day
  - `unanchored_signals` — 322 rows from research_queue.jsonl (P0/P1 findings pending CHR governance)
- **Sensitivity analysis**: `mil/analytics/cac_sensitivity.py` — weight grid across 6 variants. MODERATE sensitivity (±3 CLARK-3 swing). Re-run at Day 60.
- **Google Play package IDs fixed (2026-04-17)**: Lloyds `com.grppl.android.shell.CMBlloydsTSB73`, Monzo `co.uk.getmondo` (old IDs returned 404)
- Query: `duckdb mil_analytics.db` from repo root

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
- Executive alert: self-intelligence framing ("YOUR APP"), **qwen3:14b** synthesis of P0 reviews (ARCH-002 implemented),
  conditional Chronicle match (keyword overlap >= 2), signal strength STRONG/MODERATE/EARLY SIGNAL
- **exec_alert import fix (2026-04-06)**: `_exec_alert_description()` uses try/except import fallback — `from mil.config.get_model import get_model` → `from config.get_model import get_model` when called via subprocess (publish.py sets mil/ on sys.path, not repo root)
- **clark_tier** added to executive_alert dict — sourced from clark_protocol.get_clark_tier_for_finding()
- **Chronicle matching (2026-04-10)**: `_chronicle_match_from_findings(anchored)` — driven by top Barclays finding's actual CHR anchor from mil_findings.json. CHR-004/017/018/019 preferred for Barclays (their own sustained friction patterns); falls back to highest-CAC match only if no Barclays CHR has representation.
- **Counter import fix (2026-04-10)**: `Counter` was missing from `collections` import — caused `NameError: _Counter` which silently emptied Box 1 quotes. Fixed: `from collections import Counter, defaultdict`.
- **Teacher selection (2026-04-12)**: `_teacher_from_findings()` selects by frequency — the CHR ID that appears most often across all Barclays findings. Within that CHR, the highest-CAC finding provides the teacher context. Prevents substring-frequency gaming that caused TSB to always win when CHR-001 keywords were too generic.
- **Box 3 redesign (2026-04-12)**: "Barclays Alert" layout — 4 sections: THE SITUATION (qwen3 signal synthesis) / THE LESSON (teacher CHR entry: bank name + year) / SEVERITY (Clark tier) / NEXT STEPS (YOUR CALL framing). Teacher-student framing: competitor banks teach Barclays, not compare them.
- Top quote selection: P0 first, P1 fallback, 40+ chars, prefer 60-200 chars
- Current output (2026-04-12):
  - Barclays sentiment: P0=8+, P1=3+, chronicle_id=CHR-004, both Box 1 quotes populated
  - Competitor ticker: NatWest worst, Barclays stable, HSBC now tracked

### Sonar Briefing — publish.py (V1, ACTIVELY MAINTAINED)
File: `mil/publish/publish.py`
- **V1 is live at cjipro.com/briefing** — actively maintained (not frozen)
- Box 1: Barclays sentiment + dual quote boxes (App Store/Google Play) + brand lines + version pills
- Box 2: Issues Status — Barclays issue_type counts, trend, P0/P1, direct quote
- Box 3: **Barclays Alert** — 4-section layout: THE SITUATION / THE LESSON / SEVERITY / NEXT STEPS. Teacher-student framing. Dynamic teacher from sim_hist_score.
- All three boxes Barclays-scoped
- **Two-color score rule (2026-04-12)**: `score_num_color()` — red (#cc3333) below 50, white (#E8F4FA) ≥50. Applied to ALL sentiment score numbers (Box 1, ticker, journey rows, Box 2 list). RAG system (`score_color()`) still used for arrows and status text labels.
- **HSBC app IDs fixed (2026-04-12)**: App Store ID corrected to `1220329065`, Google Play package corrected to `uk.co.hsbc.hsbcukmobilebanking`. Both returning records from 2026-04-12 run.
- Note: cjipro.com behind Cloudflare — cache purge needed after deploy if changes not visible

### Sonar Briefing V2 — publish_v2.py (LIVE)
File: `mil/publish/publish_v2.py`
- **V2 LIVE** at cjipro.com/briefing-v2 (2026-04-05)
- Loads V1 HTML from mil/publish/output/index.html, injects V2 sections before `</body>`
- V2 sections (all use `.topbar-box` chrome — same width/mobile behaviour as Box 1/2/3):
  - **Vane Trajectory** — 14-day Plotly chart, App Store + Google Play, all competitors. Plotly CDN injected into V2 HTML (not in V1).
  - **Intelligence Findings** — top 10 Barclays findings by CAC, with tier/severity/chronicle/ceiling badges. Barclays-scoped only.
  - **Clark Protocol** — Barclays-only escalation status, tier strip + active finding rows. Barclays-scoped only.
  - **Phase 2 Demand** — ceiling finding list, request counter, by-competitor pills
- Local copy: mil/publish/output/index_v2.html
- Run: `py mil/publish/publish_v2.py`
- **publish_v2.py wired into run_daily.py as Step 5b** (after V1 publish, before log run)
- **Clark race condition fix (2026-04-12)**: `scan_and_escalate()` / `scan_and_downgrade()` REMOVED from publish_v2.py. V2 reads pre-escalated clark_log only. Escalation now runs as dedicated Step 4c in run_daily.py (before both publish steps). Eliminates CLARK-0 appearing in HTML because escalation happened after V1 publish.

### Sonar Briefing V3 — publish_v3.py (LIVE 2026-04-12, refined 2026-04-13)
File: `mil/publish/publish_v3.py`
- **V3 LIVE** at cjipro.com/briefing-v3
- Loads V1 HTML from mil/publish/output/index.html. Strips V1 Box 3 (exec-alert-panel) via `_replace_box3()` (div-depth counter). Injects V3 Intelligence Brief in Box 3 slot. V1 + V2 untouched.
- **Box 3 — Intelligence Brief** (`_build_exec_summary_box`):
  - THE SITUATION: full Sonnet prose from top risk commentary box (latest reviews, not Chronicle)
  - Real P0/P1 review quote (between Situation and Peer)
  - PEER COMPARISON: deterministic prose — Barclays rate, 5-bank peer avg, gap, best-performing peer named explicitly, days sustained, under-indexed strength note
  - THE CALL: one sentence from `call_map[clark_tier]` — Clark-3=escalate today, Clark-2=this week, Clark-1=watch, Clark-0=nominal
  - Thin `#003A5C` divider between each section (Option A — no section numbers)
  - Clark tier badge at foot
- V3 intelligence sections (below fold):
  - **Churn Risk Score** — composite score, trend badge, over/under-indexed pills
  - **Analyst Commentary** — Sonnet 3-sentence structure per issue (Sentence 1: issue/duration/severity. Sentence 2: root cause inference. Sentence 3: business risk). 3 risk + 1 strength. All 4 cards show a real P0/P1 review quote (strength cards added 2026-04-13).
  - **Technical Benchmark** — 6 issue types, bar chart, gap, days active
  - **Service Benchmark** — 10 issue types, same format
  - **Intelligence Findings** — top 8 Barclays by CAC, badges
  - **Clark Protocol** — Barclays escalation status
- Local copy: mil/publish/output/index_v3.html
- Run: `py mil/publish/publish_v3.py`
- **publish_v3.py wired into run_daily.py as Step 5c** (after V2 publish, before log run)

### Sonar Briefing V4 — publish_v4.py (LIVE 2026-04-19, MIL-39)
File: `mil/publish/publish_v4.py` + `mil/publish/templates/briefing_v4.html.j2` + `mil/publish/templates/_benchmark_section.html.j2`
- **LIVE at cjipro.com/briefing-v4** — FCA Consumer Duty 2.0 parallel to V3.
- Same layout as V3 (Intelligence Brief / Churn Risk / Analyst Commentary / Technical + Service Benchmark / Intelligence Findings / Clark Protocol) plus **four-field Provenance Chain** rendered on every Inference Card: chronicle_id / signal_ids / class_ver / teacher_ver. Missing data renders as "—" (visible audit gap, not hidden absence).
- Jinja2-rendered (autoescape=False for f-string parity, StrictUndefined). Monkeypatches six section builders in `publish_v3` to route through the template, then delegates to `legacy.generate_v3_html` for non-section orchestration (V3_STYLES, `_replace_box3`, `_load_env`). Patches are scoped to the render; V3 is untouched.
- Parallel build rationale: same pattern as V1→V2→V3. Zero risk to live V3. Retire V3 only after V4 proves out (7+ clean days recommended).
- Structural diff gate: `py mil/publish/publish_v4.py --diff-gate` — renders V3 + V4 side-by-side from identical live data, asserts structural equivalence on every section (with provenance OFF on V4 for fair comparison), then separately validates all eight production cards render the four FCA fields. Exits 0 on full pass. No publish.
- Local-only render: `py mil/publish/publish_v4.py --render` — writes `mil/publish/output/index_v4.html`, skips GitHub push.
- Full publish: `py mil/publish/publish_v4.py` — build + local copy + push to `briefing-v4/index.html`.
- **publish_v4.py wired into run_daily.py as Step 5d** (after V3 publish, before log run). Treated as CRITICAL.
- **Upstream data gaps surfaced by Provenance Chain** (for Phase B follow-up, not blocking): `signal_ids` is empty on most findings (inference isn't recording anchoring signals); `teacher_model_version` is `None` across all 138 findings (enrichment doesn't stamp teacher model version into provenance).

### Daily Pipeline — ONE COMMAND (fully agentic)
```
py run_daily.py
```
Steps (zero human intervention required):
  1. Fetch — App Store + Google Play, all active competitors, dedup against existing
  2. Enrich — Claude Haiku schema v3, skip already-enriched v3 records (< 1 second if nothing new)
  3. Inference — mil_agent.py CAC + RAG, Chronicle matching, Designed Ceiling
  4a. Research Trigger — flags P0/P1 weak-anchor findings → mil/data/research_queue.jsonl
  4b. Vault — TCP preflight on port 9871, then vault_sync.py (skipped + warned if NameNode down)
  4c. Clark Escalation — scan_and_escalate() + scan_and_downgrade(), runs BEFORE both publish steps
  4d. Benchmark + Persistence — benchmark_engine.py, churn_risk_score + issue_persistence_log.jsonl
  4e. Analytics DB — build_analytics_db.py, full rebuild of mil_analytics.db (9 tables)
  4f. Drift Monitor — drift_monitor.py, Silent Wall detector (MIL-48). Alerts → drift_log.jsonl; HIGH → Slack.
  5. Publish — publish.py, briefing_data.py, GitHub Pages push -> cjipro.com/briefing
  5b. Publish V2 — publish_v2.py, injects V2 sections, GitHub Pages push -> cjipro.com/briefing-v2
  5c. Publish V3 — publish_v3.py, commentary_engine.py (Sonnet), saves commentary_log.jsonl, cjipro.com/briefing-v3
  5d. Publish V4 — publish_v4.py, Jinja2-rendered V3 + FCA Provenance Chain, cjipro.com/briefing-v4 (MIL-39)
  6. Log Run — appends to mil/data/daily_run_log.jsonl, status=CLEAN/PARTIAL/FAILED + failed_steps[]

Flags:
  `--dry-run`    fetch + enrich only, skip inference + publish
  `--skip-fetch` skip fetch + enrich, re-run inference + publish only

Human is ONLY required for: governance review (CHR entries), M2 countersign, Jira ticket closure.

### MIL Jira — Kanban Board

**Phase 0 — ALL BUILT + CLOSED**
**Phase 1 — ALL BUILT (2026-04-05, pending Hussain Jira closure)**
**Phase 2 — ALL BUILT (2026-04-16, pending Hussain Jira closure)**

| Ticket | Component | Status |
|--------|-----------|--------|
| MIL-1 to MIL-10 | Phase 0 full stack | BUILT + CLOSED |
| MIL-11 | model_routing.yaml + get_model() | BUILT 2026-04-05 |
| MIL-12 | vane_chart.py — 14-day Plotly | BUILT 2026-04-05 |
| MIL-13 | inference_cards.py — top-N by CAC | BUILT 2026-04-05 |
| MIL-14 | clark_protocol.py + scheduler 06:30 UTC | BUILT 2026-04-05 |
| MIL-15 | exit_strategy.py + click_log.jsonl | BUILT 2026-04-05 |
| MIL-16 | Teacher autopsies — 4 × CHR, 550 pairs | BUILT 2026-04-04 |
| MIL-17 | collect_downdetector.py (0.95 trust) | BUILT 2026-04-04 |
| MIL-18 | collect_cityam.py — City A.M. + FT RSS | BUILT 2026-04-04 |
| MIL-19 | collect_reddit.py — public JSON, no OAuth | BUILT 2026-04-04 |
| MIL-20 | Trustpilot | DEFERRED — legal risk, re-evaluate Day 60 |
| MIL-21 | Facebook | EXCLUDED — poor ROI |
| MIL-22 | collect_youtube.py (0.75 trust) | BUILT 2026-04-03 |
| MIL-23 | Twitter/X | EXCLUDED — cost prohibitive |
| MIL-24 | Glassdoor | EXCLUDED — out of MIL scope |
| MIL-26 | ARCH-003 model routing (schema v1.1) | BUILT 2026-04-12 |
| MIL-27 | benchmark_engine.py + issue_persistence_log.jsonl | BUILT 2026-04-12 |
| MIL-28 | commentary_engine.py (Sonnet prose) | BUILT 2026-04-12 |
| MIL-29 | publish_v3.py — cjipro.com/briefing-v3 | BUILT 2026-04-12 |
| MIL-30 | Opus governance — CLARK-3 synthesis + CHR proposals | BUILT 2026-04-12 |
| MIL-31 | Barclays CHRONICLE depth — CHR-017/018/019, --force flag | BUILT 2026-04-16 |

**Source Stack (6 active):**
| Source | Trust Weight | Status |
|--------|-------------|--------|
| App Store | 0.90 | LIVE |
| Google Play | 0.90 | LIVE |
| DownDetector | 0.95 | LIVE (MIL-17) |
| City A.M. | 0.90 | LIVE (MIL-18) |
| Reddit | 0.85 | LIVE (MIL-19) |
| YouTube | 0.75 | LIVE (MIL-22) |

**Next ticket: MIL-39**

### MIL-31 — Barclays CHRONICLE Depth (BUILT 2026-04-16)
- CHR-017/018/019 approved — Barclays J_SERVICE_01 journey now fully anchored
- research_agent.py `--force` flag added — bypasses CHR_COVERAGE skip for manual override
- CHR_COVERAGE registry expanded: CHR-001 through CHR-019 reserved
- 116 Barclays findings previously unanchored — now anchored to CHR-017/018/019
- Commit: `feat(MIL-31): Barclays CHRONICLE depth — CHR-017/018/019 approved`

### MIL-26 — ARCH-003 Model Routing (BUILT 2026-04-12)
File: `mil/config/model_routing.yaml` (schema v1.1)
- Four-tier routing: Opus (governance), Sonnet (daily intelligence), Haiku/Refuel-8B (classification), Qwen3 (labour)
- New routes: chr_proposal (Opus), teacher_autopsy (Opus), clark_escalation_synthesis (Opus), exec_alert_v3 (Sonnet), commentary (Sonnet), churn_narrative (Sonnet)
- Always use `get_model(task)` — never hardcode model names

### MIL-27 — Benchmark Engine + Persistence Log (BUILT 2026-04-12, hardened 2026-04-18)
File: `mil/data/benchmark_engine.py`
- Full competitive benchmarking: 6 competitors, 6 technical + 10 service issue types
- Complaint-normalised rates: denominator = total records − Positive Feedback − Other
- **90-day rolling window (2026-04-18)**: `BENCHMARK_WINDOW_DAYS=90` — replaces all-time corpus. `load_competitor_records()` accepts `min_date` param. Zero-record peers excluded from peer averages.
- **Incumbent/neobank split (2026-04-18)**: `INCUMBENT_PEERS` = [barclays, natwest, lloyds, hsbc]; `NEOBANK_PEERS` = [monzo, revolut]. Benchmark returns `incumbent_avg` and `neobank_avg` in addition to overall peer avg.
- **Churn score normalised 0-100 (2026-04-18)**: `CHURN_SCORE_CAP=180`. Raw score divided by cap, capped at 100. Returns `churn_risk_score` (normalised) + `churn_risk_score_raw`.
- **Streak carry-forward (2026-04-18, corrected 2026-04-18)**: `STREAK_GAP_TOLERANCE=2` — gap ≤ 2 pipeline days continues streak without resetting. Bug fixed: silent gap days no longer added to `days_active` (was inflating churn score on weekends/skip-fetch days). Streak continues but only active signal days count.
- **Trend: scipy linregress (2026-04-18)**: 14-point slope over benchmark_history. slope >1.0 = WORSENING, <-1.0 = IMPROVING. Requires 14+ prior dates; falls back to STABLE. Replaces 3d vs 4d mean split.
- `run(mode="daily")` returns: churn_risk_score, churn_risk_score_raw, churn_risk_trend, over_indexed, under_indexed, benchmark dict
- `run(mode="backfill")` — processes all dates from daily_run_log.jsonl, builds full history
- Writes: mil/data/benchmark_cache.json (fresh each run) + mil/data/issue_persistence_log.jsonl (appends)
- **Current: churn_risk_score=49.2 (raw=88.63) trend=WORSENING, 7 over-indexed, 7 under-indexed (2026-04-18)**
- **Step 4d** in run_daily.py (after Clark, before Publish)

### MIL-28 — Commentary Engine (BUILT 2026-04-12, refined 2026-04-13/18)
File: `mil/publish/commentary_engine.py`
- Reads issue_persistence_log.jsonl, selects significant Barclays issues
- Risk selection: gap>5pp OR (days>3 AND gap>0) OR P0/P1. Strength: gap<-3pp
- Calls Sonnet (commentary route, 300 tokens) per issue — analyst prose, enforced 3-sentence structure:
  - Sentence 1: introduce issue — what it is, how long active, severity class (factual orientation)
  - Sentence 2: root cause inference — what customer evidence rules out, what it points to
  - Sentence 3: business risk — churn, regulatory, or reputational consequence if unresolved
- CHR resonance: conditional Chronicle context for 6 issue types (App Not Opening, Login Failed, Account Locked, App Crashing, Incorrect Balance, Missing Transaction)
- Top quotes: P0/P1 priority, 40-200 chars. **Both risk AND strength cards fetch quotes** (strength fix 2026-04-13)
- **Prompt versioning (2026-04-18)**: `prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]` stored in every result dict. `model` also stored. Enables drift detection across daily runs.
- Max output: 3 risk boxes + 1 strength box = 4 total
- Fallback prose if Sonnet unavailable
- Called by publish_v3.py on each daily run

### MIL-29 — Briefing V3 (BUILT 2026-04-12, refined 2026-04-13)
File: `mil/publish/publish_v3.py`
- **LIVE at cjipro.com/briefing-v3**
- Strips V1 Box 3, injects Intelligence Brief (prose-only, 3 sections + quote + Clark badge)
- Below fold: Churn Risk Score / Analyst Commentary / Technical Benchmark / Service Benchmark / Intelligence Findings / Clark Protocol
- Local copy: mil/publish/output/index_v3.html
- **Step 5c** in run_daily.py

### MIL-30 — Opus Governance Tier (BUILT 2026-04-12)
- **clark_protocol.py**: `_opus_synthesis()` called on every new CLARK-3 escalation
  - Calls Opus (clark_escalation_synthesis route) — 4-sentence structured note: what/why now/evidence/recommended action
  - `synthesis` field added to clark_log.jsonl entry. Non-fatal if Opus fails.
- **research_agent.py**: CHR proposal drafting upgraded Haiku → Opus (chr_proposal route)
  - CHR entries anchor CAC formula permanently — Opus quality non-negotiable

### Domain Taxonomy (MIL-32 — BUILT 2026-04-19)
File: `mil/config/domain_taxonomy.yaml` + `mil/config/taxonomy_loader.py`
- Single source of truth for all taxonomy. Never hardcode issue types, journeys, or severity gate in pipeline files.
- 16 enrichment issue types with `max_severity` (P0/P1/P2) + `category` (technical/service/other) + `enrichment` flag
- 9 customer journeys. 30-key journey_map (v3 + v2 legacy). exclude_from_rates list.
- `taxonomy_loader.py`: typed accessors with `@lru_cache`. Key functions: `issue_types()`, `customer_journeys()`, `apply_severity_gate(issue, sev)`, `journey_map()`, `technical_issues()`, `service_issues()`.
- Backslash bug in `"Biometric \ Face ID Issue"` fixed — forward slash canonical in YAML.
- Clone operators update domain_taxonomy.yaml to swap taxonomy for their domain — no code changes required.

### Circuit Breaker — Commentary (MIL-33 — BUILT 2026-04-19)
File: `mil/config/model_client.py` + `mil/publish/commentary_engine.py` + `mil/publish/publish_v3.py`
- `CircuitBreakerError` in model_client.py. `_failure_counts` dict tracks consecutive failures per task per process run. Threshold=3. Resets to 0 on success.
- commentary_engine.py catches `CircuitBreakerError` → loads cached commentary from `commentary_log.jsonl` (most recent prior date) → returns with `cached: True` flag.
- publish_v3.py renders amber `⚠ CACHED` badge on affected commentary cards.
- Autonomous run behaviour: Sonnet down → 3 failures → breaker trips → cached boxes published → run status PARTIAL not FAILED.

### model_client.py — Unified LLM Wrapper (hardened 2026-04-18, circuit breaker 2026-04-19)
File: `mil/config/model_client.py`
- **Prompt caching (2026-04-18)**: `cache_system: bool = False` param. When enabled and system prompt ≥ 4000 chars (`_CACHE_MIN_CHARS`), wraps as `[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]`. Use for long static system prompts (CHR synthesis, teacher autopsies).
- **Token usage logging (2026-04-18)**: every call logs `in={X} out={Y} cache_read={Z} cache_create={W}` at INFO level for cost tracking.
- Exponential backoff: `2 ** attempt` seconds, `max_retries` from thresholds.yaml
- Trace ID on every call: `uuid.uuid4().hex[:8]` or caller-supplied `trace_id`

### Enrichment Quality Scaffold (2026-04-18)
File: `mil/tests/enrichment_spot_check.py`
- Monthly manual accuracy check — samples N records (default 50), writes `spot_check_YYYY-MM-DD.json` with blank human label fields
- `--sample [N]`: generate sample file. `--score FILE`: compute accuracy from completed file, appends to `mil/data/enrichment_accuracy_log.jsonl`
- Targets: issue_type >85%, severity_class >90%. Exits code 1 if below targets.
- Run: `py mil/tests/enrichment_spot_check.py --sample 50`

### Pre-Autonomy Hardening — Phase 0+1 (2026-04-18)

New files:
- `mil/inference/cac.py` — `compute_cac()` + `compute_vol_sig()` extracted from mil_agent.py. Independently testable.
- `mil/inference/rag.py` — `find_best_chronicle_match()` + embedding cache extracted from mil_agent.py. Takes `chronicle_entries` as explicit param.
- `mil/tests/test_rag.py` — 12 tests for RAG layer (keyword overlap + find_best_chronicle_match). All passing.
- `mil/data/calibration_notes.md` — fortnightly retrospective log. First entry 2026-04-18: CHR spread confirmed, churn normalization break documented.

Fixes applied:
- `benchmark_engine.py`: streak gap bug — silent gap days no longer added to `days_active` (was inflating churn score)
- `chronicle_loader.py`: CRLF regex fix, WARNING on malformed YAML blocks, RuntimeError if <15 entries load
- `run_daily.py`: silent `except: pass` in fetch dedup loop now logs context; run log enriched with p0_count, p1_count, chr_anchor_top3, clark_tier_max
- `test_cac.py`: rewritten to import from cac.py (was testing an inline copy of the formula)

CHR distribution check (Run #34): CHR-003 22%, CHR-002 18%, CHR-005 18% — no magnet. Spread healthy.
Churn score Run #35: 53.4 WORSENING (up from 49.2). 182 new records ingested.
Churn score normalization break: runs 1–32 unnormalized (77–107), run 33+ normalized 0–100. Anomaly threshold not valid until Run #47.
31 tests passing: `py -m pytest mil/tests/test_cac.py mil/tests/test_rag.py -v`

### Dependencies (updated 2026-04-18)
- `sentence-transformers>=2.7` added to requirements.txt + mil/requirements.txt — required for embedding RAG in mil_agent.py
- `unsloth` added to mil/requirements.txt — QLoRA fine-tuning library (MIL-25). Installed 2026-04-18: unsloth-2026.4.6, torch-2.11.0+cu128, peft-0.19.1, trl-0.24.0, bitsandbytes-0.49.2, xformers-0.0.35
- **CUDA Toolkit 13.2** installed via winget (Nvidia.CUDA) — required by triton for nvcc. Requires system restart to activate PATH. PyTorch uses bundled CUDA 12.8 runtime; toolkit 13.2 is for triton kernel compilation only.

### MIL Research Agent — (MIL-26 component, BUILT 2026-04-09, upgraded MIL-30)
File: `mil/researcher/research_agent.py`
- Reads `mil/data/research_queue.jsonl` (116 Barclays findings now anchored — 2026-04-16)
- Clusters by competitor + journey_id
- Calls **Opus** to draft proposed CHRONICLE entries per cluster (upgraded from Haiku — MIL-30)
- `CHR_COVERAGE` registry: CHR-001 through CHR-019 reserved. Skips covered clusters by default.
- `--force` flag: bypasses CHR_COVERAGE skip — use when existing CHR entries don't cover a competitor's journey (e.g. Barclays J_SERVICE_01 had no anchor before CHR-017/018/019)
- Writes proposals to `mil/data/chr_proposals/<competitor>_<journey>_<timestamp>.md`
- Writes summary to `mil/data/chr_proposals/summary_<timestamp>.md`
- Run: `py mil/researcher/research_agent.py`
- Flags: `--dry-run` (cluster report only), `--competitor <name>` (filter), `--force` (bypass coverage skip)

### MIL-25 — QLoRA Gate Clearance (COMPLETE 2026-04-19)
Specialist stack: `mil/specialist/`

| Gate | Condition | Status |
|------|-----------|--------|
| 1 | 14+ days real signal data | PASS — 16 run days confirmed 2026-04-19 |
| 2 | Synthetic pairs validated (human) | PASS — countersigned by Hussain 2026-04-05 |
| 3 | CAC weights approved on real corpus | PASS — retained, approved by Hussain 2026-04-05 |
| 4 | Adversarial Attacker passes evaluation | PASS — 80% survival rate on high-CAC findings |
| 5 | Collision Lock ACTIVE | PASS — post-training P0=90% P1=100% overall=95% (2026-04-19) |

**Trained model:** `mil/specialist/qwen3-mil-v1-4b/` — Qwen3-4B, 600 pairs (450 CAC + 150 severity), 3 epochs, loss=2.293
- **Why 4B not 8B**: RTX 5070 Ti Blackwell (sm_120) has bitsandbytes instability at 8B 4-bit. 4B stable at 9GB VRAM.
- `mil/specialist/build_severity_pairs.py` — generates 150 severity calibration pairs from Haiku corpus (60 P0, 60 P1, 30 P2)
- `mil/teacher/output/severity_pairs.jsonl` — severity training pairs (used alongside synthetic_pairs.jsonl)
- `mil/specialist/train_qwen.py` — `--resume` flag added; loads both pair files; Qwen3-4B base
- `mil/specialist/collision_lock.py` — tests fine-tuned LoRA adapter directly via unsloth (not Ollama base); dual-format JSON + inline CAC text parser

**Wiring status (2026-04-19):** `specialist_severity` route **declared** in model_routing.yaml (ARCH-005). `get_model("specialist_severity")` resolves to `qwen3-mil-v1:latest` on Ollama, but **not live** — LoRA adapter hasn't been merged to GGUF and Ollama doesn't yet serve the model. Path to live: (a) merge LoRA + GGUF quantise, (b) `ollama create qwen3-mil-v1 -f Modelfile`, (c) held-out eval vs qwen3:14b enrichment baseline, (d) manual spot-check, (e) flip `status: declared` → `status: live` in model_routing.yaml. Collision lock re-run required post any retraining.

### Day 30 Success Metrics — ALL DONE (2026-04-05)
- **M1**: DONE — streak 19/5 as of 2026-04-19. Run #35 logged. Tracker: mil/data/daily_run_log.jsonl
- **M2**: DONE — NatWest MIL-F-20260402-047, CAC=0.652, CHR-001, countersigned 2026-04-02
- **M3**: DONE — 34 ceiling triggers (threshold was 22). Now 7 ceiling with 90-day window (stale all-time volume removed)

### Clark Protocol — First Scan (2026-04-05)
- 2x CLARK-3 (NatWest — ACT NOW)
- 1x CLARK-2 (Barclays — ESCALATE)
- 3x CLARK-1 (Lloyds, Monzo, NatWest — WATCH)
- Log: mil/data/clark_log.jsonl

### Pending Human Actions (Hussain)
- Close MIL-11 through MIL-31 in Jira UI
- **Apr 19 DONE**: Gate 1 cleared. Collision lock ACTIVE (P0=90%, P1=100%). Qwen3-4B trained (qwen3-mil-v1-4b). Run #35 clean, streak 19/5. MIL-32/33/34/37/38 all BUILT. Slack notification layer LIVE. Golden HTML snapshot locked for MIL-39.
- **Apr 20 autonomy HELD** (panel-reviewed decision): tighten every screw first. Use Apr 20–27 for MIL-39 (Jinja2), MIL-35 (publish adapter), MIL-36 (vault backend), held-out eval of qwen3-mil-v1-4b, calibration baseline, drift detection, 3 consecutive clean manual runs.
- **Apr 28–30 (revised autonomy target)**: qwen3-mil-v1-4b now declared in model_routing.yaml (ARCH-005, `specialist_severity` route). Remaining before live: GGUF quantise → `ollama create` → held-out eval vs qwen3:14b baseline → flip `status: declared` → `status: live`. Then schedule `run_daily.py` via cron (06:30 UTC). MIL runs without human intervention from this date. Pivot focus to CJI Pulse.
- **Fortnightly calibration**: Fill in `mil/data/calibration_notes.md` — check 3 prior Clark findings against observable outcomes. Next due 2026-05-02. Anomaly alert threshold to be set after Run #47 (14+ normalized churn scores accumulated).
- **Monthly**: Run `py mil/tests/enrichment_spot_check.py --sample 50`, label file, score with `--score`
- CHR-003: confirm HSBC root cause if source becomes available
- Cloudflare: purge cache after each briefing deploy if changes not visible
- **CJI Pulse PULSE-11 unblock**: populate 6 pending tables in data_dictionary_master.yaml — critical path to Day 90 vision

## MIL — Market Intelligence Layer

### What MIL Is

Sovereign Early Warning System built on 100% public market signals. Air-gapped from internal systems. Monitors 6 competitor apps (NatWest, Lloyds, HSBC, Monzo, Revolut, Barclays) across 6 signal sources: App Store (live), Google Play (live), DownDetector (MIL-17), City A.M. (MIL-18), Reddit (MIL-19), YouTube (MIL-22). Three sources evaluated and excluded: Facebook (poor ROI), Twitter/X (cost prohibitive), Glassdoor (wrong domain). One deferred: Trustpilot (legal risk). One deferred: FT (paywall).
**Current corpus: 7,570 enriched records. 138 findings | 100% anchored | 7 Designed Ceiling. All Day 30 metrics achieved 2026-04-05. CHRONICLE CHR-001 to CHR-019 auto-loaded via chronicle_loader.py. Embedding RAG live (all-MiniLM-L6-v2). CAC formula in cac.py, RAG layer in rag.py (both independently tested). Benchmark on 90-day rolling window. Churn score 53.4 WORSENING (Run #35). Normalization introduced Run #33; anomaly threshold valid from Run #47. Run #35, streak 19/5, 2026-04-19. QLoRA complete — qwen3-mil-v1-4b Gate 5 ACTIVE. MIL goes autonomous 2026-04-20.**

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

### MIL Model Routing — Updated 2026-04-05

Config: `mil/config/model_routing.yaml` + `mil/config/get_model.py` (MIL-11)
Use `get_model(task)` everywhere — never hardcode model names.

- **Refuel-8B (local):** Signal classification, journey attribution, MIL inference (CAC + RAG), Adversarial Attacker — `michaelborck/refuled:latest` at `http://127.0.0.1:11434/v1`
- **Qwen3 (local, default):** YAML/Markdown generation, narrative generation, non-inference scripting — `qwen3:14b` at `http://127.0.0.1:11434`
- **Qwen3 (local):** Executive alert synthesis (Box 3) — `qwen3:14b` at `http://127.0.0.1:11434`. ARCH-002 approved. **LIVE** in briefing_data.py `_exec_alert_description()`.
- **Haiku (Claude API):** Enrichment ONLY — `claude-haiku-4-5-20251001`. Retained per ARCH-002. P0 severity accuracy critical.
- **Sonnet (Claude API):** Teacher autopsies only — deep causal analysis + synthetic pair generation
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
| `mil/CHRONICLE.md` | **MIL banking failure ledger** — CHR-001 TSB 2018, CHR-002 Lloyds 2025, CHR-003 HSBC 2025, CHR-004 Barclays 2026, CHR-005 to CHR-016 competitor incidents (2026-04-16), CHR-017/018/019 Barclays J_SERVICE_01 depth (2026-04-16), ARCH-001, ARCH-002 |

## Model Routing — Updated 2026-04-05

**MIL inference routes to Refuel-8B. Enrichment on Haiku (ARCH-002). Exec alert (Box 3) on qwen3:14b — LIVE (MIL-11). Routing config in mil/config/model_routing.yaml. Always use get_model(task). Conserve Sonnet tokens.**

**DEFAULT: Qwen3** (qwen3:14b at http://127.0.0.1:11434)

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
