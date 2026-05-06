# PULSE Jira Reconciliation — Codebase vs Board

**Ticket:** PULSE-84
**Generated:** 2026-05-06
**Scope:** PULSE-1 through PULSE-83
**Source-of-truth audit:** repo state + git log + manifest contents, cross-referenced against Jira summaries

## Summary

| State | Count | Note |
|---|---:|---|
| BUILT | 14 | Ready for closure in Jira UI |
| IN_PROGRESS | 3 | Partially shipped; should not close yet |
| NOT_STARTED | 60 | No code, no commit |
| BLOCKED | 4 | NOT_STARTED + dependent on data access |
| MISFILED (deferred) | 1 | PULSE-83 — kept as-is for repurposing later |
| DUPLICATE (decision pending) | 1 | PULSE-5 — held pending Hussain decision |
| DONE (already closed) | 2 | PULSE-16, PULSE-83 |

**Hussain decisions logged 2026-05-06:**
- **PULSE-5** — held pending; do not close yet.
- **PULSE-70** — domain intent satisfied by `cjipro.com`; close as BUILT.
- **PULSE-83** — keep as-is; context will be repurposed later. No reopen, no Won't Do action now.

---

## Per-ticket audit

| Key | Jira summary | Real state | Evidence | Proposed action |
|---|---|---|---|---|
| PULSE-1 | Initialise GitLab mono-repo | BUILT | GitHub `cjipro/mil_streamlit` + GitLab mirror `streaming-analytics/while-sleeping` (CLAUDE.md) | Close in UI |
| PULSE-2 | Living Data Dictionary v2.0 | IN_PROGRESS | `manifests/data_dictionary_master.yaml` v2.0; 17 of 23 tables populated, 6 pending data access; validator `scripts/validate_KAN-011.py` | Hold; complete pending tables |
| PULSE-3 | Data Strategy v2.0 | BUILT | `manifests/data_strategy_v2.md`, commit `846a306` | Close in UI |
| PULSE-4 | Governance Principles | BUILT | `manifests/governance_principles.yaml` (21 principles), commit `ba19e96`; validator `scripts/validate_principles.py` | Close in UI |
| PULSE-5 | Master Data Dictionary | DUPLICATE (decision held) | Same artefact as PULSE-2 (`manifests/data_dictionary_master.yaml`) | **Hussain 2026-05-06: hold; do not close** |
| PULSE-6 | Human Data Dictionary | NOT_STARTED | No `data_dictionary_human.yaml` in repo (specced in `data_strategy_v2.md`, not generated) | Leave To Do |
| PULSE-7 | Agentic Data Dictionary | NOT_STARTED | No `data_dictionary_agentic.yaml` in repo | Leave To Do |
| PULSE-8 | Register DPIA | NOT_STARTED | REG-001 still open per data_strategy_v2.md | Leave To Do |
| PULSE-9 | Audit Customer_Profile_Dim for special category data | BLOCKED | CPD access pending (REG-002); per `data_dictionary_master.yaml:2905` | Leave To Do; add `blocked` label |
| PULSE-10 | Publish vulnerability data processing statement | NOT_STARTED | No public notice published | Leave To Do |
| PULSE-11 | Publish customer rights statement and legal basis for derived fields | NOT_STARTED | No public notice published | Leave To Do |
| PULSE-12 | Set up local Docker environment | BUILT | `docker-compose.yml` with postgresql + pyspark-jupyter + streamlit + ollama; validator `scripts/validate_KAN-012.py` | Close in UI |
| PULSE-13 | Document all audit findings in structured YAML | BUILT | `manifests/audit_findings.yaml`, commit `fe492e2`; validator `scripts/validate_KAN-013.py` | Close in UI |
| PULSE-14 | Resolve Finding 002 — app version / experience source | BUILT | AF-002 = RESOLVED in `manifests/audit_findings.yaml`; DADTL.applicationversion confirmed source, 60–79% coverage | Close in UI |
| PULSE-15 | Audit CUST_DIM — describe, sample, join key confirmation | BLOCKED | Data access pending | Leave To Do; add `blocked` label |
| PULSE-16 | Create all 90-day epics and tickets in Jira | DONE | Already closed | (no action) |
| PULSE-17 | Scaffold system_manifest.yaml — complete schema with all v5 fields | BUILT (with bug) | `manifests/system_manifest.yaml`, commit `377a4be`; validator `scripts/validate_KAN-017.py`. **Has YAML parse error at line 850** (list under dict) | Close in UI; file new bug ticket for parse error |
| PULSE-18 | Build build_from_manifest.py | BUILT | `scripts/build_from_manifest.py`; validator `scripts/validate_KAN-018.py` | Close in UI |
| PULSE-19 | Define semantic telemetry spec for all pipeline failures | BUILT | `manifests/telemetry_spec.yaml`, 5 error classes, P1/P2/P3, 18 codes; validator `scripts/validate_KAN-019.py` | Close in UI |
| PULSE-20 | Scaffold graduated trust model — Tiers 1–4 | BUILT | `manifests/graduated_trust_tiers.yaml`; validator `scripts/validate_KAN-01G.py` | Close in UI |
| PULSE-21 | Scaffold hypothesis library — seed with known patterns | BUILT | `manifests/hypothesis_library.yaml`, 28 hypotheses; validator `scripts/validate_KAN-01H.py` | Close in UI |
| PULSE-22 | Write data contract YAML for MA_D | BUILT | `contracts/ma_d.yaml` exists | Close in UI |
| PULSE-23 | Write data contract YAML for SE (dim_evnt) | NOT_STARTED | Only `ma_d.yaml` in `contracts/` | Leave To Do |
| PULSE-24 | Write data contract YAML for OPS_CD | NOT_STARTED | Only `ma_d.yaml` in `contracts/` | Leave To Do |
| PULSE-25 | Write MA_S output field specification | NOT_STARTED | No spec file | Leave To Do |
| PULSE-26 | Design simulation schema — 5 journey types | NOT_STARTED | No schema file | Leave To Do |
| PULSE-27 | Audit CC_D | BLOCKED | Data access pending | Leave To Do; add `blocked` label |
| PULSE-28 | Build synthetic MA_D event generator | NOT_STARTED | Only `mil/teacher/synthetic_engine.py` (MIL-scoped, different domain) | Leave To Do |
| PULSE-29 | Inject realistic op code sequences from OPS_CD | NOT_STARTED | Depends on PULSE-28 | Leave To Do |
| PULSE-30 | Inject failure modes — nulls, sentinels, schema drift, join gaps | NOT_STARTED | Depends on PULSE-28 | Leave To Do |
| PULSE-31 | Add app_version synthetic field — legacy vs refreshed split | NOT_STARTED | Depends on PULSE-28 | Leave To Do |
| PULSE-32 | Build accuracy benchmark dataset — 50 known journey patterns | NOT_STARTED | No benchmark file | Leave To Do |
| PULSE-33 | Validate simulation output against all data contracts | NOT_STARTED | Depends on PULSE-28..31 | Leave To Do |
| PULSE-34 | Build MA_S sessionisation pipeline in PySpark | PARTIAL | `poc/sessionise.py` (116 lines) exists in `poc/` — POC-grade, not production MA_S pipeline | Leave To Do; mark as having a POC seed |
| PULSE-35 | Build pre-ingestion quality gate validator | NOT_STARTED | No validator | Leave To Do |
| PULSE-36 | Derive behavioural signal fields from ordered event sequence | NOT_STARTED | | Leave To Do |
| PULSE-37 | Build quality gate with full semantic telemetry | NOT_STARTED | | Leave To Do |
| PULSE-38 | MA_S pipeline unit test suite | NOT_STARTED | No tests for sessionise | Leave To Do |
| PULSE-39 | Build daily_journey_mart aggregation | NOT_STARTED | No mart code | Leave To Do |
| PULSE-40 | Add refreshed vs legacy raw comparison layer | NOT_STARTED | | Leave To Do |
| PULSE-41 | Add delta fields | NOT_STARTED | | Leave To Do |
| PULSE-42 | Add circuit breaker threshold checks | NOT_STARTED | MIL has circuit breaker (MIL-33 in `mil/config/model_client.py`); not implemented for PULSE | Leave To Do |
| PULSE-43 | Build CC_D synthetic data generator | NOT_STARTED | | Leave To Do |
| PULSE-44 | Build cross-channel stitching pipeline | NOT_STARTED | | Leave To Do |
| PULSE-45 | Build CUST_DIM synthetic data + join to MA_S | NOT_STARTED | | Leave To Do |
| PULSE-46 | Set up Qwen 2.5-Coder:14b via Ollama in Docker + model config | PARTIAL | Ollama in `docker-compose.yml`; MIL routing now uses qwen3:14b (per `mil/config/model_routing.yaml`); PULSE-specific config not separated | Hold; revisit when PULSE LLM stack is needed |
| PULSE-47 | Build Narrative Agent prompt template | PARTIAL | `poc/narrate.py` (83 lines) exists; not productionised | Leave To Do |
| PULSE-48 | Build response mode classification + recommended action | NOT_STARTED | | Leave To Do |
| PULSE-49 | Build investigation queue generator | NOT_STARTED | | Leave To Do |
| PULSE-50 | Build hypothesis query interface | NOT_STARTED | | Leave To Do |
| PULSE-51 | Adversarial test suite — first run | NOT_STARTED | | Leave To Do |
| PULSE-52 | Build synthetic app store review and NPS generator | NOT_STARTED | | Leave To Do |
| PULSE-53 | Build keyword clustering pipeline | NOT_STARTED | | Leave To Do |
| PULSE-54 | Build Voice Agent | NOT_STARTED | | Leave To Do |
| PULSE-55 | Build expectation and promise registry | NOT_STARTED | | Leave To Do |
| PULSE-56 | Build app store rating velocity signal | NOT_STARTED (PULSE-scope) | MIL-5 built `mil/harvester/rating_velocity_monitor.py` for MIL/public-signal context — **different scope** (public competitor data, not internal Pulse signal) | Leave To Do |
| PULSE-57 | Build orchestrator pipeline runner | NOT_STARTED | | Leave To Do |
| PULSE-58 | Build degraded mode handler | NOT_STARTED | | Leave To Do |
| PULSE-59 | Implement full semantic telemetry on all failures | NOT_STARTED | | Leave To Do |
| PULSE-60 | End-to-end integration test — 7 days synthetic + push notification stubs | NOT_STARTED | | Leave To Do |
| PULSE-61 | Build Streamlit app scaffold with login and navigation | PARTIAL | `app/cji_app.py` (381 lines) + `app/pages/` exist; pages 01–05 are **empty stubs (0 lines)**; page 06 (Loans POC) and 07 (MIL adapter), 08 (Ask CJI Pro shim) populated | Hold; complete login + navigation |
| PULSE-62 | Build daily briefing page + email stub | NOT_STARTED | `app/pages/01_daily_briefing.py` is empty (0 lines) | Leave To Do |
| PULSE-63 | Build journey scorecard page | NOT_STARTED | `app/pages/02_journey_scorecard.py` is empty (0 lines) | Leave To Do |
| PULSE-64 | Build investigation queue page + Slack P1 alert stub | NOT_STARTED | `app/pages/03_investigation_queue.py` is empty (0 lines) | Leave To Do |
| PULSE-65 | Build Ask CJI — conversational hypothesis query interface | NOT_STARTED (PULSE-scope) | `app/pages/04_ask_cji.py` is empty. Ask CJI Pro v1 (MIL-39..48) shipped 2026-04-22 — **different product** (MIL-scoped public signal, no PII); PULSE Ask CJI would need internal-data scope | Leave To Do |
| PULSE-66 | Build voice signal panel | NOT_STARTED | `app/pages/05_voice_panel.py` is empty (0 lines) | Leave To Do |
| PULSE-67 | Choose and document hosting decision + deployment config | NOT_STARTED | No PULSE hosting decision doc | Leave To Do |
| PULSE-68 | Deploy to Streamlit Cloud | NOT_STARTED | | Leave To Do |
| PULSE-69 | Set up GitLab CI/CD pipeline | BUILT | `.gitlab-ci.yml` at root; `ci/test_governance_compliance.py` + `ci/test_hdfs_compliance.py`. **Note: GitLab CI disabled project-wide 2026-04-28** (Free-tier runner exhaustion, see CLAUDE.md) — pipeline definition exists but execution paused | Close in UI; add note that CI is paused |
| PULSE-70 | Configure custom domain cji.pro | BUILT | Live domain is `cjipro.com` (operational since Apr 2026, see `mil/publish/site/`). **Hussain 2026-05-06: domain intent satisfied by `cjipro.com`** — `cji.pro` was the original plan, replaced by `cjipro.com` | Close in UI |
| PULSE-71 | Publish operating model | NOT_STARTED | | Leave To Do |
| PULSE-72 | Write journey owner onboarding guide | NOT_STARTED | | Leave To Do |
| PULSE-73 | Audit and complete system_manifest.yaml — all components | IN_PROGRESS | Manifest exists but has parse error at line 850; needs completion + bug fix | Hold |
| PULSE-74 | Complete system_manifest_index.md — rebuild entry point | NOT_STARTED | No `manifests/system_manifest_index.md` | Leave To Do |
| PULSE-75 | Zero hardcoding audit | NOT_STARTED | | Leave To Do |
| PULSE-76 | Controlled rebuild proof — Voice Agent from manifest | NOT_STARTED | | Leave To Do |
| PULSE-77 | Full adversarial test suite | NOT_STARTED | | Leave To Do |
| PULSE-78 | Run 30-day synthetic evidence pack | NOT_STARTED | | Leave To Do |
| PULSE-79 | Clean-room reconstruction test | NOT_STARTED | | Leave To Do |
| PULSE-80 | Document final accuracy benchmark vs targets | NOT_STARTED | | Leave To Do |
| PULSE-81 | Document Phase 2 gate decisions | NOT_STARTED | | Leave To Do |
| PULSE-82 | Day 90 handover — evidence pack + clean-room results + open items | NOT_STARTED | | Leave To Do |
| PULSE-83 | MIL Phase 0 — Constitutional Foundation | MISFILED (deferred) | This is MIL work (MIL-1 covers same scope on MIL board). Currently in Done state on PULSE | **Hussain 2026-05-06: keep as-is; will repurpose context later** — no reopen, no Won't Do for now |

