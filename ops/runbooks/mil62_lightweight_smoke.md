# MIL-62 Lightweight 1-partner smoke test

A 5-minute corp-proxy validation, replacing the originally-specced
4-bank x 7-scenario matrix. Run this once with each new alpha
partner during onboarding — don't run before sign-in attempt #1.

## Pre-flight (do this before the partner clicks anything)

1. **Confirm partner email is in approved_users:**
   ```bash
   bash ops/admin_users/list_users.sh   # or query D1 directly
   ```
   If absent, add via admin dashboard at `login.cjipro.com/admin`
   or via D1 INSERT. Without this, partner authenticates fine but
   hits "Access pending" page — fine for proving the redirect chain
   works, but no actual product access.

2. **Open audit log tail:**
   ```bash
   cd /c/Users/hussa/while-sleeping/mil/auth/edge_bouncer
   npx wrangler d1 execute mil-auth-audit --remote --json --command \
     "SELECT id, ts, event_type, reason FROM auth_events ORDER BY id DESC LIMIT 20"
   ```
   Re-run this after the test. You're watching for:
   - `magic_link.authorize` (sign-in initiated)
   - `magic_link.callback.success` (sign-in completed)
   - `bouncer.pass.session` (auth recognised, page loaded)

3. **Be reachable on phone/Slack** for the partner during the test.
   Most failures are obvious within 30s. If they freeze or get an
   unfamiliar error page, ask for a screenshot.

## The test (partner does these steps, you watch logs)

| Step | Partner does | What to verify in logs |
|---|---|---|
| 1 | Visit `https://app.cjipro.com/sonar/{their_slug}/` | Edge serves 302 to `login.cjipro.com/?return_to=...` |
| 2 | Enters email at login form | `magic_link.authorize` row appears |
| 3 | Receives email, clicks magic link | `magic_link.callback.success` row appears |
| 4 | Lands back on briefing | `bouncer.pass.session` row appears, briefing renders |

**PASS criteria:** all 4 steps complete within 2 minutes of starting.

**FAIL modes — call the partner before troubleshooting:**

- **Sign-in form never loads** (step 1 → blank/error page on corp network)
  → Corp proxy blocked the redirect to `login.cjipro.com`. Same
  phishing-pattern signature concern that forced Apr 23 unblock.
  Roll back: `ENFORCE=false` on edge-bouncer + app-cjipro until
  fixed.

- **Email never arrives** (step 3 → no email in inbox after 2 min)
  → Corp mail server quarantined or rejected the magic-link email.
  Check sender domain reputation, SPF/DKIM alignment for
  `noreply@workosmail.com` (WorkOS sender). Workaround: use admin
  dashboard "Send sign-in link" feature for the partner.

- **Magic link click 404s or errors** (step 3 → click → broken page)
  → AuthKit callback URL mismatch. Check WorkOS dashboard
  Authentication > Redirect URIs includes `https://login.cjipro.com/callback`.

- **Lands on "Access pending"** (step 4 → blocked at allowlist gate)
  → Pre-flight item 1 was missed. Add user to approved_users.
  This is NOT a corp-proxy failure — sign-in succeeded.

## Disposition

- **All 4 steps pass:** corp network is fine. Repeat for next partner
  on a different network.
- **Any FAIL:** open ticket referencing the specific failure mode
  above. Roll back ENFORCE flags if the partner is blocked from
  doing real work.

## Why we skipped the full MIL-62 matrix

Originally specced as 4-bank × 7-scenario × hardcoded gate before
ENFORCE flip. After Apr 26 (MIL-87 redirected briefing-v4 to public
sample, alpha auth path moved to app.cjipro.com), the load-bearing
concern shifted from "alpha can't reach briefing" to "alpha can't
authenticate." The lightweight version above tests exactly that.
Full matrix remains the gold standard if scaling beyond ~10 partners
or onboarding from networks with known proxy aggression.
