#!/usr/bin/env bash
# MIL-66a — remove an email from the approved_users allowlist.
#
# Usage:
#   ./remove_user.sh <email>
#
# Does NOT touch the audit log — the history of that user's past
# access events remains intact. This only revokes FUTURE access.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <email>" >&2
  exit 64
fi

EMAIL=$(echo "$1" | tr '[:upper:]' '[:lower:]' | xargs)

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKER_DIR="$SCRIPT_DIR/../../edge_bouncer"
cd "$WORKER_DIR"

echo "Removing $EMAIL..."
npx wrangler d1 execute mil-auth-audit --remote \
  --command "DELETE FROM approved_users WHERE email = '$EMAIL';"
echo "Done. Remaining allowlist:"
npx wrangler d1 execute mil-auth-audit --remote \
  --command "SELECT email, approved_at, approved_by FROM approved_users ORDER BY approved_at DESC;"
