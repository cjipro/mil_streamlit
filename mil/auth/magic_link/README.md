# MIL-63 — Magic Link Worker

WorkOS OAuth callback + session cookie issuance for
`login.cjipro.com`. Deploys as a new Worker (`magic-link`) that
lives alongside the existing `login-cjipro` placeholder; route
cutover to `login.cjipro.com/*` is deferred to chunk 3.

## Modules

| File | Responsibility |
|---|---|
| `src/state.ts` | HMAC-signed OAuth `state` param (carries `return_to` + ts). CSRF-resistant, replay-resistant, tamper-evident. Plus `isValidReturnTo` open-redirect guard. |
| `src/authorize.ts` | Build the WorkOS `/oauth2/authorize` URL. |
| `src/exchange.ts` | POST `code` to WorkOS `/user_management/authenticate`, get back the access-token JWT. |
| `src/cookie.ts` | Construct `__Secure-cjipro-session` cookie (Domain=.cjipro.com + HttpOnly + Secure + SameSite=Lax). |
| `src/callback.ts` | Orchestrator — parses `?code&state`, verifies state, exchanges code, returns `{redirect, setCookie}` or `{error}`. |
| `src/index.ts` | Worker fetch handler. Routes: `/`, `/callback`, `/logout`, `/healthz`, `/favicon.ico`, 404 fallback. |
| `src/env.ts` | Env binding types. |

## Routes

| Method + Path | Behaviour |
|---|---|
| `GET /` | Read `?return_to=<path>` (default `/`), validate, sign state, 302 to AuthKit `/oauth2/authorize`. |
| `GET /callback` | Verify state, exchange code for access_token, 302 to `return_to` with `Set-Cookie`. On error render a minimal HTML error page (status 4xx/5xx). |
| `GET /logout` | Clear the session cookie, 302 to `DEFAULT_RETURN_TO`. |
| `GET /healthz` | 200 `ok`. For deployment smoke tests. |
| `GET /favicon.ico` | 204. Prevents browser probe from triggering an auth flow. |
| everything else | 404. |

## Security decisions (load-bearing — do not loosen without panel review)

1. **Signed state param.** HMAC-SHA256 over `{return_to, ts}` with
   `STATE_SIGNING_KEY`. Constant-time signature check.
2. **10-minute state TTL.** Rejects replayed stale states.
3. **`return_to` open-redirect guard.** Rejects `https://…`, `//evil…`,
   `../`, empty. Falls back to `DEFAULT_RETURN_TO` on invalid.
4. **Cookie flags.**
   - `__Secure-` prefix → browser rejects non-HTTPS sets
   - `HttpOnly` → no JS access (XSS mitigation)
   - `SameSite=Lax` — deliberate, NOT `Strict`. A `Strict` cookie
     would NOT ride the top-level redirect back from
     login.cjipro.com to cjipro.com/briefing*, breaking the return
     flow.
   - `Domain=.cjipro.com` → one login covers cjipro.com +
     sonar.cjipro.com + any future subdomain
5. **Cookie name is load-bearing.** `__Secure-cjipro-session` must
   match `SESSION_COOKIE_NAME` on the `edge-bouncer` Worker
   (MIL-61). Renaming requires updating both in lockstep.

## Deployment runbook (manual — requires you)

Secrets are NOT in this repo. You provision them directly on the
Cloudflare side via `wrangler secret put`. The Worker won't start
handling traffic correctly until both are set.

### One-time setup

```bash
cd mil/auth/magic_link
npm install

# 1. Provision WORKOS_CLIENT_SECRET — this is the SAME value as
#    WORKOS_API_KEY in your .env file. Paste it when prompted.
npx wrangler secret put WORKOS_CLIENT_SECRET

# 2. Generate + provision STATE_SIGNING_KEY. Any random 32+ byte
#    string works. One shot:
openssl rand -base64 32 | npx wrangler secret put STATE_SIGNING_KEY
#    (If you don't have openssl on Windows, use PowerShell:
#     [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 })))
```

