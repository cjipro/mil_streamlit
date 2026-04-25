# MIL-110 Runbook — Make `cjipro/mil_streamlit` private

**Source:** Tavis Ormandy panel review, 2026-04-25 — top finding.
**Threat:** Public code repo exposes the auth stack (edge-bouncer + magic-link Worker source, JWKS URLs, cookie name, D1 table names, runbook contents, Worker version IDs, scheduled trigger IDs) — enough material to script a pixel-perfect AuthKit phishing email.
**Fix:** flip `cjipro/mil_streamlit` to private. The Pages repo `cjipro/mil-briefing` (where rendered HTML is served from) stays public — it has no sensitive content (verified by `scripts/check_public_repo_hygiene.py`).

This runbook is the pre-flip → click → post-flip checklist.

---

## Pre-flip checks (run first)

1. **Pages repo is clean.** Run the hygiene scanner:
   ```bash
   py scripts/check_public_repo_hygiene.py
   ```
   Expected: `RESULT: CLEAN`. If it reports findings, remediate before flipping anything (otherwise you've still got a public attack surface after the flip).

2. **Publish chain still works.** Trigger the dual-publish path manually:
   ```bash
   py run_daily.py --step 5e
   ```
   Expected: pushes `sonar/barclays/index.html` and `sonar/barclays/{today_utc}/index.html` to `cjipro/mil-briefing`. The push uses `GITHUB_TOKEN` from `.env` against the Pages repo, not the code repo, so it's unaffected by the visibility flip.

3. **GitLab snapshot mirror is current.** From repo root:
   ```bash
   git push origin main      # dual-pushes to GitHub + GitLab
   git log --oneline -5      # confirm latest commits
   ```
   GitLab continues to mirror after the GitHub flip.

4. **No external readers depend on the public GitHub URL.** Check:
   - No external blog posts / docs link to `github.com/cjipro/mil_streamlit/...`
   - No Cloudflare Worker / GitHub Action / external CI pulls from the public repo (Cloudflare Workers fetch from `cjipro/mil-briefing` Pages, not from the code repo).
   - `gh issue list -R cjipro/mil_streamlit` — typically empty; if not, decide whether to migrate issues to a public-by-design tracker.

5. **Plan secret rotation** (MIL-112). Even after the flip, treat the code repo's git history as compromised — anyone who cloned before the flip retains a copy. Targets:
   - GitLab PAT (currently `glpat-...` in your local `.git/config`) → MIL-111
   - WorkOS API key (`WORKOS_API_KEY` in `.env`) → rotate via WorkOS dashboard
   - `STATE_SIGNING_KEY` (magic-link Worker secret) → `wrangler secret put`
   - `SMTP_APP_PASSWORD` → revoke + regenerate Gmail app password
   - `GITHUB_TOKEN` (Pages publish token) → regenerate
   - `CLOUDFLARE_API_TOKEN` → roll the existing `cjipro-mil-cli` per `feedback_cloudflare_token_rotate.md` (do not create a parallel token)
   - `WORKOS_WEBHOOK_SECRET` → regenerate via WorkOS dashboard

   These rotations don't have to land before the flip; the flip is the highest-leverage move and stops new attackers from reading the surface. Rotation closes the residual window.

---

## The flip (single click)

1. Open `https://github.com/cjipro/mil_streamlit/settings`.
2. Scroll to **Danger Zone** → **Change repository visibility**.
3. Click **Change visibility** → **Make private** → confirm by typing the repo name.
4. GitHub will warn you about losing public stars and forks. You have neither (this is a private project), so confirm.

The repo is now private. Anyone without explicit collaborator access (i.e., everyone) gets 404 on `github.com/cjipro/mil_streamlit/...`.

---

## Post-flip verification (run within 5 minutes)

1. **Verify private.** Open an incognito window and try to load `https://github.com/cjipro/mil_streamlit`. Expected: GitHub 404 / "you don't have access" page.

2. **Verify cjipro.com still serves.**
   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" https://cjipro.com/briefing-v4/
   curl -sS -o /dev/null -w "%{http_code}\n" https://cjipro.com/sonar/barclays/
   curl -sS -o /dev/null -w "%{http_code}\n" https://cjipro.com/
   ```
   Expected: all `200`. The visibility flip only affects the code repo. Pages serves from `cjipro/mil-briefing` (still public).

3. **Verify Workers still serve.**
   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" https://app.cjipro.com/healthz
   curl -sS -o /dev/null -w "%{http_code}\n" https://app.cjipro.com/sonar/barclays/
   curl -sS -o /dev/null -w "%{http_code}\n" https://login.cjipro.com/
   ```
   Expected: all `200`. Workers were deployed from local `wrangler deploy`, not pulled from the GitHub repo, so visibility doesn't affect them.

4. **Verify your local clone still pushes.** After the flip your local push uses `GITHUB_TOKEN` (or PAT, or SSH key) — same auth as before. Test:
   ```bash
   git commit --allow-empty -m "test(MIL-110): post-private push smoke"
   git push origin main
   ```
   Expected: push succeeds. If it fails with auth errors, re-add the token to your `.git/config` or `~/.gitconfig`.

5. **Hygiene scanner still works.**
   ```bash
   py scripts/check_public_repo_hygiene.py
   ```
   Expected: `RESULT: CLEAN`. The scanner targets `cjipro/mil-briefing` (still public), so it should run unchanged.

6. **Close MIL-110 in Jira UI.** With all five checks green.

---

## If it goes wrong (rollback)

The flip is reversible. From the same Settings → Danger Zone page, click **Change visibility** → **Make public** → confirm. The repo is public again within seconds. No data loss; no history rewrite.

Caveats:
- During the private window, anyone who tried to `git pull` from the public URL got 404 — they don't get those commits delivered, but they can pull again after the flip-back.
- GitHub Pages serving from `cjipro/mil_streamlit` would have broken — but **we don't serve Pages from `mil_streamlit`**, we serve from `mil-briefing`. So nothing to recover.

---

## Defense-in-depth landed alongside this runbook

Three pieces of code shipped with MIL-110 that make this runbook safer to repeat (e.g., when MIL-73 renames the code repo to `cji-pro`):

1. **Path deny-list in `mil/publish/adapters.py`** (`SENSITIVE_PATH_PATTERNS` + `assert_publishable()`). `GitHubPagesAdapter.publish()` refuses any path matching `mil/auth/`, `ops/runbooks/`, `scripts/`, source-code extensions (`.py`, `.ts`), top-level docs (`CLAUDE.md`, `MEMORY.md`), or secret files (`.env*`, `secrets.*`). 56 unit tests in `mil/tests/test_publish_deny_list.py`.

2. **Hygiene scanner `scripts/check_public_repo_hygiene.py`.** Standalone scan over the live Pages repo. Two checks: path-policy (16 patterns, source-shared with the deny-list) + content-policy (20 patterns: D1 UUIDs, Org/Client IDs, API tokens, env-var literals, scheduled-trigger IDs).

3. **Two-repo contract documented in `CLAUDE.md`** under "Repo host" — explicit declaration of what's public vs private, and the rule that nothing in `mil/auth/`, runbooks, or top-level docs ever ships to Pages.

---

## Out-of-scope for this ticket (separate tickets)

- **MIL-111** — rotate GitLab PAT to a project-scoped deploy token. Currently `glpat-...` in local `.git/config`.
- **MIL-112** — full git-history scrubbing of `mil_streamlit` if needed (trufflehog + gitleaks audit, then targeted `git filter-repo`). Highest-leverage path is "make private + treat history as compromised + rotate everything" rather than rewriting history (which can break clones and tags).
- **MIL-73** — rename the now-private `cjipro/mil_streamlit` to `cjipro/cji-pro`. Hard-gated post-2026-05-01.
- Soften marketing copy on `security/architecture/index.html:753` that names the `admin_users` D1 table — file as a small follow-up ticket if you want to close the low-severity finding from the MIL-110 audit.
