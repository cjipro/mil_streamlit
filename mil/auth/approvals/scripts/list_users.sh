#!/usr/bin/env bash
# MIL-66a — list the current approved_users allowlist.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKER_DIR="$SCRIPT_DIR/../../edge_bouncer"
cd "$WORKER_DIR"

npx wrangler d1 execute mil-auth-audit --remote \
  --command "SELECT email, approved_at, approved_by, note FROM approved_users ORDER BY approved_at DESC;"
