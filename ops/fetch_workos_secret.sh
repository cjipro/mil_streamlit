#!/usr/bin/env bash
# Fetch the WorkOS webhook signing secret directly from the API
# using the account API key. Bypasses the dashboard UI entirely
# so what we see is exactly what WorkOS holds server-side.
set -e

# Source .env to get WORKOS_API_KEY
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi

KEY="${WORKOS_API_KEY:-${WORKOS_CLIENT_SECRET:-}}"
if [ -z "$KEY" ]; then
  echo "WORKOS_API_KEY not found in .env. Set it (sk_test_... value from WorkOS dashboard → API Keys) and retry."
  exit 1
fi

echo "Listing all webhook endpoints in this WorkOS environment …"
RESP=$(curl -s -H "Authorization: Bearer $KEY" \
  "https://api.workos.com/webhook_endpoints")

if command -v jq >/dev/null 2>&1; then
  echo "$RESP" | jq .
  echo
  echo "Signing secrets (id → secret):"
  echo "$RESP" | jq -r '.data[] | "\(.id)  len=\(.signing_secret | length)  first6=\(.signing_secret[:6])"'
else
  echo "Raw response:"
  echo "$RESP"
fi
