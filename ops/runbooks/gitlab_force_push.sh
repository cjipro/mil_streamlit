#!/usr/bin/env bash
# gitlab_force_push.sh — recover GitLab `main` after a local rebase
# leaves the dual-remote setup with divergent histories on GitHub vs
# GitLab. Captures protection config, unprotects, force-with-lease
# pushes, re-protects with the EXACT original config.
#
# Why this script exists:
# ----------------------
# CLAUDE.md two-repo contract (MIL-110): `git push origin main` writes
# to BOTH GitHub + GitLab. GitHub is canonical; GitLab is dev-surface
# mirror for Barclays. When `main` is rebased (or `git stash → pull
# --rebase → stash pop` silently drops a commit and you re-commit it),
# GitLab rejects on non-fast-forward AND its `main` is protected, so
# `--force-with-lease` alone fails ("pre-receive hook declined").
#
# This runbook used to be a 3-step manual dashboard click + force-push
# + dashboard click. After 2026-04-28 (MIL-149 deploy), automated via
# GitLab REST API.
#
# Usage:
#   bash ops/runbooks/gitlab_force_push.sh [BRANCH] [EXPECTED_GITLAB_SHA]
#
# Args:
#   BRANCH               default "main"
#   EXPECTED_GITLAB_SHA  the SHA you expect GitLab's BRANCH to be at
#                        right now (the lease value). If GitLab's
#                        BRANCH has drifted to anything else (CI auto-
#                        merge, another agent push), the push rejects
#                        and we re-protect — no overwrite.
#
# Examples:
#   bash ops/runbooks/gitlab_force_push.sh main b0f5617
#   bash ops/runbooks/gitlab_force_push.sh main "$(git rev-parse gitlab/main)"
#
# Requirements:
#   .env carries GITLAB_TOKEN (api scope), GITLAB_BASE_URL=https://gitlab.com,
#     GITLAB_PROJECT_ID
#   Git remote `gitlab` exists and points at the GitLab project.
#   curl + jq + python on PATH (python used as last-resort json reader).
#
# Safety:
#   - Always force-with-lease (never plain --force).
#   - Always restores the EXACT pre-state (push/merge/unprotect access
#     levels, allow_force_push flag, code-owner approval flag).
#   - Refuses if BRANCH != "main" without explicit GITLAB_FORCE_PUSH_OK=1
#     (small papercut to slow blast-radius creep onto release branches).

set -euo pipefail

BRANCH="${1:-main}"
EXPECTED_SHA="${2:-}"

if [[ "$BRANCH" != "main" && "${GITLAB_FORCE_PUSH_OK:-0}" != "1" ]]; then
  echo "Refusing to force-push to non-main branch '$BRANCH'." >&2
  echo "Re-run with GITLAB_FORCE_PUSH_OK=1 if you really mean it." >&2
  exit 2
fi

if [[ -z "$EXPECTED_SHA" ]]; then
  echo "Usage: $0 [BRANCH] [EXPECTED_GITLAB_SHA]" >&2
  echo "EXPECTED_GITLAB_SHA is required — it's the lease value passed to" >&2
  echo "  --force-with-lease. Get it via:" >&2
  echo "    git fetch gitlab && git rev-parse gitlab/main" >&2
  exit 2
fi

# Load .env (avoid printing values).
if [[ ! -f .env ]]; then
  echo "no .env in cwd — run from repo root" >&2
  exit 2
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

: "${GITLAB_TOKEN:?GITLAB_TOKEN missing from .env}"
: "${GITLAB_BASE_URL:?GITLAB_BASE_URL missing from .env}"
: "${GITLAB_PROJECT_ID:?GITLAB_PROJECT_ID missing from .env}"

API="${GITLAB_BASE_URL%/}/api/v4/projects/${GITLAB_PROJECT_ID}/protected_branches"

echo "=== 1. Capture current protection config for '$BRANCH' ==="
CONFIG_JSON="$(mktemp)"
trap 'rm -f "$CONFIG_JSON"' EXIT
curl -sS -o "$CONFIG_JSON" -w "  HTTP %{http_code}\n" \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$API/$BRANCH"

# Extract the four fields we need to restore. Falls back to defaults
# if jq isn't available (python read).
extract_field() {
  local key="$1" default="$2"
  if command -v jq >/dev/null 2>&1; then
    jq -r ".$key // $default" "$CONFIG_JSON" 2>/dev/null || echo "$default"
  else
    python -c "import json,sys; d=json.load(open('$CONFIG_JSON')); print(d.get('$key', $default))" 2>/dev/null || echo "$default"
  fi
}

# push_access_levels[0].access_level (Maintainer=40, Developer=30, Admin=60).
extract_access_level() {
  local key="$1" default="$2"
  if command -v jq >/dev/null 2>&1; then
    jq -r ".${key}[0].access_level // $default" "$CONFIG_JSON" 2>/dev/null || echo "$default"
  else
    python -c "import json,sys; d=json.load(open('$CONFIG_JSON')); arr=d.get('$key', []); print(arr[0]['access_level'] if arr else $default)" 2>/dev/null || echo "$default"
  fi
}

PUSH_LVL="$(extract_access_level push_access_levels 40)"
MERGE_LVL="$(extract_access_level merge_access_levels 40)"
UNPROTECT_LVL="$(extract_access_level unprotect_access_levels 40)"
ALLOW_FORCE="$(extract_field allow_force_push false)"
CODE_OWNER="$(extract_field code_owner_approval_required false)"

echo "  Captured: push=$PUSH_LVL merge=$MERGE_LVL unprotect=$UNPROTECT_LVL force=$ALLOW_FORCE code_owner=$CODE_OWNER"

echo ""
echo "=== 2. Unprotect '$BRANCH' (HTTP 204 expected) ==="
curl -sS -X DELETE -o /dev/null -w "  HTTP %{http_code}\n" \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$API/$BRANCH"

echo ""
echo "=== 3. Force-with-lease push (lease=$EXPECTED_SHA) ==="
PUSH_OUT="$(git push gitlab "$BRANCH" --force-with-lease="$BRANCH:$EXPECTED_SHA" 2>&1)" || PUSH_RC=$?
PUSH_RC="${PUSH_RC:-0}"
echo "$PUSH_OUT" | sed 's/^/  /'

# WHATEVER happened with the push, ALWAYS re-protect. Skipping
# re-protection on push failure would leave main wide open.
echo ""
echo "=== 4. Re-protect '$BRANCH' (HTTP 201 expected) ==="
RESTORE_BODY=$(cat <<EOF
{
  "name": "$BRANCH",
  "push_access_level": $PUSH_LVL,
  "merge_access_level": $MERGE_LVL,
  "unprotect_access_level": $UNPROTECT_LVL,
  "allow_force_push": $ALLOW_FORCE,
  "code_owner_approval_required": $CODE_OWNER
}
EOF
)
curl -sS -X POST -o /dev/null -w "  HTTP %{http_code}\n" \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$RESTORE_BODY" "$API"

echo ""
echo "=== 5. Verify post-state ==="
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$API/$BRANCH" | head -c 600
echo ""

if [[ "$PUSH_RC" -ne 0 ]]; then
  echo ""
  echo "PUSH FAILED (rc=$PUSH_RC) but main was re-protected. Inspect" >&2
  echo "the push output above. Most common cause: the lease SHA you" >&2
  echo "passed is not what GitLab actually had — fetch + rerun:" >&2
  echo "  git fetch gitlab && git rev-parse gitlab/main" >&2
  exit "$PUSH_RC"
fi

echo ""
echo "Done. GitHub + GitLab now in sync."