---

## Closure list — ready for Jira UI close (BUILT → Done)

**Hussain to manual-close in Jira UI** (per the hard rule: Claude does not close tickets programmatically).

1. **PULSE-1** — GitLab mono-repo
2. **PULSE-3** — Data Strategy v2.0
3. **PULSE-4** — Governance Principles
4. **PULSE-12** — Docker environment
5. **PULSE-13** — Audit findings YAML
6. **PULSE-14** — F002 app version resolved
7. **PULSE-17** — system_manifest.yaml *(close as BUILT; file new bug ticket for parse error)*
8. **PULSE-18** — build_from_manifest.py
9. **PULSE-19** — Telemetry spec
10. **PULSE-20** — Graduated trust model
11. **PULSE-21** — Hypothesis library
12. **PULSE-22** — MA_D contract
13. **PULSE-69** — GitLab CI/CD pipeline *(close as BUILT; add comment that runners are paused since 2026-04-28)*
14. **PULSE-70** — Custom domain *(intent satisfied by `cjipro.com`; close as Done)*

## Held pending decision

- **PULSE-5** (Master Data Dictionary — duplicate of PULSE-2): Hussain 2026-05-06 — **hold; do not close yet.**
- **PULSE-83** (MIL Phase 0 misfiled): Hussain 2026-05-06 — **keep as-is; will repurpose context later.** No reopen, no Won't Do action.

