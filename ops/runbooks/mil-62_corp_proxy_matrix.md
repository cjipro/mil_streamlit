# MIL-62 — Corp-proxy test matrix

**Panel-designated HARD gate to alpha invites.** No partner receives
an invite until every bank in the matrix below passes every
scenario below. A single failing row blocks the whole cohort — we
fix the underlying issue (or scope the partner out of that bank)
before invites go.

## Why this exists

The Apr 23 Barclays block (Cloudflare Access redirect tripping the
phishing-pattern filter at Barclays corp proxies) is the
load-bearing incident. `cjipro.com/briefing*` was reachable on
corp network only after Cloudflare Access was stripped. If a
different auth step re-introduces a proxy-hostile pattern, we
repeat that incident in a much worse form — during partner
onboarding.

The risks to check for:
- **Redirect-chain filters.** Bank proxies flag anything matching
  `*.cloudflareaccess.com` / `*.workos.com` / `*.authkit.app`. If
  the login flow routes through any of those hostnames, proxies
  may 403.
- **Email content filters.** Magic-link emails from WorkOS may be
  quarantined by corp Mimecast / Proofpoint / Microsoft Defender.
- **Cookie policy.** Some corp browsers strip `SameSite=Lax`
  cookies or block third-party cookies by default. Our
  `__Secure-cjipro-session` is first-party to `.cjipro.com` so
  this should be fine, but verify.
- **TLS interception.** Corp proxies often re-sign HTTPS with an
  internal CA. `__Secure-` cookies require a browser-trusted
  certificate chain; a re-signed chain breaks silently.

## Prerequisites

Before running this matrix, confirm:

- [x] MIL-63 magic-link Worker deployed + reachable at
      `https://login.cjipro.com/` (commits `e45b06b` + `88d2c46` +
      `7dcebbe` on 2026-04-24; chunk 3 cutover complete; browser-
      tested end-to-end against AuthKit staging)
- [ ] WorkOS AuthKit staging env has `hussain.x.ahmed@barclays.com`
      (or equivalent bank-network test email) provisioned as a user
- [ ] MIL-61 edge-bouncer deployed, **ENFORCE=true** (not shadow), at
      least one briefing route bound (`cjipro.com/briefing-v4*`)
      → **PARTIAL as of 2026-04-24**: routes bound on all four
      briefing paths, JWKS/issuer corrected from authoritative
      OpenID config, shadow-mode logs confirmed clean on synthetic
      traffic, but `ENFORCE=false` still. Flip gated on 24–72h of
      real `pass/valid-session` log entries on authenticated
      briefing loads. Scenarios S3, S6, S7 cannot fully execute
      until this flips (briefings currently pass through).
- [ ] Test account credentials available for each bank's corp
      browser session

### Pre-flight smoke (runs off corp network, takes 60s)

Before enlisting a bank-corp tester, sanity-check the plumbing from
any machine with public internet access:

```
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://cjipro.com/
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://cjipro.com/briefing-v4/
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://login.cjipro.com/healthz
curl -s -o /dev/null -D - https://login.cjipro.com/ 2>&1 | grep -i '^location:'
```

Expected:
- Landing + briefing: 200 (until ENFORCE flips)
- `login.cjipro.com/healthz`: 200 `ok`
- `login.cjipro.com/` Location header: `https://api.workos.com/user_management/authorize?...` (NOT `authkit.app` directly — that endpoint returns `application_not_found` for User Management clients, see commit `e45b06b` postmortem)

If pre-flight fails, fix before involving a corp tester — no point
burning partner time on a broken test rig.

## Test scenarios (per bank)

### S1 — Landing page reachable

From the bank's corp laptop / browser / VPN:

```
GET https://cjipro.com/
```

Expected: HTTP 200, HTML renders, no redirect, no Cloudflare
challenge page.

Fail modes:
- HTTP 403 / proxy block page → corp proxy categorising cjipro.com.
  Remediation: submit to that bank's URL-classification vendor
  (Cisco Talos / Zscaler / Palo Alto / Forcepoint / Symantec — see
  MIL-51 status).

### S2 — Privacy + security.txt reachable (trust signals)

```
GET https://cjipro.com/privacy/
GET https://cjipro.com/.well-known/security.txt
```

Expected: both 200. Same fail mode as S1.

### S3 — Gated briefing triggers login redirect (no loops)

```
GET https://cjipro.com/briefing-v4/
```

