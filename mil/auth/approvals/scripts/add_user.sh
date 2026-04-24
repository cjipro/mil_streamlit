#!/usr/bin/env bash
# MIL-66a — add an email to the approved_users allowlist.
#
# Usage:
#   ./add_user.sh <email> <approved_by> [note]
#
# Runs from anywhere; targets the mil-auth-audit D1 via the
# edge_bouncer worker directory (any wrangler.toml that binds
# AUDIT_DB works).

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <email> <approved_by> [note]" >&2
  exit 64
fi

EMAIL=$(echo "$1" | tr '[:upper:]' '[:lower:]' | xargs)
APPROVED_BY="$2"
NOTE="${3:-}"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKER_DIR="$SCRIPT_DIR/../../edge_bouncer"

cd "$WORKER_DIR"

# Use INSERT OR IGNORE so re-running the script on an already-approved
# email is a no-op, not an error. Run an UPDATE too in case the
# approved_by / note fields should refresh.
SQL="INSERT OR IGNORE INTO approved_users (email, approved_at, approved_by, note) VALUES ('$EMAIL', '$TS', '$APPROVED_BY', $([ -z "$NOTE" ] && echo "NULL" || echo "'$NOTE'"));"

echo "Adding $EMAIL..."
npx wrangler d1 execute mil-auth-audit --remote --command "$SQL"
echo "Done. Verify:"
npx wrangler d1 execute mil-auth-audit --remote --command "SELECT * FROM approved_users WHERE email = '$EMAIL';"