---

## Drift fix — CLAUDE.md

CLAUDE.md repeatedly refers to "PULSE-11" as the Living Data Dictionary ticket. **Jira disagrees**:
- Jira PULSE-11 = "Publish customer rights statement and legal basis for derived fields"
- The Living Data Dictionary ticket in Jira is **PULSE-2**

**Lines requiring fix in CLAUDE.md** (all "PULSE-11" references that mean the data dictionary):
- Line 79 (the Day 90 vision context)
- Line 150 ("PULSE-11: Living Data Dictionary (IN_PROGRESS...)")
- Line 152 ("**In progress:** PULSE-11 v2.0...")
- Line 153 ("**Next after PULSE-11:** PULSE-16...")
- Line 912 (Apr 28 next steps "(h) ... CJI Pulse PULSE-11 unblock...")
- Line 918 ("**CJI Pulse PULSE-11 unblock**...")
- Line 944 ("...when PULSE-11 unblocks...")
- Line 1021 ("PULSE-11 v2.0 tracks complete...")
- Line 1027 ("Track F: validate_PULSE-11.py v2.0...")
- Line 1060 ("`manifests/data_strategy_v2.md` | PULSE-11 v2.0 — complete data strategy")
- Line 1062 ("`manifests/data_dictionary_master.yaml` | PULSE-11 — master source...")

