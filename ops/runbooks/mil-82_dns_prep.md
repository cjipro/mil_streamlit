# MIL-82 — Cloudflare DNS prep for app.cjipro.com + admin.cjipro.com

The brand-architecture lock (2026-04-25) split cjipro.com into a
public marketing surface (cjipro.com — already live) and an
authenticated product surface (`app.cjipro.com` — MIL-84) plus an
admin surface (`admin.cjipro.com` — MIL-83). This ticket lays down
the DNS records so the Workers can claim the subdomains the moment
they're deployed, and so URL-filter vendors that have already
classified `cjipro.com` extend that classification cleanly.

## Status snapshot

| Subdomain                | Worker (target)         | Status today                      |
|--------------------------|-------------------------|-----------------------------------|
| `cjipro.com`             | (GitHub Pages)          | LIVE — public marketing site       |
| `login.cjipro.com`       | `magic-link`            | LIVE — magic-link auth             |
| `sonar.cjipro.com`       | (cloudflared tunnel)    | LIVE — Ask CJI Pro chat (alpha)    |
| **`app.cjipro.com`**     | `app-cjipro` (MIL-84)   | **TODO** — needs DNS              |
| **`admin.cjipro.com`**   | `magic-link` /admin     | **TODO** — needs DNS              |

## What "prep" means

Two operating modes for this ticket. Pick one based on whether the
Workers are deployed yet at execution time.

- **Mode A — Workers deployed first** (preferred when MIL-83 + MIL-84
  ship together): bind each subdomain as a Worker custom domain via
  the wrangler.toml `[[routes]]` block. Cloudflare auto-creates the
  DNS records when the binding lands. **No DNS edits needed in this
  mode** — the Worker deploy creates them.

- **Mode B — DNS first, Workers later** (only if you want to reserve
  the subdomain claim before the Worker is ready, e.g. for URL-filter
  vendor classification carry-over): create CNAME records pointing
  to `login.cjipro.com` (which already returns a valid TLS cert and
  a "coming soon" placeholder via the existing magic-link Worker).
  Replace with the real bindings in MIL-83/84.

Default to Mode A. Mode B is a tactical move if URL-filter
classification (MIL-51) needs a settled DNS picture before the
Workers ship.

## Mode A — Worker custom-domain binding (preferred)

When MIL-83 and MIL-84 are ready to deploy, edit each Worker's
`wrangler.toml` and add custom-domain routes.

### admin.cjipro.com (MIL-83)

The admin surface migrates from `login.cjipro.com/admin` to its own
subdomain. Two options:

**Option A1 — Reuse the magic-link Worker (cheapest, no new Worker):**
in `mil/auth/magic_link/wrangler.toml`, add a second `[[routes]]`
entry:
```toml
[[routes]]
pattern = "login.cjipro.com"
custom_domain = true

[[routes]]
pattern = "admin.cjipro.com"
custom_domain = true
```
Then in `src/index.ts` route by hostname: requests to
`admin.cjipro.com` get the existing /admin handler; requests to
`login.cjipro.com` keep working as today. The magic-link Worker
already has the auth + audit + approvals plumbing this needs.

**Option A2 — Separate `admin-cjipro` Worker:** copy the magic-link
Worker into `mil/auth/admin/`, strip the magic-link callback flow,
keep the admin handler. More files but cleaner separation.

