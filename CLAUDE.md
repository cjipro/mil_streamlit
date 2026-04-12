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
- V1 at cjipro.com/briefing FROZEN — never touch
- V2 extends V1 with: Vane Trajectory Chart (MIL-12), Inference Cards (MIL-13), Clark Protocol (MIL-14), Phase 2 Demand (MIL-15)
- All V2 sections use `.topbar-box` chrome — same width/padding as Box 1/2/3, mobile-optimised

**Next ticket: MIL-27 (undefined)**

**Phase 2 — IN PROGRESS (2026-04-12)**
- MIL-25: QLoRA Gate Clearance — specialist stack built, 4/5 gates passed (BUILT 2026-04-05, Gate 1 pending ~2026-04-19)
- MIL-26: Research Agent — mil/researcher/research_agent.py, clusters research queue, drafts CHR proposals (BUILT 2026-04-09)

## MIL Pipeline State — 2026-04-12 (updated)

### Infrastructure
- **docker-compose.yml**: mil-namenode (port 9871) + mil-datanode (ports 9864/9866) LIVE
  - Zero Entanglement: MIL HDFS sovereign on 9871. CJI Pulse HDFS on 9870. Never shared.
  - WebHDFS 2-step PUT confirmed working: NameNode 9871 → DataNode 9864 redirect chain
  - HDFS volumes: C:/Users/hussa/hdfs-volumes/mil-namenode + mil-datanode
- **ARCH-001**: Qwen-14B decommissioned from MIL enrichment. Claude Haiku is now primary enrichment model.
- **ARCH-002**: qwen3:14b evaluated for enrichment (2026-04-03). 20-record blind test vs Haiku baseline: schema compliance 100%, issue_type agreement 90%, severity agreement 95%. DISQUALIFIED for enrichment — downgraded a P0 blocking issue to P2. P0 accuracy is non-negotiable for MIL. Haiku retained for enrichment. qwen3 approved for exec alert synthesis (Box 3) — **IMPLEMENTED 2026-04-05** in briefing_data.py via `_exec_alert_description()` using OpenAI-compat Ollama call + `get_model("exec_alert")`.

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
- Current state: **10/10 VAULTED** — all claude-haiku-4-5-20251001
  - app_store_barclays_enriched.json: VAULTED
  - app_store_lloyds_enriched.json: VAULTED
  - app_store_monzo_enriched.json: VAULTED
  - app_store_natwest_enriched.json: VAULTED (new — 2026-04-03)
  - app_store_revolut_enriched.json: VAULTED (new — 2026-04-03)
  - app_store_hsbc_enriched.json: VAULTED (new — 2026-04-12)
  - google_play_barclays_enriched.json: VAULTED
  - google_play_natwest_enriched.json: VAULTED
  - google_play_revolut_enriched.json: VAULTED
  - google_play_hsbc_enriched.json: VAULTED (new — 2026-04-12)

### Inference Engine (mil_agent.py — MIL-8)
File: `mil/inference/mil_agent.py`
- CAC formula: C_mil = (alpha*Vol_sig + beta*Sim_hist) / (delta*Delta_tel + 1)
  - alpha=0.40, beta=0.40, delta=0.20 (not tuned before Day 30)
- RAG: keyword overlap against CHRONICLE entries (CHR-001/002 inference_approved only)
  - CHR-003: inference_approved=true (APPROVED — Hussain Ahmed 2026-04-09, confidence_score=0.55, root cause inferred: app platform refresh outage)
  - CHR-004: inference_approved=true (APPROVED — Hussain Ahmed 2026-04-02)
- Designed Ceiling: triggers when CAC > 0.45 AND delta_tel=0.0
  - Output: "To confirm this I require internal HDFS telemetry data. Request Phase 2."
- Refuel-8B called per finding for blind_spots + narrative + failure_mode
- Deterministic fallback if Refuel unavailable (Article Zero compliant)
- issue_type (v3) -> journey_id mapping in JOURNEY_MAP (updated from v2 journey_category)
- Current findings: **135 total** | 135 anchored | 0 unanchored | 34+ Designed Ceiling (HSBC contributing ~20 new findings from 2026-04-12 run)
- **blind_spots fix**: Refuel-8B returns blind_spots as string; coerced to list on ingest (2026-04-05)

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
- **Chronicle matching (2026-04-10)**: `_chronicle_match_from_findings(anchored)` — driven by top Barclays finding's actual CHR anchor from mil_findings.json. CHR-004 preferred for Barclays (their own sustained friction pattern); falls back to highest-CAC match only if CHR-004 has no representation.
- **Counter import fix (2026-04-10)**: `Counter` was missing from `collections` import — caused `NameError: _Counter` which silently emptied Box 1 quotes. Fixed: `from collections import Counter, defaultdict`.
- **Teacher selection (2026-04-12)**: `_teacher_from_findings()` now selects by `chronicle_match.sim_hist_score` (keyword overlap between signal keywords and CHR `pattern_keywords`) — NOT by confidence/CAC. TSB (CHR-001) wins at sim=1.00 because Barclays' Feature Broken keywords most closely match CHR-001 pattern keywords. Other CHR entries win when their keywords match the active signal better.
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
  4c. Clark Escalation — scan_and_escalate() + scan_and_downgrade(), runs BEFORE both publish steps
  5. Publish — publish.py, briefing_data.py, GitHub Pages push -> cjipro.com/briefing
  5b. Publish V2 — publish_v2.py, injects V2 sections, GitHub Pages push -> cjipro.com/briefing-v2
  6. Log Run — appends to mil/data/daily_run_log.jsonl, reports M1 streak

