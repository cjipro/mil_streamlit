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

## Real finding — Astronomer.io JWT in conductor settings

**File:** `conductor/.claude/settings.local.json` (a Claude Code per-project settings file from a nested sub-project)
**Commit:** `bcee05c3351052164ade57364e1ca399b96ce1f9`
**Date:** 2026-03-18
**Author:** Hussain
**Issue type:** Auth token committed alongside an unrelated PULSE-migration sync commit.

**Current state:**
- `.gitignore` already excludes `.claude/` — this can't recur on a fresh commit, only the historical commit retains the value.
- The token's expiry is unknown. JWTs typically have a finite `exp` claim; a 6-week-old token may already be dead. Decoding here was deliberately avoided to prevent re-leaking.

**Remediation options:**

1. **Rotate the Astronomer credential** in your Astronomer dashboard, regardless of expiry status. This invalidates the leaked token even if it hasn't naturally expired. Recommended.
2. **Confirm expiry** by decoding the JWT locally (`echo "<token>" | cut -d. -f2 | base64 -d | jq .exp`) — if the `exp` claim is in the past, the token is already dead.
3. **(Optional) Rewrite history** to remove the file from `bcee05c`. This requires `git filter-repo` or `git filter-branch`, the same surgery done for the Slack webhook in 2026-04-20. Coordinate the rewrite with any GitLab mirror force-push.

The minimum action that closes this finding is option 1 (rotate). Option 3 is a hardening step for the open-source release, where a public-repo audit would re-flag this file.

## Process additions for next-time

The Slack webhook incident in 2026-04-20 added a rotation discipline; this audit confirms the rotation+filter-branch worked. To close the loop on the conductor JWT:

1. Add a pre-commit hook running `gitleaks protect` (or the scan script) so a fresh commit fails closed if it contains a known token shape.
2. Add a CI step running `gitleaks git --log-opts=HEAD~10..HEAD` on every PR — catches drift between full-history audits.
3. Bake `make gitleaks` into the Makefile alongside `make doctor` so a fork operator can run the scan on demand.

Both improvements are scoped for a follow-up MIL ticket — they need decisions about how aggressively to fail CI (false positives in test fixtures will need allowlist entries).