A1 is the smaller change. Recommend A1 unless MIL-83 explicitly
calls for separation (it doesn't, last I checked).

### app.cjipro.com (MIL-84)

This subdomain hosts the authenticated product surface for all four
products (Reckoner, Sonar, Pulse workspace, Lever). It needs its
own Worker per the website rebuild plan: `app-cjipro` with edge-
bouncer JWT validation.

Wrangler scaffold (in `mil/auth/app_cjipro/wrangler.toml`, to be
created in MIL-84):
```toml
name = "app-cjipro"
main = "src/index.ts"
compatibility_date = "2026-04-25"

[[routes]]
pattern = "app.cjipro.com"
custom_domain = true

[vars]
ENFORCE = "false"   # shadow-mode first, same playbook as edge-bouncer
EXPECTED_ISS = "https://api.workos.com/user_management/<client_id>"
JWKS_URL = "<authkit-domain>/oauth2/jwks"
```

Deploying with `npx wrangler deploy` from `mil/auth/app_cjipro/`
auto-creates the DNS for `app.cjipro.com`.

## Mode B — DNS-first reservation (only if needed)

If we need DNS records BEFORE the Workers ship (typically because
URL-filter vendors are mid-review and we want the subdomains
included in the classification carry-over from `cjipro.com`):

1. Cloudflare dashboard → `cjipro.com` zone → DNS → Records → **Add
   record**.
2. For `app`:
   - Type: `CNAME`
   - Name: `app`
   - Target: `login.cjipro.com`
   - Proxy status: **Proxied (orange cloud)** — required for TLS via
     Cloudflare's edge cert
   - TTL: Auto
3. For `admin`:
   - Type: `CNAME`
   - Name: `admin`
   - Target: `login.cjipro.com`
   - Proxy status: **Proxied**
   - TTL: Auto

Both will resolve to the magic-link Worker placeholder until MIL-83
and MIL-84 replace the bindings.

Curl alternative (for the `Email Routing - Edit` API scope is missing
and we have a non-Email-Routing API token instead):

```bash
ZONE_ID=0da15aa946c4c4e74584371147b934a1
TOKEN=<your-CF-API-token-with-DNS-Edit-on-cjipro.com>

curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"CNAME","name":"app","content":"login.cjipro.com","ttl":1,"proxied":true,"comment":"MIL-82 reservation; replaced by app-cjipro Worker custom domain in MIL-84"}'

curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"CNAME","name":"admin","content":"login.cjipro.com","ttl":1,"proxied":true,"comment":"MIL-82 reservation; replaced by admin route on magic-link Worker in MIL-83"}'
```

## Verification

Whichever mode shipped, verify both records resolve to a valid TLS
endpoint:

```powershell
Resolve-DnsName -Type A app.cjipro.com
Resolve-DnsName -Type A admin.cjipro.com
```

Both should return Cloudflare proxy IPs (likely `104.21.x.x` /
`172.67.x.x`). Then:

```bash
curl -sI https://app.cjipro.com/    | head -5
curl -sI https://admin.cjipro.com/  | head -5
```

Both should return `HTTP/2 200` (or 302 if the placeholder
redirects), with `cf-ray` and `server: cloudflare` headers. Any
`SSL_ERROR_NO_CYPHER_OVERLAP` or cert-name-mismatch means the
proxy bit is off — flip it to **Proxied** in the dashboard.

## Backout

Mode A — undeploy the Worker (or remove the `[[routes]]` entry and
re-deploy). Cloudflare deletes the auto-created DNS record.

Mode B — delete the two DNS records via the dashboard. Subdomain
returns to NXDOMAIN; nothing depends on it yet so this is safe.

## Coordination notes

- **Don't bind both Workers to the same hostname.** If MIL-83 lands
  Option A1 (magic-link handles admin.cjipro.com), do NOT also
  create a separate `admin-cjipro` Worker — the route binding is
  exclusive.
- **MIL-86 dependency.** When `/sonar/{client_slug}/{date}/` migrates
  to `app.cjipro.com/sonar/{client_slug}/{date}/`, the URL on the
  PDB email (MIL-49) needs to flip too. Track in MIL-87 (cutover
  ticket).
- **Cookie domain.** The session cookie issued by the magic-link
  Worker today is `Domain=.cjipro.com` (per MIL-64 spec). It will
  cover `app.cjipro.com` + `admin.cjipro.com` automatically once
  the bindings land — no cookie work needed.
- **Edge-bouncer scope.** When `app.cjipro.com` ships its own Worker
  (MIL-84), edge-bouncer's existing four-route binding on
  `cjipro.com/briefing*` doesn't move. The new Worker on
  `app.cjipro.com` enforces JWT independently using the same JWKS.
  This is intentional — two separate Worker scripts isolate failure
  domains.

## Done means

- `app.cjipro.com` resolves and returns 2xx/3xx with valid TLS.
- `admin.cjipro.com` resolves and returns 2xx/3xx with valid TLS.
- Either: a Worker is bound (Mode A), or a CNAME is reserving the
  name (Mode B).
- The status table at the top of this file reflects the actual
  state.
- CLAUDE.md MIL-82 row updated to BUILT with the mode used and the
  date.
