# GitLab token rotation — MIL-111

Rotates the credential used for the GitLab read-mirror (dual-push +
Jira-issue archive). Migrates from a user-scoped Personal Access Token
to a project-scoped Project Access Token — same blast-radius rotation
for cjipro.com, lower blast radius for any fork that retargets to its
own GitLab instance.

This runbook is **operator-action gated** — Claude cannot create the new
token in your GitLab UI. Steps below are the canonical sequence; copy
and run them top-to-bottom.

## Why migrate from user PAT to Project Access Token

| Token type | Scope | Blast radius | Supports |
|---|---|---|---|
| **User PAT** | All projects the user can access | Compromise → attacker has full user rights across every project | git + API |
| **Project Access Token** | Single project | Compromise → attacker has only the project's scopes | git + API |
| **Deploy Token** | Single project, repository ops only | Lowest blast radius | git only (no API) |

Deploy tokens would be ideal but cannot run the API endpoints
`gitlab_force_push.sh` and `import_jira_to_gitlab.py` need
(`/api/v4/projects/{id}/protected_branches`, `/api/v4/projects/{id}/issues`).
Project Access Tokens are the right choice: project-scoped + API-capable.

## What the token is used for

| Consumer | Scope needed | Purpose |
|---|---|---|
| `git push origin main` (dual-push) | `write_repository` | Mirror commits from GitHub canonical to GitLab |
| `ops/gitlab_import/import_jira_to_gitlab.py` | `api` | Create + read GitLab Issues mirroring Jira state |
| `ops/runbooks/gitlab_force_push.sh` | `api` | Unprotect/protect `main` during rebase-recovery force-pushes |

A single token with `api` + `write_repository` covers all three. `api`
is a superset; `write_repository` is included redundantly because the
git push doesn't go through `/api/`.

## Rotation procedure

### 1. Generate the new Project Access Token

1. Go to **https://gitlab.com/streaming-analytics/while-sleeping/-/settings/access_tokens**
2. Click **Add new token**
3. Name: `cjipro-mirror-2026-04-30` (date-stamped — makes future rotations easier to track)
4. Expiry: pick 1 year out (GitLab Free maximum). Calendar a reminder to rotate again before expiry.
5. Role: **Maintainer** (needed for protected-branch admin via API)
6. Scopes:
   - `api` (covers Jira-import + force-push API calls)
   - `write_repository` (covers dual-push)
7. Click **Create**
8. **Copy the token immediately** — GitLab shows it once.

### 2. Update `.env`

Replace the existing `GITLAB_TOKEN` value:

```bash
# Edit .env at the repo root
GITLAB_TOKEN=<paste new token>
GITLAB_BASE_URL=https://gitlab.com
GITLAB_PROJECT_ID=80021701
```

The env var name does not change — every consumer reads `GITLAB_TOKEN`.

### 3. Verify dual-push works

Make a no-op commit (e.g. amend a comment in this runbook) and push:

```bash
git push origin main
```

Expected output:

```
To https://github.com/cjipro/mil_streamlit.git
   <range>  main -> main
To https://gitlab.com/streaming-analytics/while-sleeping.git
   <range>  main -> main
```

If GitLab side fails with `HTTP 401 Unauthorized`, the token isn't being
picked up. Check the remote URL:

```bash
git remote -v
```

The GitLab push URL should contain the token:
`https://oauth2:<token>@gitlab.com/streaming-analytics/while-sleeping.git`.
If it's stale, rewrite it:

```bash
git remote set-url --push --add origin "https://oauth2:$GITLAB_TOKEN@gitlab.com/streaming-analytics/while-sleeping.git"
```

### 4. Verify API calls work

Test the issue-listing endpoint that `import_jira_to_gitlab.py` uses:

```bash
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "$GITLAB_BASE_URL/api/v4/projects/$GITLAB_PROJECT_ID/issues?per_page=1" | head -c 200
```

Expected: a JSON array beginning with `[{...`. Failure mode is `{"message":"401 Unauthorized"}` — token doesn't have `api` scope or wasn't pasted correctly.

Test the protected-branch endpoint that `gitlab_force_push.sh` uses:

```bash
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "$GITLAB_BASE_URL/api/v4/projects/$GITLAB_PROJECT_ID/protected_branches/main" | head -c 200
```

Expected: a JSON object with `"name":"main"`. Failure mode is `403 Forbidden` — token doesn't have Maintainer role.

### 5. Revoke the old PAT

Once steps 3 + 4 confirm the new token works:

1. Go to **https://gitlab.com/-/user_settings/personal_access_tokens**
2. Find the old token (or any tokens with names like `cjipro-mirror-*` from before this rotation).
3. Click **Revoke**.

**Do not skip this step.** A successful rotation that leaves the old credential live is half a rotation — the old token still works until the user explicitly revokes.

### 6. Log the rotation

Append to `ops/security_audit/token_rotations.log` (create if missing):

```
2026-04-30  GITLAB_TOKEN  user-PAT -> project-access-token  cjipro-mirror-2026-04-30  Hussain
```

Future audits read this log to track rotation cadence.

## Rollback

If the new token doesn't work and rotation needs to be undone:

1. Generate a *new* user PAT with `api` + `write_repository` scopes (same as the old one).
2. Paste into `.env` `GITLAB_TOKEN`.
3. Verify dual-push + API calls (steps 3 + 4 above).
4. **Revoke** any project access tokens created during the failed migration.

The old PAT cannot be un-revoked — if you've already revoked it in step 5,
generating a new PAT is the only path back.

## What the token does NOT cover

- `gitlab.com/oauth2` for GitLab UI sign-in (different auth domain)
- CI/CD runner registration (uses runner registration tokens, separate)
- GitLab Pages deploys (we don't use GitLab Pages — public surfaces are GitHub Pages)

If a fork needs CI/CD, registration tokens are configured separately under
**Settings → CI/CD → Runners**. Out of scope for this rotation.