**The "PULSE-1G" / "PULSE-1H" references (lines 145–146)** are also drift — those were KAN-era sub-ticket suffixes. In Jira today, the Trust model = PULSE-20 and Hypothesis library = PULSE-21.

### Origin of the drift
The Jira board was migrated from `KAN-*` numbering to `PULSE-*` (commits `968cce2 feat/KAN-016: PULSE board migration` and `480bf94 PULSE migration — KAN references purged, statuses corrected`) but with **a fresh sequential allocation, not a 1:1 KAN→PULSE map**. CLAUDE.md never picked up the new mapping for the four most-cited tickets (KAN-011, KAN-1G, KAN-1H, KAN-016).

### Proposed fix
1. Replace all CLAUDE.md "PULSE-11" data-dictionary references with **PULSE-2**.
2. Replace "PULSE-1G" with **PULSE-20** (graduated trust model).
3. Replace "PULSE-1H" with **PULSE-21** (hypothesis library).
4. Add a one-line note near the top of the PULSE section: *"Numbering migrated from KAN-* to PULSE-* in 2026-03; CLAUDE.md was updated retroactively. Validators in `scripts/` retain `validate_KAN-NNN.py` filenames as historical artefacts."*

---

## PULSE-83 — deferred

PULSE-83 is currently `Done` on the PULSE board with summary "MIL Phase 0 — Constitutional Foundation." This is MIL-board work; MIL-1 is the canonical ticket on the correct board.

