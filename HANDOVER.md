# CJI Pulse — Handover Brief
**For:** Next Claude session
**Date:** 2026-03-12
**Prepared by:** Claude (browser session)
**Status:** Sprint 1 — Day 2 of 7 — 8 tickets BUILT, 1 IN_PROGRESS, 3 blocked, 1 pending human input

---

## FIRST: Read This Before Doing Anything

This file is the authoritative handover for the next Claude session. It contains:
- What has been built (with commit hashes)
- What only the human can do (clearly labelled)
- What the AI agent should do autonomously
- The full infrastructure reality as of 2026-03-12

**Start command for next session:**
> "Read CLAUDE.md and this HANDOVER.md. Confirm orientation. Report current sprint status. Await instruction."

CLAUDE.md is auto-read by Claude Code on launch. Attach this file manually.

---

## The System in One Sentence

CJI Pulse is a Python-based journey intelligence platform that ingests 330M app sessions monthly, derives behavioural signals, classifies findings with response modes (EVIDENCED / DIRECTIONAL / CONTRADICTED / GUARDED / UNKNOWN), and presents them to ~20 journey owners via a Streamlit dashboard and conversational query interface.

**Day 90 Vision:**
> "Customers experiencing difficulties on Step 3 of Loans journey, abandoning — likely 45+, likely vulnerable. In last 3 days 5 customers said App journey sucks."

---

## Environment

| Item | Value |
|------|-------|
| GitLab repo | `https://gitlab.com/streaming-analytics/while-sleeping` |
| GitLab Project ID | `80021701` |
| Jira site | `https://cjipro.atlassian.net` |
| Jira project key | `KAN` |
| Jira cloud ID | `d9b829b8-66af-42de-bc53-a79515365742` |
| Jira email | `hussain.marketing@gmail.com` |
| Local repo | `C:\Users\hussa\while-sleeping\` |
| OS | Windows — always use `py` not `python` or `python3` |
| Python command | `py` |
| Git shell | Git Bash (MINGW64) |
| Claude Code | Latest — launch with `claude` in repo directory |
| Node.js | v24.14.0 |
| Ollama | Running — `qwen2.5-coder:14b` at `http://localhost:11434` |

**Credentials** are in `~/while-sleeping/.env` (gitignored). Never commit this file.

---

## Infrastructure Reality (Updated 2026-03-12)

| Platform | Status | Role |
|----------|--------|------|
| Hadoop | Legacy — slow, blocking KAN-014 | Source of raw app events (MA_D) |
| Databricks | Contract signed, onboarding in progress | Primary replacement for Hadoop |
| Snowflake | Onboarded and available | Available now for data contracts |
| ClickHouse | POC in place | Analytics layer candidate |
| Docker | Running — all 4 services healthy | Local dev environment |
| PostgreSQL | localhost:5432, db=cjipulse | Local dev database |
| Streamlit | http://localhost:8501 (admin/admin123) | Frontend |
| Jupyter | http://localhost:8888 | PySpark notebooks |
| Ollama | http://localhost:11434 | Local model inference |

---

## Critical Rules — Non-Negotiable

1. **Jira ticket closure is always manual** — human closes in Jira UI. Never programmatic. Ever.
2. **Manifest is source of truth** — `system_manifest.yaml` overrides everything including Jira
3. **Dual closure rule** — validator passes AND human closes in Jira UI. Neither alone is sufficient.
4. **Always use `py`** not `python` or `python3` on this Windows machine
5. **Validate before committing** — run validator, report result, then commit
6. **Two-commit rule** — feat: commit for work, chore: commit for manifest/CLAUDE.md update
7. **Never close Jira tickets programmatically** — this is rule 1 restated. That important.
8. **Law of Consistency** — all ticket IDs use three-digit padded format: KAN-0XX (e.g. KAN-013, KAN-01G)
9. **Jira does not exist yet** — KAN-016 has not run. Zero tickets in Jira UI. Do not attempt Jira actions.
10. **Model routing** — use Sonnet for complex tasks, Qwen for simple YAML/templates only
11. **Original names never enter the system** — HMAC-SHA256 hashes only. Hashes generated outside codebase.
12. **source_hash = HASH_PENDING_ORIGINAL** in all table entries until original system provides hash.
13. **TAQ Bank rule** — only organisational name that surfaces. Substitution registry active and mandatory.
14. **WARN_NOT_FAIL** — principle violations emit WARN_P codes. Builds never fail on principle checks.

