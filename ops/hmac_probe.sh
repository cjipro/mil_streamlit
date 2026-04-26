#!/usr/bin/env bash
# Reads the WorkOS signing secret from stdin (silent prompt), then
# computes HMAC-SHA256 over the exact (timestamp.body) string captured
# from the failed delivery — and prints the first 12 hex chars to
# compare against:
#   WorkOS sent:  c6178e688bc1
#   We computed:  84c0cdd468f5
# If your local computation matches WorkOS's, the secret is correct
# and the Worker has stale/wrong bytes. If it matches ours, the
# secret on your clipboard equals the one on the Worker (so neither
# matches what WorkOS actually used to sign).
set -e

TS="1777225683723"
# Body captured from the failed delivery (matches body_first16 +
# body_last16 in the diagnostic log; total 383 bytes).
BODY='{"id":"event_01HS2EAGQA9EZW6D0MFCV5S38D","data":{"type":"email_verification","email":"todd@example.com","status":"succeeded","user_id":"user_01EHWNC0FCBHZ3BJ7EGKYXK0E6","ip_address":"0.0.0.0","user_agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X x.y; rv:42.0) Gecko/20100101 Firefox/42.0"},"event":"authentication.email_verification_succeeded","created_at":"2024-03-02T19:07:33.155Z"}'

echo "Body length: ${#BODY} bytes (diagnostic said 383)"

read -s -p "Paste your WorkOS signing secret then hit Enter (input hidden): " SECRET
echo
echo "Secret length: ${#SECRET} chars (diagnostic said 47)"

PAYLOAD="${TS}.${BODY}"
HMAC=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" -hex | sed 's/^.*= //')

echo "HMAC prefix:   ${HMAC:0:12}"
echo "WorkOS sent:   c6178e688bc1"
echo "Worker has:    84c0cdd468f5"