**Hussain decision 2026-05-06:** keep as-is. Will repurpose the slot's summary/description later when a real PULSE ticket needs the number. No reopen, no Won't Do action now.

Future-Hussain: edit summary + description in place when assigning real work. The Done status preserves audit trail until the slot is repurposed.

---

## Bugs / follow-ups surfaced by this audit

1. **`manifests/system_manifest.yaml` parse error at line 850** — FIXED 2026-05-06. Added `mil_components:` top-level key; manifest now parses cleanly (71 MIL entries indexed under the new key). Validates `import yaml; yaml.safe_load(...)` clean.
2. **Empty page stubs in `app/pages/01_..05_*.py`** — DELETED 2026-05-06. Page nav now contains only populated pages (06_loans_poc, 07_mil, 08_ask_cji_pro). PULSE-62..66 will recreate when work starts.
3. **`poc/sessionise.py` and `poc/narrate.py` belong to PULSE-34/PULSE-47** — open. Currently parked in `poc/`. Promote to a future `pulse/` directory when those tickets are picked up, or annotate as POC-stage in their docstrings.
4. **`mil_components:` in PULSE manifest mixes MIL ticket inventory into the PULSE source-of-truth manifest** — not a bug, but worth flagging. Originally specced as Sprint 2 + MIL Phase 0 work co-tracked in one manifest; now that MIL has its own Jira board and matures separately, the MIL block could migrate to a dedicated `mil/manifest.yaml`. Defer until someone needs it.

---

## Acceptance criteria — status

- [x] Reconciliation doc committed *(this file)*
- [x] CLAUDE.md PULSE references corrected *(2026-05-06: 11 line fixes applied — PULSE-10→PULSE-1, PULSE-1G→PULSE-20, PULSE-1H→PULSE-21, PULSE-11→PULSE-2, plus PULSE-3 for data-strategy table-row, plus migration note inserted)*
- [x] Closure list delivered to Hussain *(BUILT list above; held list above)*
- [ ] PULSE-83 misfiling resolved *(deferred per Hussain 2026-05-06 — keep as-is, repurpose later)*

Three of four AC complete. PULSE-83 deferred-by-decision. Once the 14-ticket closure list is actioned in Jira UI, PULSE-84 itself is ready to close.