---

## Repo Structure (Live as of 2026-03-12)
```
~/while-sleeping/
├── CLAUDE.md                           ← auto-read by Claude Code — persistent context
├── HANDOVER.md                         ← this file — attach to every browser session
├── .env                                ← credentials, gitignored, never commit
├── .env.example                        ← committed template
├── config/
│   ├── model_config.yaml               ← hybrid model routing config
│   └── model_router.yaml               ← routing logic (updated to claude-sonnet-4-6)
├── contracts/
│   └── ma_d.yaml                       ← KAN-020 skeleton — zero-copy contract
├── manifests/
│   ├── system_manifest.yaml            ← THE MANIFEST — 82 components, source of truth
│   ├── telemetry_spec.yaml             ← KAN-019 — error spec, all pipelines must use
│   ├── graduated_trust_tiers.yaml      ← KAN-01G — trust model, Tier 5 LOCKED_PHASE_2
│   ├── hypothesis_library.yaml         ← KAN-01H — 23 hypotheses, 16 APPROVED, 7 PENDING
│   ├── audit_findings.yaml             ← KAN-013 — 5 findings, FIND-002 CRITICAL/OPEN
│   ├── data_strategy_v2.md             ← KAN-011 — complete data strategy v2.0
│   ├── governance_principles.yaml      ← KAN-011 — 21 constitutional principles v2.0
│   └── data_dictionary_master.yaml     ← KAN-011 — master source, 10 tables, HASH_PENDING
├── scripts/
│   ├── build_from_manifest.py          ← KAN-018 — executable manifest runner
│   ├── validate_KAN-011.py             ← v2.0 — 16 checks, all passing
│   ├── validate_KAN-012.py
│   ├── validate_KAN-013.py
│   ├── validate_KAN-018.py
│   ├── validate_KAN-019.py
│   ├── validate_KAN-020.py
│   ├── validate_KAN-01G.py
│   ├── validate_KAN-01H.py
│   └── validate_principles.py          ← WARN_NOT_FAIL checker, always exit 0
└── logs/
    └── principle_warnings.log          ← WARN_P codes logged here
```

---

## Ticket Status — Sprint 1 (Days 1–7)

### BUILT ✅

| Ticket | Name | Commit | Notes |
|--------|------|--------|-------|
| KAN-010 | Initialise GitLab mono-repo | — | Complete |
| KAN-017 | system_manifest.yaml | `377a4be` | 82 components (was 73) |
| KAN-019 | telemetry_spec.yaml | `021a8a9` | 18 error codes |
| KAN-01G | graduated_trust_tiers.yaml | `d630986` + `4c65746` | Tier 5 locked |
| KAN-01H | hypothesis_library.yaml | `dd89e32` | 23 hypotheses, 16 APPROVED |
| KAN-013 | audit_findings.yaml | `fe492e2` | 5 findings, FIND-002 CRITICAL/OPEN |
| KAN-018 | build_from_manifest.py | `bb47a21` | Supports --component, --dry-run, --status, --sprint |
| KAN-012 | Docker environment | — | All 4 services confirmed healthy |

### IN PROGRESS 🔄

| Ticket | Status | Notes |
|--------|--------|-------|
| KAN-011 | IN_PROGRESS | v2.0 data strategy complete. Field population awaiting human input. |

### KAN-011 v2.0 Track Commits (2026-03-12)

