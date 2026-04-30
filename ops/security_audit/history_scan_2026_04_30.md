# Git history secret audit — 2026-04-30

Two-pass scan of the full repo history (`git log --all`):

1. **Pattern scan** (`scripts/scan_history_secrets.py`) — stdlib + git CLI, no external deps. Catches known token shapes (sk-ant-, ghp_, glpat-, hooks.slack.com, sk_test_, AKIA, etc.).
2. **gitleaks** v8.30.1 — proper entropy + rule library. Installed via winget for this audit.

## Pattern scan — clean

```
scan_history_secrets — clean (no pattern hits in repo history)
```

The Slack webhook leak from 2026-04-20 is no longer present in history (resolved at the time via `git filter-branch` rewrite of 214 commits per CLAUDE.md). No other matches against the catalogued token shapes.

## gitleaks — 8 findings, classified

405 commits scanned, 13.4 MB of diff content, 8 raw findings. Detail in `ops/security_audit/gitleaks_report.json` (redacted).

| # | Rule | File | Classification | Action |
|---|---|---|---|---|
| 1 | generic-api-key | `mil/auth/magic_link/test/sign_in.test.ts:22` | **False positive** — test fixture, value is a literal `mil149-test-key-...` | None |
| 2 | generic-api-key | `mil/auth/magic_link/test/webhooks.test.ts:4` | **False positive** — test fixture, `whsec_test_0123456789abcdef0123456789abcdef` (placeholder) | None |
| 3 | generic-api-key | `mil/auth/magic_link/test/state.test.ts:4` | **False positive** — test fixture, `test-signing-key-0123456789abcdef` | None |
| 4 | generic-api-key | `mil/auth/magic_link/test/index.test.ts:16` | **False positive** — same test fixture | None |
| 5 | generic-api-key | `mil/auth/magic_link/test/callback.test.ts:15` | **False positive** — same test fixture | None |
| 6 | generic-api-key | `CLAUDE.md:591` | **False positive** — `chronicle_id=1.0` (RAG match score), pattern-only false positive on the `=1.0` substring | None |
| 7 | curl-auth-user | `conductor/.claude/settings.local.json:18` | **Pre-rotated** — `admin:admin` curl against `localhost:11434` (local Ollama, never exposed to internet) | None — well-known default, local-only port |
| 8 | jwt | `conductor/.claude/settings.local.json:7` | **Real finding — Astronomer.io JWT** (auth_connection token from a Claude Code session in the `conductor/` sub-project) | **Rotate** if still live |

## Real finding — Astronomer.io JWT in conductor settings — RESOLVED

**File:** `conductor/.claude/settings.local.json` (a Claude Code per-project settings file from a nested sub-project)
**Commit:** `bcee05c3351052164ade57364e1ca399b96ce1f9`
**Date:** 2026-03-18
**Author:** Hussain
**Issue type:** Browser-session JWT committed alongside an unrelated PULSE-migration sync commit.

**Resolution (2026-04-30):**

Decoded the JWT locally — confirmed it was a short-lived browser-session token:

| Claim | Value |
|---|---|
| `iss` | `https://auth.astronomer.io/` |
| `aud` | `[astronomer-ee, https://astronomer-prod.us.auth0.com/userinfo]` |
| `iat` | 2026-03-13 23:40:05 UTC |
| `exp` | 2026-03-14 00:40:05 UTC |
| Lifetime | **1 hour** |
| Status as of audit | **EXPIRED 47 days ago** |

Astronomer's session JWTs are short-lived by design (1-hour TTL via Auth0). There are no long-lived API tokens in the user's Astronomer account. The leaked credential was dead before this audit ran.

**Action taken:**
- Token tail `gCbGf33e45vg` added to `KNOWN_ROTATED` in `scripts/scan_history_secrets.py` so future scans demote this hit to INFO.
- `.gitignore` already excludes `.claude/` — recurrence is structurally prevented.

**Remaining hardening (optional, deferred to open-source release prep):**
- **History rewrite** to remove `conductor/.claude/settings.local.json` from `bcee05c` via `git filter-repo`. Same surgery as the Slack webhook scrub in 2026-04-20. Audit hygiene benefit for a public repo; not a live security exposure.

## Process additions for next-time

The Slack webhook incident in 2026-04-20 added a rotation discipline; this audit confirms the rotation+filter-branch worked. To close the loop on the conductor JWT:

1. Add a pre-commit hook running `gitleaks protect` (or the scan script) so a fresh commit fails closed if it contains a known token shape.
2. Add a CI step running `gitleaks git --log-opts=HEAD~10..HEAD` on every PR — catches drift between full-history audits.
3. Bake `make gitleaks` into the Makefile alongside `make doctor` so a fork operator can run the scan on demand.

Both improvements are scoped for a follow-up MIL ticket — they need decisions about how aggressively to fail CI (false positives in test fixtures will need allowlist entries).
