# mil/auth/app_cjipro — app.cjipro.com Worker (MIL-84)

Authenticated product surface for the four CJI products. Hosts Reckoner default surface today (MIL-92); future routes for Sonar (`/sonar/{client_slug}/{date}/`, MIL-86), Pulse workspace, and Lever workspace land on this same Worker as new TypeScript modules under `src/`.

## What it does

Same JWT + approval gate as `mil/auth/edge_bouncer/`, but instead of `fetch(request)` to a GitHub Pages origin, this Worker renders the product surfaces itself. Shared session/whitelist logic is imported directly from `../edge_bouncer/src/` to keep one source of truth for JWT validation. Audit + approval D1 work uses the same `mil-auth-audit` database as the other two Workers.

Decision flow per request:

1. **Public allowlist.** `/healthz`, `/favicon.ico`, `/.nojekyll`, `/robots.txt`. Bypasses auth.
2. **Cookie + JWT.** Read `__Secure-cjipro-session`, verify against the WorkOS JWKS (issuer + signature only — User Management access tokens do not carry `aud`).
3. **Sub → email → approved.** Look up the JWT's `sub` in the `sessions` table, check the resulting email against `approved_users`. Both fail closed (403 access-pending page).
4. **Render or redirect.** Approved → `dispatch(request)` in `router.ts`. Missing/invalid → 302 to `login.cjipro.com` with `return_to`.

## Deploy

Pre-reqs Hussain has to do once before first deploy:

1. **MIL-82 DNS** is already done (CNAME → login.cjipro.com via Cloudflare Mode B). Verify with `curl -sI https://app.cjipro.com/` — should return Cloudflare TLS even before this Worker ships.
2. **No new D1 database.** This Worker uses the existing `mil-auth-audit` (id `84acbc8b-6169-4668-ae0e-15ccfbfdf1ca`) — same one the bouncer + magic-link write to. No `wrangler d1 create` step needed.
3. **No new secrets.** All auth values are non-secret (JWKS_URL, EXPECTED_ISS, EXPECTED_AUD) and live in `wrangler.toml`. Worker has no signing key of its own.

Then, from `mil/auth/app_cjipro/`:

```bash
npm install
npm run typecheck   # tsc --noEmit
npm test            # vitest run
npx wrangler deploy
```

The deploy is what creates `app.cjipro.com` as a Cloudflare Worker custom domain — Cloudflare auto-replaces the MIL-82 placeholder CNAME with a Worker-bound DNS record. ENFORCE stays `false` for at least 24 hours of shadow-mode traffic before flipping. Same playbook as the edge-bouncer rollout.

## ENFORCE rollout

`ENFORCE=false` is the safe default. In that mode every gate decision is logged via `logAuthEvent` but the Worker always renders. We watch `wrangler tail app-cjipro` for at least 24h on real alpha-cohort traffic, look for `pass.session` rows from approved users + `redirect.missing` from cold visitors, and only then flip `ENFORCE=true` via `wrangler deploy --var ENFORCE:true` (or by editing `wrangler.toml` and redeploying). The toggle is per-deploy.

When enforce is on:
- Missing/invalid JWT → 302 to login.cjipro.com (full-page redirect, never modal).
- Valid JWT but not approved → 403 access-pending page (no loop back to login).
- Approved → renders the surface.

## Reckoner content (MIL-92)

`src/reckoner.ts` exports `renderReckonerHtml(snapshot: ReckonerSnapshot)` and an `mvpSnapshot()` helper that returns illustrative-but-realistic content tagged with an alpha-preview banner. The real-data follow-up replaces `mvpSnapshot()` with a snapshot read from the daily build (`mil/outputs/mil_findings.json` + `mil_analytics.db`) — typed contract stays the same.

Three sections, three Clark tiers, the four-stage chain language baked in:
- **Section 01 · Aggregate** — Industry Pulse: severity-weighted top patterns + KPI strip.
- **Section 02 · Awareness** — Anomalies: baseline-deltas with CHR anchors + confidence flags.
- **Section 03 · Action** — Decisions Surfaced: patterns at CLARK-2/3 ready for an audience.

Two interface modes are intentionally disabled in MVP per the brand-spine lock: Conversational drill-in (MIL-93) and Drag-drop canvas. The tabs render but click-disabled with a "Coming" pill.

## Testing

Three suites:

| Suite                       | What it covers                                                  |
|-----------------------------|-----------------------------------------------------------------|
| `test/router.test.ts`       | Pathname dispatch, content presence, no-XSS escaping, 404 page  |
| `test/reckoner.test.ts`     | Reckoner template rendering, severity/Clark badges, empty cases |
| `test/auth_gate.test.ts`    | enforce=true/false matrix, public-path bypass, fail-closed AUDIT |

`npm test` runs all three. ~25–30 tests total, no network, no D1 writes (fake D1 stub matches the edge-bouncer test pattern).

## Why this Worker exists separately from edge-bouncer

Two separate Worker scripts isolate failure domains. A bug in one Worker can't take the other surface down. `cjipro.com/briefing*` (edge-bouncer) and `app.cjipro.com/*` (this Worker) enforce JWT independently using the same JWKS. This is intentional, not a tech-debt accident.
