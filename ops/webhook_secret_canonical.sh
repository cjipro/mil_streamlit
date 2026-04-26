#!/usr/bin/env bash
# Canonical secret upload + verify path. Eliminates clipboard drift
# by sourcing the secret from a single file.
set -e

SECRET_FILE="${1:-/tmp/workos_signing_secret.txt}"
if [ ! -f "$SECRET_FILE" ]; then
  echo "Secret file not found: $SECRET_FILE"
  echo
  echo "First, save the WorkOS signing secret to that file:"
  echo "  1. Open WorkOS dashboard → Webhooks → your endpoint"
  echo "  2. F12 → Network tab → Click 'Reveal' on the signing secret"
  echo "  3. In the Network tab, click the new request"
  echo "  4. Open Response/Preview tab — find the field with the full secret"
  echo "  5. Copy the secret value (just the value, no quotes/braces)"
  echo "  6. Open Notepad or VS Code, paste the secret, save as:"
  echo "     C:\\Users\\hussa\\AppData\\Local\\Temp\\workos_signing_secret.txt"
  echo "     (Save as type 'All Files' to avoid .txt.txt double extension)"
  echo "  7. Re-run this script: bash ~/while-sleeping/ops/webhook_secret_canonical.sh"
  exit 1
fi

# Strip any trailing newline that text editors append
SECRET=$(cat "$SECRET_FILE" | tr -d '\r\n')
LEN=${#SECRET}
FIRST=${SECRET:0:1}
LAST=${SECRET: -1:1}

echo "Sourced from: $SECRET_FILE"
echo "Length:       $LEN chars"
echo "First char:   $FIRST"
echo "Last char:    $LAST"
echo

# Show any non-printable bytes for diagnostics
echo "Hidden characters check (look for ^I, ^M, $ at line ends):"
cat -A "$SECRET_FILE" | head -3
echo

read -p "Continue with upload? [y/N] " ok
if [ "$ok" != "y" ]; then
  echo "Aborted."
  exit 0
fi

# Source CLOUDFLARE_API_TOKEN from .env so wrangler's non-interactive
# stdin path can authenticate. Without this, piping fails with
# "non-interactive environment ... CLOUDFLARE_API_TOKEN required".
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "WARN: CLOUDFLARE_API_TOKEN not set after sourcing .env."
  echo "      Wrangler may fall through to OAuth (requires DNS to dash.cloudflare.com)."
fi

cd "$(dirname "$0")/../mil/auth/magic_link"
echo "$SECRET" | npx wrangler secret put WORKOS_WEBHOOK_SECRET

echo
echo "Upload complete. The secret on disk should now be exactly $LEN chars."
echo "Run the probe to confirm: bash ~/while-sleeping/ops/hmac_probe.sh"
echo "(in the probe, paste the SAME secret — they will both match this file)"