Expected (once `ENFORCE=true`): HTTP 302 to
`https://login.cjipro.com/?return_to=/briefing-v4/`. Browser
follows the redirect and lands on the AuthKit login form
(background #FAFAF7, accent #003A5C, "Sign in to CJI Pro" heading).

**While `ENFORCE=false`** (current state): briefing loads directly
with HTTP 200. That's still a useful test — it confirms edge-bouncer
is in the request path without denying traffic. To verify, run
`cd mil/auth/edge_bouncer && npx wrangler tail` concurrently and
watch for a `{"action": "redirect", "reason": "missing", "enforce": false}`
log entry. If the decision log fires, S3 is effectively pre-flighted
even though the visible behaviour is "briefing loads". Re-run S3
for real after the flip.

Fail modes:
- In ENFORCE mode, no redirect → check route bindings in
  `mil/auth/edge_bouncer/wrangler.toml` + `wrangler deployments list`.
- Redirect to `*.workos.com` or `*.authkit.app` visible in URL bar
  → custom-domain cutover incomplete. Block invites.
- Redirect loop back to `login.cjipro.com` → `DEFAULT_RETURN_TO`
  misconfigured (see commit `e45b06b`). Confirm wrangler.toml has
  `DEFAULT_RETURN_TO = "https://cjipro.com/briefing-v4/"`, not `/`.
- Proxy blocks login.cjipro.com even though cjipro.com loaded →
  different categorisation between subdomain and apex. Submit
  login.cjipro.com separately.

### S4 — Magic-link email delivery

Enter the bank-network test email into the AuthKit form. Expected:
"check your inbox" state on the login page, within 60s a magic-
link email arrives from WorkOS in the corp inbox.

Fail modes:
- Email never arrives → corp email filter quarantined it. Check
  junk / quarantine. Remediation: whitelist `@workos.com` sender
  or (preferred) send from a `@cjipro.com` sender via WorkOS
  custom SMTP config.
- Email arrives in junk → tolerable for alpha, flag for beta.

### S5 — Magic-link click reaches callback

Click the link in the email from the corp browser.

Expected: browser follows WorkOS → `https://login.cjipro.com/callback?code=…`
→ 302 back to `/briefing-v4/` on `cjipro.com`.

Fail modes:
- Link rewritten by corp email security (e.g. Mimecast click-
  tracker domain in URL bar). Verify the final destination still
  reaches `login.cjipro.com/callback` — corp click-trackers
  usually forward after a safety check, that's OK. Record the
  tracker domain for reference.
- Link blocked at click time (proxy blocks destination). Same
  remediation as S3.
- Callback returns "Sign-in error" → check the error code:
  - `expired` → state TTL too short. Unlikely unless >10 min
    elapsed.
  - `bad-signature` → STATE_SIGNING_KEY mismatch. Serious — stop.
  - `workos-error` → user cancelled or WorkOS rejected. Retry.

### S6 — Session cookie is set + ridden back to briefing

After the callback 302, the browser requests `cjipro.com/briefing-v4/`
with the `__Secure-cjipro-session` cookie attached. Edge Bouncer
accepts it, passes through to origin.

Expected: briefing renders. DevTools Application tab shows the
`__Secure-cjipro-session` cookie with `Domain=.cjipro.com`,
`HttpOnly`, `Secure`, `SameSite=Lax`.

Fail modes:
- Cookie not set → TLS interception may have broken the
  `__Secure-` prefix requirement. Check the browser's certificate
  panel — if the cert chain leads to an internal corp CA, that's
  the cause. Remediation is hard (need corp IT to whitelist).
- Cookie set but briefing returns another 302 to login →
  Edge Bouncer rejected the JWT. Check edge-bouncer logs for
  `reason: invalid` and detail. Likely `EXPECTED_ISS` mismatch;
  update and redeploy.

### S7 — Subsequent briefing navigations use the cookie

Navigate to `cjipro.com/briefing-v3/` in the same session.
Expected: 200, no redirect, cookie rides along (SameSite=Lax
allows top-level navigation).

Fail modes:
- Redirect to login → cookie stripped between requests. Verify
  SameSite policy in corp browser settings.

### S8 — JWT payload inspection (diagnostic only)

Run this if S6 or S7 fails in a confusing way — it isolates "did
WorkOS issue a valid token" from "did edge-bouncer accept it".

From DevTools → Application → Cookies → `.cjipro.com` → copy the
`__Secure-cjipro-session` value. On any machine (off corp network
is fine — the JWT is self-contained), decode the payload:

```bash
COOKIE='<paste here>'
echo "$COOKIE" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | python -m json.tool
```

Or paste into https://jwt.io (decode only, don't check "secret" —
the public key lookup happens server-side via JWKS).