Flags:
  `--dry-run`    fetch + enrich only, skip inference + publish
  `--skip-fetch` skip fetch + enrich, re-run inference + publish only

Human is ONLY required for: governance review (CHR entries), M2 countersign, Jira ticket closure.

### MIL Jira — Kanban Board

**Phase 0 — ALL BUILT + CLOSED**
**Phase 1 — ALL BUILT (2026-04-05, pending Hussain Jira closure)**

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

**Source Stack (6 active):**
| Source | Trust Weight | Status |
|--------|-------------|--------|
| App Store | 0.90 | LIVE |
| Google Play | 0.90 | LIVE |
| DownDetector | 0.95 | LIVE (MIL-17) |
| City A.M. | 0.90 | LIVE (MIL-18) |
| Reddit | 0.85 | LIVE (MIL-19) |
| YouTube | 0.75 | LIVE (MIL-22) |

**Next ticket: MIL-27 (undefined)**

### MIL-26 — Research Agent (BUILT 2026-04-09)
File: `mil/researcher/research_agent.py`
- Reads `mil/data/research_queue.jsonl` (78 PENDING items across 10 clusters)
- Clusters by competitor + journey_id
- Calls Haiku to draft proposed CHRONICLE entries per cluster
- Skips clusters already covered by existing CHR entries (e.g. Barclays covered by CHR-004)
- Writes proposals to `mil/data/chr_proposals/<competitor>_<journey>_<timestamp>.md`
- Writes summary to `mil/data/chr_proposals/summary_<timestamp>.md`
- Run: `py mil/researcher/research_agent.py`
- Flags: `--dry-run` (cluster report only), `--competitor <name>` (filter)

### MIL-25 — QLoRA Gate Clearance (BUILT 2026-04-05)
Specialist stack: `mil/specialist/`

| Gate | Condition | Status |
|------|-----------|--------|
| 1 | 14+ days real signal data | PENDING — 12/14 days, clears ~2026-04-19 |
| 2 | Synthetic pairs validated (human) | PASS — countersigned by Hussain 2026-04-05 |
| 3 | CAC weights approved on real corpus | PASS — retained, approved by Hussain 2026-04-05 |
| 4 | Adversarial Attacker passes evaluation | PASS — 80% survival rate on high-CAC findings |
| 5 | Collision Lock baseline recorded | PASS — pre-training LOCKED documented |

- `mil/specialist/adversarial_attacker.py` — Gate 4: stress-tests high-CAC findings via Refuel-8B. Pass = >=80% survival.
- `mil/specialist/collision_lock.py` — Gate 5: Haiku vs qwen3 P0/P1 agreement check. Pre-training LOCKED expected. Re-run post-training to confirm ACTIVE.
- `mil/specialist/cac_calibrator.py` — Gate 3: CAC weight analysis on real corpus. RETAIN confirmed (100% chr match, 37.7% ceiling rate). `--approve` records human sign-off.
- `mil/specialist/validate_pairs.py` — Gate 2: side-by-side synthetic pair vs real finding review. `--sign` records countersignature.
- `mil/specialist/train_qwen.py` — entry point: gate check + QLoRA training. Run `--check` to see gate status. Training only executes when all 5 pass.

Gate check: `py mil/specialist/train_qwen.py --check`
Post Gate 1 (~2026-04-19): re-run collision_lock.py then execute training.

### Day 30 Success Metrics — ALL DONE (2026-04-05)
- **M1**: DONE — streak now 11/5 as of 2026-04-12. Run #21 logged. Tracker: mil/data/daily_run_log.jsonl
- **M2**: DONE — NatWest MIL-F-20260402-047, CAC=0.652, CHR-001, countersigned 2026-04-02
- **M3**: DONE — 34 ceiling triggers (threshold was 22)

### Clark Protocol — First Scan (2026-04-05)
- 2x CLARK-3 (NatWest — ACT NOW)
- 1x CLARK-2 (Barclays — ESCALATE)
- 3x CLARK-1 (Lloyds, Monzo, NatWest — WATCH)
- Log: mil/data/clark_log.jsonl

### Pending Human Actions (Hussain)
- Close MIL-11 through MIL-26 in Jira UI
- Keep running `py run_daily.py` daily — Gate 1 clears ~2026-04-19
- Post Gate 1: `py mil/specialist/collision_lock.py` then `py mil/specialist/train_qwen.py`
- Run research agent: `py mil/researcher/research_agent.py` — review proposals in mil/data/chr_proposals/
- CHR-003: confirm HSBC root cause if source becomes available
- Cloudflare: purge cache after each briefing deploy if changes not visible

## MIL — Market Intelligence Layer

### What MIL Is

Sovereign Early Warning System built on 100% public market signals. Air-gapped from internal systems. Monitors 6 competitor apps (NatWest, Lloyds, HSBC, Monzo, Revolut, Barclays) across 6 signal sources: App Store (live), Google Play (live), DownDetector (MIL-17), City A.M. (MIL-18), Reddit (MIL-19), YouTube (MIL-22). Three sources evaluated and excluded: Facebook (poor ROI), Twitter/X (cost prohibitive), Glassdoor (wrong domain). One deferred: Trustpilot (legal risk). One deferred: FT (paywall).
**Current corpus: 4,000+ enriched records across 10 files (schema v3, claude-haiku-4-5-20251001). 135 findings | 34+ Designed Ceiling. All Day 30 metrics achieved 2026-04-05. HSBC now live (2026-04-12).**

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
| `mil/CHRONICLE.md` | **MIL banking failure ledger** — CHR-001 TSB 2018, CHR-002 Lloyds 2025, CHR-003 HSBC 2025, CHR-004 Barclays 2026, ARCH-001, ARCH-002 |

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