| Track | Commit | What Was Built |
|-------|--------|----------------|
| A | `846a306` | data_strategy_v2.md — complete data strategy v2.0 |
| B | `ba19e96` | governance_principles.yaml v2.0 — 21 principles, table registry, substitution registry, 3-layer governance, REG-001–004 |
| C | `8fb05ed` | data_dictionary_master.yaml — skeleton 10 tables, all HASH_PENDING_ORIGINAL |
| D | `6e0cf82` | system_manifest.yaml — KAN-011 v2.0, 82 components, REG-001–REG-004 registered |
| E | `9255b06` | CLAUDE.md — data strategy v2.0 embedded, principle agent names, critical rules |
| F | `cce12bd` | validate_KAN-011.py v2.0 — 16 checks all PASS, 1 WARN_P4 (expected) |
| G | this commit | system_manifest.yaml final sync + HANDOVER.md |

### BLOCKED ⏸️

| Ticket | Blocked By | Who Unblocks |
|--------|-----------|--------------|
| KAN-014 | Hadoop access latency + AF-002 CRITICAL OPEN (app_version not found) | HUMAN — investigate app_version via Databricks/Snowflake |
| KAN-015 | Data access | HUMAN — needs data warehouse access for CUST_DIM |
| KAN-011 field population | Human must provide field lists | HUMAN — see Human Actions Required below |

### NOT STARTED ⬜

| Ticket | Depends On |
|--------|-----------|
| KAN-016 | KAN-011, KAN-014, KAN-015 must complete first |

---

## ⚠️ HUMAN ACTION REQUIRED — Do These Before Next AI Session

### PRIORITY 1 — KAN-011 Field Population
Provide field lists for:
- **MAER (Mobile_App_Events_Raw)** — field names, types, sample values, PII flags
- **MAER_F (Mobile_App_Events_Ref)** — field names and types
- **OCR (Operation_Codes_Ref)** — field names and types (465 codes)
- Investigate native flag in OCR — meaning unknown (AF-003 MEDIUM FLAGGED)

### PRIORITY 2 — AF-002 CRITICAL (KAN-014)
**Action:** Investigate whether app_version or experience_cohort field exists in any accessible table via Databricks or Snowflake
**Report back:** Field name, table name, data type, sample values — or confirmation it doesn't exist

### PRIORITY 3 — Audit CUST_DIM (KAN-015)
**Action:** Check CPD for: age_band, vulnerability_flag, customer_segment fields
**Report back:** Which fields exist, data types, null rates
**Note:** REG-002 blocks DPIA completion until this audit is done

### PRIORITY 4 — Regulatory Actions
These four actions are required before live customer data is processed:
- REG-001: Register formal DPIA with data protection function
- REG-002: Complete audit of Customer_Profile_Dim
- REG-003: Publish vulnerability data processing statement
- REG-004: Publish customer rights statement + legal basis for derived fields

### PRIORITY 5 — Source Hashes
When ready, provide HMAC-SHA256 hashes for each table's original fully-qualified name.
Hashes must be generated by the original system using their secret key — outside this codebase.
Paste hashes into data_dictionary_master.yaml replacing HASH_PENDING_ORIGINAL values.

### AFTER KAN-016 RUNS (future session only)
**Action:** Manually close in Jira UI at https://cjipro.atlassian.net:
KAN-010, KAN-017, KAN-019, KAN-01G, KAN-01H, KAN-013, KAN-018, KAN-012

---

## What AI Should Do Autonomously in Next Session
```
1. KAN-011 field population — once human provides MAER/MAER_F/OCR field lists
   Tool: Sonnet | Populate data_dictionary_master.yaml fields section per table
   Then: Run validate_KAN-011.py — expect PASS 16/16

2. KAN-011 dict generation — once master is populated
   Tool: Sonnet | Generate data_dictionary_human.yaml (gold fields only)
   Tool: Sonnet | Generate data_dictionary_agentic.yaml (all fields, context-rich)

3. KAN-014 — Document resolution of AF-002 in audit_findings.yaml
   Tool: Sonnet | Once human provides app_version information

4. KAN-015 — Document CUST_DIM audit findings
   Tool: Sonnet | Once human provides field audit results

5. KAN-016 — Create all Jira tickets via API
   Tool: Sonnet | Requires KAN-011, KAN-014, KAN-015 complete
   IMPORTANT: Creation only — never close tickets programmatically

6. Sprint 2 tickets KAN-021/022/023/024 can start if Sprint 1 blocked
```

