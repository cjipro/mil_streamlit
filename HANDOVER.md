# CJI Pulse — Handover Brief
**For:** Next Claude session
**Date:** 2026-03-12
**Prepared by:** Claude (browser session)
**Status:** Sprint 1 — Day 2 of 7 — 8 tickets BUILT, 3 blocked, 1 pending human input

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

**KAN-014 is blocked because Hadoop is slow — not because of a data knowledge gap.**
The recovery path is Databricks federation (already defined in contracts/ma_d.yaml).

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

---

## Model Routing Rules

| Use Sonnet (claude-sonnet-4-6) for | Use Qwen (local) for |
|-------------------------------------|----------------------|
| Multi-file logic | Simple YAML scaffolds |
| CLI tools with multiple flags | Single-file templates with no dependencies |
| Telemetry spec compliance | Validation scripts under 50 lines |
| Anything reading multiple manifests | Clearly isolated boilerplate |
| Anything that took Qwen >10 mins | — |

**Default to Sonnet when in doubt.**

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
│   ├── system_manifest.yaml            ← THE MANIFEST — 73 components, source of truth
│   ├── telemetry_spec.yaml             ← KAN-019 — error spec, all pipelines must use
│   ├── graduated_trust_tiers.yaml      ← KAN-01G — trust model, Tier 5 LOCKED_PHASE_2
│   ├── hypothesis_library.yaml         ← KAN-01H — 23 hypotheses, 16 APPROVED, 7 PENDING
│   └── audit_findings.yaml             ← KAN-013 — 5 findings, FIND-002 CRITICAL/OPEN
├── scripts/
│   ├── build_from_manifest.py          ← KAN-018 — executable manifest runner
│   ├── validate_KAN-012.py
│   ├── validate_KAN-013.py
│   ├── validate_KAN-018.py
│   ├── validate_KAN-019.py
│   ├── validate_KAN-020.py
│   ├── validate_KAN-01G.py
│   └── validate_KAN-01H.py
└── src/agents/ app/ agents/ data/ docs/ notebooks/ tests/
```

---

## Ticket Status — Sprint 1 (Days 1–7)

### BUILT ✅

| Ticket | Name | Commit | Notes |
|--------|------|--------|-------|
| KAN-010 | Initialise GitLab mono-repo | — | Complete |
| KAN-017 | system_manifest.yaml | `377a4be` | 73 components |
| KAN-019 | telemetry_spec.yaml | `021a8a9` | 18 error codes |
| KAN-01G | graduated_trust_tiers.yaml | `d630986` + `4c65746` | Tier 5 locked, storage targets added |
| KAN-01H | hypothesis_library.yaml | `dd89e32` | 23 hypotheses, 16 APPROVED |
| KAN-013 | audit_findings.yaml | `fe492e2` | 5 findings, FIND-002 CRITICAL/OPEN |
| KAN-018 | build_from_manifest.py | `bb47a21` | Supports --component, --dry-run, --status, --sprint |
| KAN-012 | Docker environment | — | All 4 services confirmed healthy |

### ADDITIONAL WORK COMPLETED THIS SESSION

| Item | Commit | Notes |
|------|--------|-------|
| Law of Consistency normalisation | `fcbd0dc` | KAN-1G/1H → KAN-01G/01H across all layers |
| Model string updates | `19303ff` | claude-3.x → claude-sonnet-4-6 / claude-opus-4-6 |
| Manifest hardening | `4c65746` | Zero-copy contract, edge-aware recovery, adoption hooks |
| CLAUDE.md model routing rules | `b505f7f` | Sonnet vs Qwen routing documented |

### BLOCKED ⏸️

| Ticket | Blocked By | Who Unblocks |
|--------|-----------|--------------|
| KAN-014 | Hadoop access latency | HUMAN — investigate app_version via Databricks/Snowflake |
| KAN-015 | Data access | HUMAN — needs data warehouse access for CUST_DIM |
| KAN-011 | Real table names needed | HUMAN — provide actual employer table names |

### NOT STARTED ⬜

| Ticket | Depends On |
|--------|-----------|
| KAN-016 | KAN-011, KAN-014, KAN-015 must complete first |

---

## ⚠️ HUMAN ACTION REQUIRED — Do These Before Next AI Session

### PRIORITY 1 — Unblock KAN-014
**Action:** Investigate app_version / experience cohort field via Databricks or Snowflake (not Hadoop)
**What to look for:** Does app_version or experience_cohort exist in any accessible table?
**Report back:** Field name, table name, data type, sample values

### PRIORITY 2 — Provide real table names for KAN-011
**Action:** Share actual employer table names for these aliases:
- MA_D → ?
- SE → ?
- OPS_CD → ?
- CC_D → ?
- CUST_DIM → ?
- MA_S → ? (output table)

### PRIORITY 3 — Audit CUST_DIM (KAN-015)
**Action:** Check CUST_DIM for: age_band, vulnerability_flag, customer_segment fields
**Report back:** Which fields exist, data types, null rates

### AFTER KAN-016 RUNS (future session only)
**Action:** Manually close in Jira UI at https://cjipro.atlassian.net:
KAN-010, KAN-017, KAN-019, KAN-01G, KAN-01H, KAN-013, KAN-018, KAN-012

---

## What AI Should Do Autonomously in Next Session
```
1. KAN-011 — Build config/table_config.py with real TABLE_CONFIG dictionary
   Tool: Sonnet | Create + run scripts/validate_KAN-011.py

