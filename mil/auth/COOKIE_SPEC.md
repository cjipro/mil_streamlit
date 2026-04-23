# MIL-64 — `__Secure-cjipro-session` cookie specification

**Load-bearing contract between the magic-link Worker (issuer) and
the Edge Bouncer (validator).** Changing any of the invariants
below requires coordinated deploys to both Workers; silent drift
will break auth.

This spec is machine-enforced by
`mil/auth/magic_link/src/cookie_spec.ts` + its test file.

## Cookie identity

| Field | Value | Why |
|---|---|---|
| **Name** | `__Secure-cjipro-session` | `__Secure-` prefix forces the browser to reject any `Set-Cookie` attempted over HTTP, and to refuse `Secure` being dropped. Name is consumed by Edge Bouncer's `SESSION_COOKIE_NAME` env var — lock-step. |
| **Value** | WorkOS-issued access-token JWT (RS256, WorkOS JWKS) | Validated by Edge Bouncer via `jose` against the remote JWKS. Short-lived (≤1h typical). When expired, Edge Bouncer sees an invalid signature and redirects to login → seamless refresh for the user. |

## Attribute requirements (MUST, every `Set-Cookie` call)

| Attribute | Value | Rationale |
|---|---|---|
| `Domain` | `.cjipro.com` | One cookie covers cjipro.com, sonar.cjipro.com, login.cjipro.com, and any future subdomain. Without this, users would have to log in separately per subdomain. |
| `Path` | `/` | Cookie visible to every path. Scoping to subpaths would break the briefing flow. |
| `HttpOnly` | present | No JavaScript access — mitigates session exfil via XSS. Edge Bouncer reads via `Cookie` request header, no JS read needed. |
| `Secure` | present | Only sent over HTTPS. Redundant with `__Secure-` prefix but belt+braces. |
| `SameSite` | `Lax` | **Deliberate — NOT `Strict`.** `Strict` would block the cookie on the top-level GET redirect from `login.cjipro.com/callback` → `cjipro.com/briefing-v4/`, breaking the login return flow. `Lax` permits top-level cross-site navigations but blocks iframe + cross-site POST, which is the correct tradeoff. |
| `Max-Age` | From env `COOKIE_MAX_AGE_SECONDS`; default `3600` | Expires the cookie client-side without relying on server bookkeeping. Matches WorkOS access-token lifetime. |

## Attribute prohibitions (MUST NOT, ever)

- **No `Expires` datetime** — use `Max-Age` only. Clocks drift; `Max-Age` is relative and robust.
- **No `Domain=cjipro.com`** (without leading dot) — some old browsers treat these differently, and we want explicit cross-subdomain behaviour.
- **No `SameSite=None`** — opens CSRF surface. `Lax` is correct.
- **No `SameSite` absence** — modern Chrome treats missing SameSite as `Lax` already, but we set it explicitly so downstream middleboxes don't default differently.
- **No `Partitioned`** — MIL-64 scope is first-party session, not third-party. If we ever embed cross-site, revisit.

## Issuance flow (magic-link Worker)

The cookie is issued in exactly ONE place: `GET /callback` in
`mil/auth/magic_link/src/index.ts`, after successful code exchange
with WorkOS. The Set-Cookie value is produced by
`buildSessionCookie(accessToken, cookieConfig)` in `cookie.ts`.

No other path issues the cookie. In particular: no login form set,
no refresh endpoint, no "remember me" flag. Those are future work.

## Revocation flow (magic-link Worker)

The cookie is revoked by `GET /logout` via
`buildClearCookie(cookieConfig)` which sets `Max-Age=0` with
matching Domain + Path. Clearing a cookie requires the SAME
Domain + Path as the original set, or the browser ignores it.

## Validation flow (Edge Bouncer)

Edge Bouncer reads the cookie header, extracts the named cookie
via `extractCookie()` (`session.ts`), and verifies the JWT
signature against WorkOS JWKS. It does NOT trust the cookie on
its name alone — every request re-verifies the signature.

JWKS is cached in module scope for `JWKS_CACHE_TTL_SECONDS` (default
3600s). WorkOS rotates keys automatically; `jose` handles rotation
via kid-based lookup.

## Rotation / re-issuance

v1 does not implement server-side session rotation. When the
WorkOS access-token expires (≤1h), Edge Bouncer sees `invalid`
and 302s back to login. User re-authenticates; magic-link Worker
issues a fresh cookie.

Future tickets:
- **MIL-68** adds sliding-window session policy (4h inactivity /
  24h absolute) via refresh tokens — requires server-side session
  state, likely a new Durable Object or D1 table.
- **MIL-65** adds an audit event on every issue + revoke; the
  cookie carries no audit identity beyond the JWT `sub` claim.

## Testing the spec

```bash
cd mil/auth/magic_link
npm test -- cookie        # isolates cookie-related tests
```

The machine-readable form of this spec is
`mil/auth/magic_link/src/cookie_spec.ts` and its accompanying
`test/cookie_spec.test.ts`. Any drift between this document and
those files is a bug — fix both.

## Change procedure

Any modification to any row in "Attribute requirements" above
requires:

1. Update this file with the new value + rationale.
2. Update `cookie_spec.ts` to reflect the new invariant.
3. Update `cookie.ts` if the cookie construction changes.
4. Run full magic_link test suite.
5. Update Edge Bouncer if the change affects validation (name
   change → update `SESSION_COOKIE_NAME` env var in lockstep).
6. Coordinate the deploy: magic-link first (start issuing new
   cookies), Edge Bouncer second (start accepting new cookies).
   Reverse order would reject live sessions.
7. Flag the change in CHANGELOG section below.

## Changelog

| Date | Change | Author |
|---|---|---|
| 2026-04-24 | Initial spec captured from chunks 1-2 of MIL-63 implementation | Claude |