---

## KAN-011 v2.0 — What Is Ready for Next Session

| Artifact | Status | Notes |
|----------|--------|-------|
| data_strategy_v2.md | BUILT | Complete. No changes needed. |
| governance_principles.yaml | BUILT | Complete. 21 principles, all structures present. |
| data_dictionary_master.yaml | IN_PROGRESS | Skeleton done. Fields[] empty. Awaiting field lists from human. |
| data_dictionary_human.yaml | NOT_STARTED | Will be generated from master once fields populated. |
| data_dictionary_agentic.yaml | NOT_STARTED | Will be generated from master once fields populated. |
| validate_KAN-011.py | BUILT | v2.0, 16 checks, PASS. Will re-run after field population. |

---

## Validator Results (Track F)

```
validate_KAN-011.py v2.0 -- all 16 checks PASS
  [PASS] data_strategy_v2.md exists and is non-empty
  [PASS] governance_principles.yaml exists and valid YAML
  [PASS] All 21 principles present (P1-P21) -- 21 found
  [PASS] All 21 agent_names present and non-empty
  [PASS] violation_policy is WARN_NOT_FAIL
  [PASS] All 10 tables in table_registry -- 10 found
  [PASS] All source_hashes are HASH_PENDING_ORIGINAL
  [PASS] substitution_registry has 3 entries
  [PASS] data_dictionary_master.yaml exists and valid YAML
  [PASS] All 10 tables in master dictionary -- 10 found
  [PASS] No original names in master dictionary
  [WARN_P4] Check: no original names detected in master dictionary -- PASS
  [PASS] REG-001 through REG-004 present
  [PASS] Three-layer governance present with all 3 layers
  [PASS] Reassessment triggers present (event_driven + scheduled)

Checks: 16 passed, 0 failed
WARN_P codes raised: 1 (WARN_P4 informational -- confirming no original names detected)
Exit code: 0
No build failed on principle violation.
```

---

## JSON Machine Summary
```json
{
  "session_date": "2026-03-12",
  "sprint": 1,
  "sprint_day": 2,
  "tickets_built": ["KAN-010","KAN-017","KAN-019","KAN-01G","KAN-01H","KAN-013","KAN-018","KAN-012"],
  "tickets_in_progress": ["KAN-011"],
  "tickets_blocked": ["KAN-014","KAN-015"],
  "tickets_not_started": ["KAN-016"],
  "component_count": 82,
  "kan_011_v2_tracks": {
    "A": "846a306",
    "B": "ba19e96",
    "C": "8fb05ed",
    "D": "6e0cf82",
    "E": "9255b06",
    "F": "cce12bd",
    "G": "pending_this_commit"
  },
  "validator_result": "PASS 16/16",
  "warn_p_codes_raised": ["WARN_P4 (informational)"],
  "build_failed_on_principle": false,
  "all_source_hashes": "HASH_PENDING_ORIGINAL",
  "original_names_in_codebase": false,
  "taq_bank_rule": "active",
  "substitution_registry": "active",
  "regulatory_open_items": ["REG-001","REG-002","REG-003","REG-004"],
  "human_actions_required": [
    "Provide MAER field list for dictionary population",
    "Provide MAER_F field list",
    "Provide OCR field list",
    "Investigate app_version source (AF-002 CRITICAL OPEN)",
    "Audit CUST_DIM (REG-002, KAN-015)",
    "Register DPIA (REG-001)",
    "Real table name hashes generated outside codebase by original system"
  ],
  "infrastructure": {
    "hadoop": "SLOW — blocking KAN-014",
    "databricks": "CONTRACT_SIGNED — onboarding",
    "snowflake": "LIVE",
    "clickhouse": "POC",
    "docker": "HEALTHY — all 4 services running",
    "ollama": "RUNNING — qwen2.5-coder:14b"
  },
  "jira_state": "EMPTY — KAN-016 not yet run",
  "human_required": true
}
```

---

*Handover prepared: 2026-03-12. Single file — git tracks evolution.*
*Next session: Read CLAUDE.md + this file. Confirm orientation. Await instruction.*