2. KAN-014 — Document resolution of FIND-002 in audit_findings.yaml
   Tool: Sonnet | Update manifests/audit_findings.yaml FIND-002 status

3. KAN-015 — Document CUST_DIM audit findings
   Tool: Sonnet | Update manifests/audit_findings.yaml with new findings

4. KAN-016 — Create all 76 Jira tickets via API
   Tool: Sonnet | Requires KAN-011, KAN-014, KAN-015 complete
   IMPORTANT: Creation only — never close tickets programmatically

5. Sprint 2 tickets KAN-021/022/023/024 can start immediately
   if Sprint 1 remains blocked — no dependencies on blocked tickets
```

---

## Sprint 2 Preview — Can Start Early if Sprint 1 Blocked

| Ticket | Name |
|--------|------|
| KAN-021 | Data contract YAML for SE (dim_evnt) |
| KAN-022 | Data contract YAML for OPS_CD |
| KAN-023 | MA_S output field specification |
| KAN-024 | Simulation schema — 5 journey types |
| KAN-020 | MA_D data contract full build (skeleton exists) |

---

## Decisions Made This Session (2026-03-12)

| Decision | Detail |
|----------|--------|
| Law of Consistency | KAN-0XX three-digit padding universal — enforced across all layers |
| Model routing | Sonnet for complex, Qwen for simple boilerplate only |
| Manifest hardening | Consultant recommendations incorporated at manifest layer — no new code |
| Infrastructure reality | Databricks/Snowflake/ClickHouse reflected in manifest |
| KAN-014 root cause | Hadoop latency — recovery path is Databricks federation |
| Jira UI not available | KAN-016 not run — dual closure applies only after KAN-016 |
| HANDOVER.md | Single file, always overwritten, git tracks evolution |

---

## Programme Principles (The 12)

1. Every Friday: something deployed, board moved, technical problem solved
2. Demotivation is #1 risk: short sprints, visible wins, scope protected
3. Manifest is source of truth: Jira is a view, never the source
4. Manifest executable from Day 1
5. Audit before architecture: Canonical Statement 04 is law
6. Semantic telemetry on every failure
7. Build for future agents: all config machine-readable YAML
8. Human-led first release
9. One command to run everything: `py run_daily.py --date YYYY-MM-DD`
10. Protect customer outcomes: Do Not Break, CONTRADICTED, vulnerable cohorts are first-class
11. Governance as a ramp, not a wall
12. AI is easy to demo. It is hard to ship. Day 90 is a shipping proof, not a demo.

---

## Session Commits (2026-03-12)

| Hash | Message |
|------|---------|
| `fe492e2` | feat/KAN-013: audit_findings.yaml — 5 findings, validator passes |
| `357179a` | chore: update KAN-013 status to BUILT in system_manifest.yaml |
| `bb47a21` | feat/KAN-018: build_from_manifest.py — executable manifest runner |
| `19303ff` | chore: update CLAUDE.md sprint status + model routing rules |
| `fcbd0dc` | chore: Law of Consistency — normalise KAN-01G/01H across all layers |
| `83c96f7` | chore: update CLAUDE.md — correct sprint status |
| `7fba1b1` | chore: sync system_manifest.yaml — KAN-17 BUILT |
| `4c65746` | feat: manifest hardening — zero-copy contract, edge-aware recovery |
| `b505f7f` | chore: update CLAUDE.md — manifest hardening context added |

---

## JSON Machine Summary
```json
{
  "session_date": "2026-03-12",
  "sprint": 1,
  "sprint_day": 2,
  "tickets_built": ["KAN-010","KAN-017","KAN-019","KAN-01G","KAN-01H","KAN-013","KAN-018","KAN-012"],
  "tickets_blocked": ["KAN-014","KAN-015","KAN-011"],
  "tickets_not_started": ["KAN-016"],
  "human_actions_required": [
    "Investigate app_version field via Databricks/Snowflake — unblocks KAN-014",
    "Provide real employer table names for TABLE_CONFIG — unblocks KAN-011",
    "Audit CUST_DIM for age_band, vulnerability_flag — unblocks KAN-015"
  ],
  "agentic_next_actions": [
    "KAN-011: Build TABLE_CONFIG once human provides table names",
    "KAN-014: Document FIND-002 resolution once human provides app_version info",
    "KAN-016: Create all Jira tickets once KAN-011/014/015 complete",
    "Sprint 2 tickets KAN-021/022/023/024 can start if Sprint 1 blocked"
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
