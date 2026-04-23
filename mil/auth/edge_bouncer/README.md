# MIL-61 — Edge Bouncer

Cloudflare Worker that gates cjipro.com + sonar.cjipro.com behind a
WorkOS session JWT.

Three jobs, in order:
1. **Public allowlist** — `/`, `/privacy*`, `/.well-known/*`,
   `/robots.txt`, `/sitemap.xml`, `/.nojekyll` pass unconditionally.
   (Apr 23 Barclays corp-proxy lesson: these MUST stay public.)
2. **Session check** — reads `__Secure-cjipro-session` cookie,
   verifies JWT signature against the WorkOS JWKS, checks `iss` +
   `aud`.
3. **Redirect on miss** — 302 to `https://login.cjipro.com/?return_to=<path>`.

The Worker does not itself serve any content — it either passes
through to origin (`fetch(request)`) or returns a 302.

## Feature flag

`ENFORCE=false` (default) puts the Worker in **shadow mode**:
decisions are logged but the Worker always passes through. Flip to
`ENFORCE=true` on the day MIL-63 (magic-link flow) ships and actual
session cookies start being set — not before.

## Local dev

```
cd mil/auth/edge_bouncer
npm install
npm run typecheck
npm test
npm run dev      # runs wrangler dev against Cloudflare's local sim
```

## Deployment

Route binding is intentionally commented out in `wrangler.toml` —
activate when ready. Deployment is a three-step operation the
first time:

1. **Deploy the Worker** (no routes yet):
   ```
   npx wrangler deploy
   ```

2. **Bind routes** by uncommenting the four `[[routes]]` blocks in
   `wrangler.toml` and running `npx wrangler deploy` again. That
   attaches the Worker to:
   - `cjipro.com/briefing*`
   - `cjipro.com/briefing-v2*`
   - `cjipro.com/briefing-v3*`
   - `cjipro.com/briefing-v4*`

   `sonar.cjipro.com/*` is DEFERRED — binding here would intercept
   the Ask CJI Pro tunnel at `/api/*`. MIL-54 retires the sonar
   Cloudflare Access policy; we revisit then.

3. **Verify shadow mode** — tail logs:
   ```
   npx wrangler tail
   ```
   Hit `https://cjipro.com/briefing-v4/` anonymously. Expect a log
   line `{"action":"redirect","reason":"missing", ...}` followed by
   the origin content loading normally (because `ENFORCE=false`).

4. **Flip enforcement** — only after MIL-63 ships and you've seen at
   least one successful magic-link login set the cookie. Then:
   ```
   npx wrangler deploy --var ENFORCE:true
   ```

## Environments

`wrangler.toml` currently hardcodes the **staging** WorkOS values
from `mil/config/workos.yaml`:
- `client_01KPY7CA07ZD1WG3DMQE1FZQE1`
- JWKS: `https://api.workos.com/sso/jwks/client_01KPY7CA07ZD1WG3DMQE1FZQE1`

When production values land in `workos.yaml`, add a
`[env.production]` block to `wrangler.toml` and deploy with
`wrangler deploy --env production`.

## Interaction with the MIL-59 `login-cjipro` Worker

The Edge Bouncer redirects **to** `login.cjipro.com`. The
`login-cjipro` Worker serves that domain. MIL-63 will rewrite
`login-cjipro` to handle the magic-link callback — at that point
the two Workers form a pair:

- `edge-bouncer` → runs on cjipro.com/briefing* + sonar.cjipro.com/*
  → redirects to login on miss
- `login-cjipro` → runs on login.cjipro.com/* → handles magic-link
  request + callback, sets `__Secure-cjipro-session` cookie on the
  `.cjipro.com` apex domain, 302s back to `return_to`

## Testing the Worker against a real JWT

When you want to smoke-test against a real WorkOS-issued session
JWT (e.g. during MIL-63 development), set the cookie manually in
browser devtools:

```
__Secure-cjipro-session=<paste JWT>; path=/; domain=.cjipro.com; secure
```

The Worker will then verify against the live JWKS.

## Monitoring

Every decision logs a single-line JSON object to Cloudflare logs.
Pull via `wrangler tail`, Logpush, or the dashboard. Schema:

```
{
  "ts": "2026-04-24T12:34:56Z",
  "enforce": true,
  "method": "GET",
  "host": "cjipro.com",
  "path": "/briefing-v4/",
  "action": "pass" | "redirect",
  "reason": "public" | "valid-session" | "missing" | "invalid",
  "detail": "<error message on invalid>"
}
```

MIL-65 (immutable audit log) will pipe these to R2 or Axiom.
