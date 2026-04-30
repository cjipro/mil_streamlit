# Private paths — CJI vs Hodos boundary at the file level

This document maps the seven categories of CJI-private content (per
[hodos/HODOS_NAMING.md](hodos/HODOS_NAMING.md)) to the file paths and
deny-list patterns that enforce them. It exists so contributors, future
Claude sessions, and forkers can see at a glance what stays on the CJI
side and what could eventually ship in the public Hodos engine.

Lock context: MIL-110 (rewrite 2026-04-30) under MIL-167 architectural
lock. See `CLAUDE.md` section "Hodos / CJI Architecture (LOCKED
2026-04-30 — canonical)" for the operational rule.

## Two enforcement points

1. **Publish-time deny-list** in `mil/publish/adapters.py`
   (`SENSITIVE_PATH_PATTERNS`). Refuses any `adapter.publish(path,
   content)` call where `path` matches a sensitive pattern. Defensive
   net against caller bugs that try to push sensitive content to the
   Pages repo.

2. **Pages-repo hygiene scanner** in
   `scripts/check_public_repo_hygiene.py`. Audits the live
   `cjipro/mil-briefing` repo for any tracked file matching the same
   patterns, plus a content-policy scan for known-sensitive strings
   (D1 UUIDs, Org IDs, API tokens, scheduled-trigger IDs, CHRONICLE
   entry headers).

Both enforcement points are kept in lock-step. Adding a category here
means updating the patterns in both files plus the test paths in
`mil/tests/test_publish_deny_list.py`.

## The seven categories

### 1. CJI CHRONICLE entries (CJI-private)

Real banking incident analyses — CHR-001..019+ and growing. CJI's
curated ledger; partner-grade content.

| Path | Why blocked |
|---|---|
| `mil/CHRONICLE.md` | Master ledger file |
| `mil/chronicle/entries/CHR-*.yaml` | Per-entry YAML files |

NB: chronicle_id *references* (e.g. "anchor: CHR-007" in V4 Provenance
Chain inference cards) are LEGITIMATE in rendered briefings. The
hygiene scanner targets the structured-entry form (markdown headers,
YAML keys), not the references.

### 2. Tenant data (CJI-private)

Per-tenant operational data. Includes partner-identifying signals.

| Path | Why blocked |
|---|---|
| `mil/data/historical/` | Enriched record corpus (signal data) |
| `mil/data/*_log.jsonl` | Pipeline run logs (clark, commentary, daily run, persistence, etc.) |
| `mil/vault/` | HDFS vault contents (mil_vault.db, anchor logs) |
| `mil/outputs/` | Inference findings (mil_findings.json etc.) |

### 3. Tenant identity + partner identities (CJI-private)

Names real cjipro.com values + alpha partner identities.

| Path | Why blocked |
|---|---|
| `mil/config/tenant.yaml` | cjipro.com domain config, organisation identity |
| `mil/config/clients.yaml` | Partner names + email-domain mapping |

### 4. CJI brand surface sources (CJI-private — trademark)

The HTML sources for cjipro.com. Rendered output ships to Pages; the
source files themselves stay in the CJI repo to enforce Mozilla-style
trademark policy (see `hodos/TRADEMARK.md`).

| Path | Why blocked |
|---|---|
| `mil/publish/site/` | Source HTML for cjipro.com landing, privacy, products, security, etc. |

### 5. Engine code (Hodos-bound, blocked from Pages anyway)

Belongs in the future `cjipro/hodos` public repo. Blocked from the
Pages repo because Pages serves rendered output only.

| Path | Why blocked from Pages |
|---|---|
| `mil/auth/` | Auth Workers — Hodos-bound; never appears as Pages content |
| `mil/chat/` | Chat layer — Hodos-bound |
| `mil/inference/` | Inference engine — Hodos-bound |
| `mil/harvester/` | Signal harvesters — Hodos-bound |
| `mil/specialist/` | Specialist pipeline — Hodos-bound |
| `mil/teacher/` | Teacher pipeline — Hodos-bound |
| `scripts/` | Operations scripts — internal |
| `ops/runbooks/` | Runbooks — internal |

### 6. Internal docs (CJI-private)

Working notes for the project; not artefacts.

| Path | Why blocked |
|---|---|
| `CLAUDE.md` | Project instructions for Claude Code |
| `MEMORY.md` | Memory index |
| `MILXX_*.md` | Internal MIL-NN runbooks (e.g. MIL67_PASSKEYS.md) |

### 7. Secrets

Always blocked, regardless of CJI/Hodos framing.

| Path | Why blocked |
|---|---|
| `.env*` | Environment files |
| `secrets.{yaml,yml,json,toml}` | Secret files |

## What's NOT in this list (public-by-design)

- Rendered HTML output going to the Pages repo (`briefing/`,
  `briefing-v4/`, `sonar/{slug}/`, `products/`, `security/`,
  `research/`, `insights/`, `press/`, `trust/`, etc.) — these ARE the
  published artefacts.
- Hodos legibility docs in `hodos/` — those eventually ship in the
  public `cjipro/hodos` repo.
- Synthetic / sample data corpora (`mil/data/sample/`) — illustrative,
  no real banking content.
- Documentation files in `hodos/` (LICENSE / NOTICE / TRADEMARK.md /
  CONTRIBUTING.md / GOVERNANCE.md / HODOS_NAMING.md).

## Quick test

If you're touching a file and want to know which side of the boundary
it's on, grep the patterns:

    py -m pytest mil/tests/test_publish_deny_list.py -v

If a path you intend to publish raises `ValueError`, that's the
deny-list catching a category violation. Move the content elsewhere or
update the deny-list (with a corresponding test addition) if you've
genuinely identified a new public-by-design path.

## When this list changes

Update all four together — they're kept in lock-step by review:

1. `PRIVATE_PATHS.md` (this file) — the human-readable categorisation
2. `mil/publish/adapters.py` `SENSITIVE_PATH_PATTERNS` — the publish-time guard
3. `scripts/check_public_repo_hygiene.py` `SENSITIVE_PATH_PATTERNS` import + `SENSITIVE_CONTENT_PATTERNS` — the audit-time scanner
4. `mil/tests/test_publish_deny_list.py` `LEGITIMATE_PATHS` + `SENSITIVE_PATHS` — the regression suite

## Reference

- Engine vs product split: `hodos/HODOS_NAMING.md`
- Architectural lock: `CLAUDE.md` section "Hodos / CJI Architecture (LOCKED 2026-04-30 — canonical)"
- Lock context: MIL-167
- This rewrite: MIL-110
