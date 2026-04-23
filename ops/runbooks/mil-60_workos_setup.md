# MIL-60 — WorkOS account + custom domain mapping

Runbook for Hussain. All work happens in the WorkOS dashboard +
Cloudflare DNS. No code changes on this ticket — Claude picks up
with MIL-61 once you have the JWKS URL + Client ID.

## What this accomplishes

1. A WorkOS organisation exists with AuthKit configured for CJI Pro
2. login.cjipro.com is REGISTERED with WorkOS as a future custom
   domain, but the DNS CNAME is NOT yet switched — the MIL-59
   placeholder keeps serving until MIL-63 is ready to flip
3. Claude has the four values needed to build the Edge Bouncer
   (MIL-61): JWKS URL, Client ID, AuthKit Domain, Organisation ID

## Step 1 — create the WorkOS account

1. Go to `https://dashboard.workos.com/signup`
2. Sign up with `hello@cjipro.com` (or your work email)
3. Create an organisation name: `CJI Pro`
4. Region: **EU** (data residency matters for UK bank customers —
   WorkOS's EU region keeps auth data in-region, which is a
   procurement positive signal at Phase 3)

## Step 2 — pick the environment

WorkOS gives you two environments by default: **Sandbox** and
**Production**. Use **Sandbox** for MIL-60/61/62 alpha testing. Keep
Production pristine and only switch over when the Apr 28 auto-fire
proves the stack out.

In the dashboard top-bar, make sure the environment selector says
**Sandbox** before proceeding.

## Step 3 — configure AuthKit

AuthKit is WorkOS's hosted login UI. Left sidebar → **Authentication**
→ **AuthKit**.

Settings to enable on the sandbox:
- **Magic link**: ON
- **Password**: OFF (Phase 1 is magic-link-only per MIL-63)
- **SSO**: OFF (comes online in MIL-70)
- **Passkey**: OFF for now (comes online in MIL-67)
- **Session expiry**: 24h (MIL-68 will tune sliding windows later)

Appearance tab:
- Background colour: `#FAFAF7` (cream, matches cjipro.com)
- Accent colour: `#003A5C` (deep blue)
- Logo: upload a simple CJI Pro wordmark if you have one, otherwise
  leave the default WorkOS branding off
- Sign-in heading: "Sign in to CJI Pro"

## Step 4 — register login.cjipro.com as a custom domain (do NOT flip DNS yet)

Left sidebar → **Domains** → **Add domain** → enter `login.cjipro.com`.

WorkOS displays:
- A CNAME target (something like `redirect.workos.com` or
  `<tenant>.authkit.app`)
- A TLS certificate validation record (a TXT record)

**Do not add these DNS records in Cloudflare yet.** We need the
placeholder (MIL-59) to keep serving while we build MIL-61. Just
screenshot / copy-paste the CNAME target and TXT record somewhere
you can find them for MIL-63.

(Why the delay: if you add the CNAME now, login.cjipro.com
immediately flips to WorkOS's default AuthKit UI, replacing the
"Coming soon" placeholder with a functional email field pointing
at a directory with zero users. Partners hitting that would see a
broken-feeling experience. We flip the DNS as the LAST step of
MIL-63 when the full magic-link flow is ready.)

## Step 5 — record the four values Claude needs for MIL-61

Find and record these in a note you can paste into the next Claude
session:

| Value | Where in WorkOS dashboard | Looks like |
|---|---|---|
| **Organisation ID** | Top of the dashboard, next to your org name | `org_01H...` |
| **Client ID** | API Keys → Public → Client ID | `client_01H...` |
| **JWKS URL** | API Keys → Public → JWKS URL | `https://api.workos.com/sso/jwks/client_01H...` |
| **AuthKit Domain** | Authentication → AuthKit → Domain | `<tenant>.authkit.app` or `login.cjipro.com` once DNS is switched |

The **API Secret Key** (private) you'll also need — keep it in
`.env` on your local machine as `WORKOS_API_KEY`. Claude will
reference the env var name but never see the actual key.

## Step 6 — (optional) set up a directory with your email

Left sidebar → **User Management** → **Users** → **Add User**.

Add `hello@cjipro.com` (or your work email). This gives you a valid
user to test magic-link flows against once MIL-63 ships.

## What you are NOT doing in this ticket

- **Not flipping DNS** — login.cjipro.com stays pointed at the
  MIL-59 placeholder until MIL-63 is ready
- **Not writing any code** — the WorkOS-side client library
  integration happens in MIL-61 (Edge Bouncer)
- **Not enabling SSO or passkeys** — those are later tickets

## Acceptance

- [ ] WorkOS account exists, environment selector says **Sandbox**
- [ ] AuthKit configured (magic link on, password/SSO off)
- [ ] login.cjipro.com registered as a custom domain in WorkOS
      (CNAME + TXT records captured but NOT added to Cloudflare DNS)
- [ ] Four values captured for MIL-61: Organisation ID, Client ID,
      JWKS URL, AuthKit Domain
- [ ] `WORKOS_API_KEY` added to local `.env` file

## When this is done

Start the next Claude session with:
```
MIL-60 complete. Here are the values for MIL-61:
  Organisation ID: org_01H...
  Client ID:       client_01H...
  JWKS URL:        https://api.workos.com/sso/jwks/...
  AuthKit Domain:  <tenant>.authkit.app
Let's build MIL-61.
```

Claude picks up from there.
