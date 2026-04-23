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

- [ ] MIL-63 magic-link Worker deployed + reachable at
      `https://login.cjipro.com/` (chunk 3 cutover complete)
- [ ] WorkOS AuthKit staging env has `hussain.x.ahmed@barclays.com`
      (or equivalent bank-network test email) provisioned as a user
- [ ] MIL-61 edge-bouncer deployed, ENFORCE=true (not shadow), at
      least one briefing route bound (`cjipro.com/briefing-v4*`)
- [ ] Test account credentials available for each bank's corp
      browser session

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

Expected: HTTP 302 to
`https://login.cjipro.com/?return_to=/briefing-v4/`. Browser
follows the redirect and lands on the AuthKit login form
(background #FAFAF7, accent #003A5C, "Sign in to CJI Pro" heading).

Fail modes:
- No redirect (ENFORCE probably still false)
- Redirect to `*.workos.com` or `*.authkit.app` visible in URL bar
  → custom-domain cutover incomplete. Block invites.
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

## Results matrix

Fill this in per bank. Date + tester initials in each cell; ✅ /
❌ / ⚠ (partial) in the status column.

| Bank    | Tester | Date | S1 | S2 | S3 | S4 | S5 | S6 | S7 | Overall |
|---------|--------|------|----|----|----|----|----|----|----|----|
| Barclays |  |  |  |  |  |  |  |  |  |  |
| HSBC     |  |  |  |  |  |  |  |  |  |  |
| Lloyds   |  |  |  |  |  |  |  |  |  |  |
| NatWest  |  |  |  |  |  |  |  |  |  |  |

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

- 2026-04-24 — Runbook drafted. Matrix blank. Prerequisites not
  yet satisfied (MIL-63 chunk 3 cutover pending; ENFORCE still
  false on edge-bouncer).
