#!/usr/bin/env bash
# MIL-61 post-flip monitor — detects "stuck" sign-in attempts.
#
# Counts magic_link.authorize events in the last 24h and checks how
# many were followed by a callback.success or callback.failure from
# the same ip_hash within +30 minutes. Authorize events with no
# callback at all are "stuck" — most likely failure modes:
#   1. Corp proxy blocked redirect to login.cjipro.com
#   2. Magic-link email never delivered
#   3. User abandoned mid-flow (legitimate, harder to filter out)
#
# A persistently-high stuck-rate after MIL-61 ENFORCE flip is the
# signal that lightweight MIL-62 testing should run urgently.
set -e

cd "$(dirname "$0")/../mil/auth/edge_bouncer"

SQL='WITH recent_authorize AS (
  SELECT id, ts, ip_hash FROM auth_events
  WHERE event_type = "magic_link.authorize" AND ts > datetime("now", "-1 day")
),
recent_callback AS (
  SELECT id, ts, ip_hash FROM auth_events
  WHERE event_type IN ("magic_link.callback.success", "magic_link.callback.failure")
    AND ts > datetime("now", "-1 day", "-30 minutes")
),
classified AS (
  SELECT
    a.id, a.ts, a.ip_hash,
    CASE WHEN EXISTS (
      SELECT 1 FROM recent_callback c
      WHERE c.ip_hash = a.ip_hash
        AND datetime(c.ts) BETWEEN datetime(a.ts) AND datetime(a.ts, "+30 minutes")
    ) THEN 1 ELSE 0 END AS has_callback
  FROM recent_authorize a
)
SELECT
  COUNT(*) AS total_authorize_24h,
  SUM(has_callback) AS completed_24h,
  COUNT(*) - SUM(has_callback) AS stuck_24h,
  ROUND(100.0 * SUM(has_callback) / NULLIF(COUNT(*), 0), 1) AS completion_rate_pct
FROM classified;'

# datetime() normalisation on both sides of BETWEEN is load-bearing.
# Without it, raw ts strings ("...T19:50:13.443Z") compare lexicographically
# against the rewritten upper bound ("...20:20:13" with space separator),
# T = 0x54 vs space = 0x20 makes upper < lower, range collapses, all
# matches fall through.

RESP=$(npx wrangler d1 execute mil-auth-audit --remote --json --command "$SQL" 2>&1)
echo "$RESP"

if command -v jq >/dev/null 2>&1; then
  STUCK=$(echo "$RESP" | jq -r '.[0].results[0].stuck_24h // 0' 2>/dev/null || echo 0)
  TOTAL=$(echo "$RESP" | jq -r '.[0].results[0].total_authorize_24h // 0' 2>/dev/null || echo 0)
  RATE=$(echo "$RESP" | jq -r '.[0].results[0].completion_rate_pct // 100' 2>/dev/null || echo 100)
  echo
  echo "=== Summary ==="
  echo "  Total sign-in attempts (24h): $TOTAL"
  echo "  Stuck (no callback in 30m):   $STUCK"
  echo "  Completion rate:              $RATE %"

  # NB: stuck-rate is currently noisy because (a) MIL-61 ENFORCE flip
  # makes every visit to cjipro.com/briefing* redirect through
  # login.cjipro.com which fires authorize even for bots / link-preview
  # crawlers / abandoned tabs, and (b) we have no real alpha traffic
  # yet. Don't threshold the rate until you have a clean week-on-week
  # baseline. For now the meaningful signal is: did `completed_24h`
  # tick up after a real partner test? If yes, system works.
  echo
  echo "Track these numbers over time. After onboarding a real partner:"
  echo "  - completed_24h should go up"
  echo "  - if completed_24h stays at zero while a known partner tries to sign in,"
  echo "    that is a corp-proxy failure — apply MIL-62 lightweight smoke runbook."
fi
