#!/usr/bin/env bash
cd "$(dirname "$0")/../mil/auth/magic_link" || exit 1
exec npx wrangler secret put WORKOS_WEBHOOK_SECRET
