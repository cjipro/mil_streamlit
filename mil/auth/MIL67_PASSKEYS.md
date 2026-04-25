# MIL-67 — WebAuthn / Passkeys runbook

Adds biometric / hardware-key auth (TouchID, FaceID, Windows Hello,
YubiKey, etc.) on top of the existing WorkOS AuthKit flow. Phase A
delegates the cryptographic ceremony to WorkOS — they store credentials,
prompt enrollment, and handle assertion. Our code only ingests the
resulting events for audit + observability.

## Phase A — admin steps

### 1. Enable WebAuthn in WorkOS

WorkOS dashboard → User Management → **Authentication methods** →
toggle **Passkey** on. (Already-signed-in users get an enrollment
prompt next time they hit AuthKit; new users get the prompt during
their first sign-in.)

No code change needed for this step. AuthKit handles the entire
ceremony.

### 2. Configure the webhook

WorkOS dashboard → **Webhooks** → Add Endpoint:

- URL: `https://login.cjipro.com/webhooks/workos`
- Events: subscribe to **all** for now (we filter in code; once we
  see the actual event types in our audit log we narrow the
  subscription).
- After saving, click "Reveal signing secret" — copy it.

### 3. Set the secret on the magic-link Worker

```bash
cd mil/auth/magic_link
npx wrangler secret put WORKOS_WEBHOOK_SECRET
# paste the secret when prompted
```

### 4. Verify it works

Trigger any event (e.g. sign in fresh — `authentication.success` will
fire). Check the audit log:

```bash
cd mil/auth/edge_bouncer
npx wrangler d1 execute mil-auth-audit --remote --json --command \
  "SELECT id, ts, reason, detail FROM auth_events
   WHERE event_type = 'workos.webhook'
   ORDER BY id DESC LIMIT 10"
```

Each row's `reason` column = the WorkOS event type string
(e.g. `authentication.passkey_registered`). `detail` = the WorkOS
event id (`evt_...`) so you can correlate against the dashboard.

## Phase B — what we'll do once events flow

After ~24h of webhook traffic we'll see the actual event-type names
WorkOS uses. Phase B will:

1. Split `workos.webhook` into typed events:
   `passkey.registered`, `passkey.used`, `authentication.success`, etc.
2. Add a `Passkey?` column to the admin dashboard, joined from a
   `user_security(sub, passkey_enrolled, last_used_at)` table updated
   by webhook events.
3. Optionally narrow the WorkOS webhook subscription to just the
   events we route — reduces noise in the audit table.

## Failure modes

- **`WORKOS_WEBHOOK_SECRET` not set** → endpoint returns 503. Set the
  secret as in step 3.
- **Replay window exceeded (>5min skew)** → 401. Could be clock drift;
  check Cloudflare's edge clock vs WorkOS's. WorkOS retries automatically.
- **Signature mismatch** → 401. Either secret is wrong or the body
  was tampered between WorkOS and us. Cloudflare Tunnel doesn't
  modify bodies; if this fires, rotate the WorkOS secret + update
  via `wrangler secret put`.
- **Audit DB unreachable** → the audit write is fire-and-forget via
  `ctx.waitUntil`. The 200 ack still goes back to WorkOS. The event
  is lost from our timeline but not from WorkOS's; query their
  webhook log to recover.

## Security properties

- Signature verification is mandatory — no secret = no acceptance.
  Even an attacker who knows the URL can't post fake events.
- Replay protection via 5-minute timestamp window.
- Constant-time HMAC compare in `webhooks.ts::constantTimeEqual`.
- We never authenticate users via webhook events — they only enrich
  the audit timeline. The bouncer + admin gate still verify the
  WorkOS-signed session JWT directly. A compromised webhook secret
  would let an attacker fabricate audit entries but not impersonate
  anyone.