### Deploy

```bash
npx wrangler deploy
```

First deploy will print the workers.dev URL — something like
`https://magic-link.hussain-marketing.workers.dev`. Confirm this
matches `REDIRECT_URI` in `wrangler.toml` (I've pre-populated it
with that exact URL; if your subdomain differs, edit the toml and
redeploy).

### WorkOS dashboard step

Before the end-to-end flow works, the redirect URI must be
allowlisted on the WorkOS side:

1. Dashboard → Authentication → Redirects
2. Add `https://magic-link.hussain-marketing.workers.dev/callback`
   (the workers.dev URL for now; chunk 3 adds
   `https://login.cjipro.com/callback` alongside it)

### Smoke tests

```bash
# 1. Health check (no secrets or WorkOS involvement)
curl -i https://magic-link.hussain-marketing.workers.dev/healthz
# expect: 200 "ok"

# 2. Authorize redirect — should 302 to ideal-log-65-staging.authkit.app
curl -i "https://magic-link.hussain-marketing.workers.dev/?return_to=/briefing-v4/"
# expect: 302 + Location header pointing at AuthKit

# 3. Browser test — paste the /?return_to=... URL into a browser.
#    AuthKit UI loads, you enter an email, receive a magic-link
#    email, click it, AuthKit redirects to /callback, the Worker
#    exchanges code and 302s to /briefing-v4/ with the session
#    cookie set on .cjipro.com.
```

### What still won't work after chunk 2 deploy

- `login.cjipro.com/*` still routes to the OLD `login-cjipro`
  Worker (MIL-59 placeholder). The new Worker is ONLY reachable at
  the workers.dev URL. Chunk 3 cuts over.
- Edge Bouncer (MIL-61) still runs in `ENFORCE=false` shadow mode.
  Even if a cookie is set, nothing is gated yet.

## Rollback

```bash
npx wrangler delete magic-link
```

Removes the Worker entirely. Cookies already set on
`.cjipro.com` would persist until browser TTL expires — they do no
harm on their own because Edge Bouncer only reads them.

## Chunk 3 cutover — activating login.cjipro.com

Chunk 2 leaves this Worker reachable only at its workers.dev URL.
Chunk 3 cuts `login.cjipro.com/*` over from the MIL-59 placeholder
Worker to this one. The full sequence is inside `wrangler.toml`
alongside the commented-out `[[routes]]` block — it's the
authoritative procedure. Short version:

1. Browser-test the full flow at the workers.dev URL first
2. WorkOS dashboard: add `https://login.cjipro.com/callback` to
   allowed redirect URIs
3. Update `REDIRECT_URI` in wrangler.toml
4. Cloudflare dashboard: remove `login.cjipro.com` custom-domain
   binding from `login-cjipro`
5. Uncomment the `[[routes]]` block → `npx wrangler deploy`
6. `wrangler delete login-cjipro` (or keep as workers.dev fallback)

Rollback is the reverse: comment routes, redeploy, reattach
custom domain to `login-cjipro`. Placeholder returns in <60s.

## Interaction with Edge Bouncer (MIL-61)

`mil/auth/edge_bouncer/` sits in front of cjipro.com/briefing*
and redirects to `login.cjipro.com` when the session cookie is
missing or invalid. That Worker's `wrangler.toml` has commented-
out routes for the four briefing paths — binding them is an
independent decision (safe any time after this Worker is live at
`login.cjipro.com`, because ENFORCE=false means shadow-mode
pass-through). See `mil/auth/edge_bouncer/wrangler.toml` for the
activation checklist.

## Testing

```bash
npm install
npm run typecheck
npm test          # 44 tests / 5 files
```

Tests use `crypto.subtle` (same as the Worker runtime) and stub
`fetch` for WorkOS calls. Integration tests call `worker.fetch()`
directly with a synthetic `Env`.
