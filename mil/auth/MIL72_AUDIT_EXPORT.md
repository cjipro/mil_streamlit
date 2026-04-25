# MIL-72 — Per-Tenant Audit Log Export

Partners' security teams pull a feed of auth events scoped to their
own users, into their SIEM (Splunk, Sentinel, Datadog, etc.). Phase A
shipped: admin pulls the file from the dashboard or via curl, hand-
delivers to the partner. Phase B (signed pre-shared URLs partners can
fetch directly on a cron) follows once a partner asks.

## Endpoint

```
GET https://login.cjipro.com/admin/api/audit_export
  ?org=<org_id>
  &since=<iso8601>     (default: 7 days ago)
  &until=<iso8601>     (default: now)
  &format=jsonl|csv    (default: jsonl)
```

Auth: same gate as the rest of `/admin/*` — caller's session JWT
must verify and their email must be in `admin_users`. Non-browser
callers attach the session cookie they got from /callback.

Response headers:
- `content-type` — `application/x-ndjson` or `text/csv; charset=utf-8`
- `content-disposition` — `attachment; filename="audit_<org>_<since>_<until>.<ext>"`
- `x-row-count` — number of events in the export (handy for the
  partner's ingestion pipeline to verify expected volume)
- `cache-control` — `no-store`

## Dashboard usage

Sign in at `https://login.cjipro.com/admin` → scroll to **Per-tenant
audit export** → fill in:
- Org id (from WorkOS dashboard, e.g. `org_01HXYZ...`)
- Since (datetime, default last 7 days)
- Until (datetime, default now)
- Format (jsonl / csv)

Click Download. Browser saves the file with the auto-generated name.

## What's INCLUDED in a tenant export

Every `auth_events` row whose `user_hash` resolves back to a `sub`
present in `sessions` with `organization_id = <org>`. By event_type:

- `bouncer.pass.session` — the user accessed a briefing
- `bouncer.deny.not_approved` — a sign-in passed JWT but their email
  isn't on the allowlist
- `bouncer.redirect.invalid` — JWT verification failed (bad/expired)
- `bouncer.rate_limited` — Cloudflare WAF challenged + passed through
- `magic_link.callback.success` / `magic_link.callback.error` —
  sign-in flow completion
- `magic_link.logout`
- `dsync.user.*` — SCIM provisioning / deprovisioning of users in
  this org
- `connection.activated` / `connection.deactivated` /
  `connection.deleted` — SAML connection lifecycle
- `signup.request` — only if the requester later signed in and
  their session was tied to this org (rare)

## What's EXCLUDED

- `admin.*` events (your governance, not the partner's)
- `bouncer.pass.public` (no user attached — landing page hits)
- `signup.request` events from people who never signed in
- All internal hash columns (`user_hash`, `ip_hash`, `ua_hash`,
  `prev_hash`, `row_hash`) — partners don't need our salts
- Events from before the org's first user signed in (sessions row
  didn't exist; user_hash can't be matched back)

The export contains: `id, ts, worker, event_type, method, host,
path, enforce, country, reason, detail`. JSONL has one event per
line; CSV has a header row and standard escaping.

## Sharing with a partner SOC

For one-shot delivery (typical for alpha):
1. Pull the file from the dashboard.
2. SHA256 it locally:
   ```bash
   shasum -a 256 audit_org_01HXYZ_2026-04-18_2026-04-25.jsonl
   ```
3. Send via your usual secure file-transfer channel (S/MIME email,
   secure document portal, etc.). Include the SHA256 separately so
   the partner can verify integrity.
4. Note in the cover message: "events older than `<earliest_ts>`
   may not be in this export — `last_active_at` tracking started
   after MIL-68 (2026-04-25)".

For recurring delivery (Phase B will automate this):
- Until Phase B ships, schedule a `wrangler` job in your environment
  that hits the API with curl + a saved session cookie + writes the
  result to wherever the partner pulls from. The audit log records
  every export as `admin.audit_export` so you can prove cadence.

## Backfill caveat

`organization_id` on sessions only populates for sign-ins AFTER the
MIL-72 deploy (2026-04-25). Earlier sign-ins have NULL org_id and
won't match in the export query. To backfill an org's existing users:

1. Query `sessions` for null org_ids belonging to known partner emails.
2. Update them in-place via `wrangler d1 execute`:
   ```sql
   UPDATE sessions
   SET organization_id = 'org_01HXYZ...'
   WHERE email IN ('alice@partnerbank.com', 'bob@partnerbank.com')
     AND organization_id IS NULL
   ```

## Example curl

```bash
COOKIE="__Secure-cjipro-session=<paste-from-browser-devtools>"
curl -s -H "cookie: $COOKIE" \
  "https://login.cjipro.com/admin/api/audit_export?org=org_01HXYZ&format=jsonl" \
  > audit_export.jsonl
wc -l audit_export.jsonl
head -1 audit_export.jsonl | jq .
```

If you get a 302 → your cookie's expired (re-sign-in). If you get
403 → your email isn't in `admin_users`.

## Operational notes

- The query rebuilds user_hash for every (sub × day) in the window,
  so a 30-day window with 5 users in the org = 150 sha256 calls per
  request. Trivial compute, but query latency grows linearly with
  window size. For windows over 90 days, expect a few seconds.
- D1 query response is materialized in memory before formatting —
  for a tenant with millions of events, paginate via tighter `since`
  / `until` windows.
- Phase B will likely move to a streamed response with a cursor
  parameter for unbounded windows. Filed as a follow-up if/when a
  partner needs it.

## Phase B (deferred, not in this commit)

- Signed pre-shared URLs partners can pull on a cron without admin
  involvement. Token rotation via the existing audit-log timeline.
- Webhook-style push delivery (we POST to the partner's endpoint
  with HMAC signature, mirroring how WorkOS pushes to us).
- Cursor-paginated streaming for very large tenants.
