# MIL-69 — Login + Webhook Rate Limiting (Cloudflare WAF)

Cloudflare's edge protects the auth surface BEFORE any Worker code
runs. Five rules cover everything we expose; each is a one-time
dashboard action.

There's already a per-IP rate limit on `POST /request-access` inside
the magic-link Worker (5 / hour / IP, see `mil/auth/approvals/src/
rate_limit.ts`). The WAF rules below are a second layer that:
- Catches abuse cheaper (no Worker invocation = no billable request)
- Covers paths the in-Worker limiter doesn't (admin API, authorize)
- Provides a global-volume guardrail in case a single IP rotates

## Where to click

Cloudflare dashboard → cjipro.com → **Security** → **WAF** →
**Rate limiting rules** → **Create rule**.

Repeat for each rule below. After creating each rule, save → enable.

## The five rules

### Rule 1 — Signup form (in-Worker limit + WAF backstop)

| Field | Value |
|---|---|
| Name | `MIL-69 signup form` |
| Expression | `(http.host eq "login.cjipro.com" and http.request.uri.path eq "/request-access" and http.request.method eq "POST")` |
| Counting characteristic | IP |
| Period | 1 hour |
| Requests | 10 |
| Action | Block, retry-after = 3600 |
| Mitigation timeout | Same as period |

Justification: in-Worker says 5/h, WAF says 10/h — anything that gets
past WAF gets the friendlier in-Worker error page; sustained abuse
gets the WAF block.

### Rule 2 — Admin API

| Field | Value |
|---|---|
| Name | `MIL-69 admin api` |
| Expression | `(http.host eq "login.cjipro.com" and starts_with(http.request.uri.path, "/admin/api/") and http.request.method eq "POST")` |
| Counting characteristic | IP |
| Period | 1 minute |
| Requests | 60 |
| Action | Managed Challenge |
| Mitigation timeout | 10 minutes |

Justification: admin API is gated by JWT verify + admin_users; rate
limit is anti-DoS, not anti-auth-brute-force. Challenge over Block so
a real admin who fat-fingers won't get hard-locked.

### Rule 3 — AuthKit redirect entry

| Field | Value |
|---|---|
| Name | `MIL-69 authorize entry` |
| Expression | `(http.host eq "login.cjipro.com" and http.request.uri.path eq "/" and http.request.method eq "GET")` |
| Counting characteristic | IP |
| Period | 1 minute |
| Requests | 30 |
| Action | Managed Challenge |
| Mitigation timeout | 5 minutes |

Justification: `/` does the WorkOS authorize redirect. Spamming this
costs nothing on its own but warms our state-signing path; 30/min/IP
is generous for a real human, way too slow for an enumeration
attempt.

### Rule 4 — WorkOS webhook (allowlist source IPs)

WorkOS publishes their webhook source IPs at
https://workos.com/docs/events/webhooks#source-ip-addresses (last
checked: confirm against current docs before deploying — they may
rotate).

| Field | Value |
|---|---|
| Name | `MIL-69 webhook IP allowlist` |
| Expression | `(http.host eq "login.cjipro.com" and http.request.uri.path eq "/webhooks/workos" and not ip.src in {<workos_ip_1> <workos_ip_2> ...})` |
| Action | Block |
| (No rate-limit window — this is a fixed allowlist, not a counting rule.) |

Use Cloudflare → **Security** → **WAF** → **Custom rules** for an
IP-allowlist (Custom rules, not Rate limiting rules).

Justification: signature verification already rejects unauth events;
this drops them at the edge so we don't spend Worker time on them
and the audit log stays clean.

### Rule 5 — Catch-all volume cap

| Field | Value |
|---|---|
| Name | `MIL-69 global volume cap` |
| Expression | `(http.host eq "login.cjipro.com")` |
| Counting characteristic | IP |
| Period | 1 minute |
| Requests | 200 |
| Action | Managed Challenge |
| Mitigation timeout | 10 minutes |

Justification: catches whatever the four targeted rules missed.
200/min/IP is generous; real users will never approach.

## Verification

After enabling rules, hit the rate limits manually to confirm:

```bash
# Should get 10 successes then a 403/429 page
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    https://login.cjipro.com/request-access \
    -H "content-type: application/x-www-form-urlencoded" \
    -d "email=test+$i@example.com"
done
```

Look in Cloudflare dashboard → Security → Events to see the matched
rule + decision per request.

## Audit-log correlation

When WAF challenges/blocks fire BEFORE the Worker, they don't land
in our audit log — they're in Cloudflare's Security Events. If WAF
serves a challenge page and the user solves it, the request reaches
the Worker normally and the audit log captures it as if it were any
other request.

`bouncer.rate_limited` event type exists for the case where the
Worker itself observes Cloudflare's CF-Challenge headers (added in
companion commit). Query:

```bash
cd mil/auth/edge_bouncer
npx wrangler d1 execute mil-auth-audit --remote --json --command \
  "SELECT id, ts, path, reason FROM auth_events
   WHERE event_type = 'bouncer.rate_limited'
   ORDER BY id DESC LIMIT 20"
```

For a true unified view across edge + Worker, configure Cloudflare
Logpush to push WAF events into a separate sink (R2, BigQuery,
Datadog) and join on `cf-ray` header. Out of scope for MIL-69.

## What NOT to rate-limit

- `cjipro.com/briefing*` — handled by the bouncer's session check
  (no auth attempt without a valid JWT). Rate-limiting GETs of HTML
  punishes refreshes by real users.
- `cjipro.com/` and `/privacy` — public landing pages. Leave open.
- The WorkOS authorize round-trip (redirect from `login.cjipro.com/`
  to `api.workos.com/...` and back). Rule 3 covers our entry side;
  WorkOS handles their own brute-force protection on the AuthKit page.

## Maintenance

- Recheck WorkOS webhook source IPs (Rule 4) every quarter — they
  can change without notice.
- If you see legitimate users tripping the limits, raise the
  threshold in the dashboard rather than disabling the rule.
- Cloudflare Free tier includes basic rate limiting; if you hit the
  rule-count cap, upgrade or consolidate rules.