Expected payload fields (must match edge-bouncer's env vars):
- `iss` = `https://ideal-log-65-staging.authkit.app`
  (matches `EXPECTED_ISS` in `mil/auth/edge_bouncer/wrangler.toml`)
- `aud` = `client_01KPY7CA07ZD1WG3DMQE1FZQE1`
  (matches `EXPECTED_AUD`)
- `exp` > current Unix time
- `sub` = opaque user ID (`user_01...`)
- `sid` = opaque session ID (`session_01...`)

Fail modes:
- `iss` doesn't match → AuthKit tenant mismatch. Either
  `EXPECTED_ISS` is wrong (update wrangler.toml, redeploy) or the
  magic-link Worker was pointed at a different tenant.
- `aud` doesn't match → AuthKit client binding drift. Check
  `mil/config/workos.yaml` against the WorkOS dashboard.
- `exp` already past → cookie served stale; session expired. Log
  in again. Expected with 60-min `COOKIE_MAX_AGE_SECONDS`.
- Payload doesn't decode at all → cookie got truncated en route.
  Suspect corp email security rewriting the magic-link URL in a
  way that corrupted state. Capture full request/response headers
  for debugging.

Record the decoded `iss` + `aud` in the results cell for the
bank — useful if we later need to reconstruct what a corp browser
actually saw.

## Results matrix

Fill this in per bank. Date + tester initials in each cell; ✅ /
❌ / ⚠ (partial) in the status column. S8 is diagnostic-only,
run it only when another scenario fails opaquely.

| Bank    | Tester | Date | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | Overall |
|---------|--------|------|----|----|----|----|----|----|----|----|---------|
| Barclays |  |  |  |  |  |  |  |  |  |  |  |
| HSBC     |  |  |  |  |  |  |  |  |  |  |  |
| Lloyds   |  |  |  |  |  |  |  |  |  |  |  |
| NatWest  |  |  |  |  |  |  |  |  |  |  |  |

## Gate decision

Alpha invites proceed only when:
- [ ] At least 3 of 4 banks pass ALL scenarios end-to-end
- [ ] For the failing bank (if any), partner is explicitly scoped
      OUT of that bank's cohort — they'll join after remediation

Partial passes (S1–S3 pass, S4–S5 fail because of email filters):
- [ ] Document as a known limitation; alpha invitees on that bank
      may need to use a personal email for magic-link
- [ ] Open a MIL-52-style ticket to ship `@cjipro.com`-sender
      WorkOS custom SMTP so magic-links come from our domain

## Failure remediation playbook

| Failure | First fix |
|---|---|
| `cjipro.com` blocked at proxy | URL-filter vendor submission (MIL-51 status — check which vendor). Usually 24–72h to re-categorise. |
| `login.cjipro.com` blocked separately | Submit the subdomain to the same vendor. Same SLA. |
| WorkOS email filtered | (a) Manual sender allowlist via corp IT, (b) ship `@cjipro.com`-sender SMTP (requires SPF update — MIL-52). |
| `__Secure-` cookie refused | Corp TLS interception. Remediate via corp IT whitelist; otherwise that bank is alpha-blocked. |
| `EXPECTED_ISS` mismatch | Update `mil/auth/edge_bouncer/wrangler.toml`, redeploy, continue. |

## Who runs this

Hussain coordinates with an alpha partner on each bank. Tester
runs from their own corp laptop — Claude cannot replicate a corp-
network environment. Results come back here.

## Status log

- 2026-04-24 (morning) — Runbook drafted. Matrix blank.
  Prerequisites not yet satisfied (MIL-63 chunk 3 cutover pending;
  ENFORCE still false on edge-bouncer).
- 2026-04-24 (afternoon) — MIL-63 chunk 3 cutover DONE. login.cjipro.com
  now served by magic-link Worker (commit `e45b06b`); browser-tested
  end-to-end with AuthKit staging. Edge-bouncer JWKS/issuer corrected
  from `.well-known/openid-configuration` (no longer PROVISIONAL).
  Four briefing routes bound with ENFORCE=false (commit `88d2c46`).
  S3/S6/S7 still blocked on ENFORCE=true flip, scheduled for
  2026-04-26 check-in after 48h shadow-mode observation. Pre-flight
  smoke section added. S8 JWT-inspection scenario added for
  diagnostic use. Matrix still blank — banks still need corp-network
  testers.
