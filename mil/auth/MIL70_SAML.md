# MIL-70 — SAML Self-Configuration via WorkOS Admin Portal

WorkOS hosts the entire SSO/SAML/SCIM admin UI on `setup.workos.com`.
We never see a SAML XML; we never write IdP metadata parsing. We
generate a one-shot 5-minute setup link tied to a partner's
organization, share it with their IT team, they configure their IdP
(Okta / Azure AD / Google Workspace / OneLogin / etc.) inside
WorkOS's hosted UI. Webhook events flow back to our audit log when
the connection activates.

This makes "enterprise SSO support" a config conversation, not an
engineering project.

## Onboarding a partner organization

### 1. Create the organization in WorkOS

WorkOS dashboard → **Organizations** → **+ Create Organization**:
- Name: `Partner Bank Plc` (whatever the partner calls themselves)
- Domains: `partnerbank.com` (one or more — these gate which emails
  WorkOS auto-routes to this org's SSO connection later)

After saving, copy the `org_01...` id from the URL or the org detail
page. You'll paste it in step 4.

### 2. Add the partner's alpha contacts to approved_users

Until SAML activates, the partner's users still sign in via magic-
link from `login.cjipro.com`. So they need to be on the allowlist:

```bash
cd mil/auth/approvals
./scripts/add_user.sh contact1@partnerbank.com hussain "alpha — partner bank IT lead"
./scripts/add_user.sh contact2@partnerbank.com hussain "alpha — partner bank business"
```

### 3. (optional) Make a partner-side admin

If the partner's IT lead should manage their own approvals later,
add them to `admin_users` too:

```bash
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cd mil/auth/edge_bouncer
npx wrangler d1 execute mil-auth-audit --remote --command \
  "INSERT INTO admin_users (email, added_at, added_by) VALUES \
    ('contact1@partnerbank.com', '$TS', 'hussain@cjipro')"
```

### 4. Generate the setup link

Sign in to https://login.cjipro.com/admin → scroll to
**Partner SSO setup link** → paste the `org_01...` id from step 1
→ pick intent → click **Generate**.

| Intent | Use when |
|---|---|
| `sso` | Set up SAML / OIDC SSO connection (most common starting point) |
| `domain_verification` | Verify the partner controls a domain (DNS TXT record) |
| `dsync` | SCIM directory sync (auto-provision users from Okta / etc.) |
| `audit_logs` | Partner-facing audit log streams (rare for alpha) |
| `log_streams` | Real-time log forwarding to partner's SIEM (rare for alpha) |

Copy the link → email it to the partner's IT contact. Subject
something like *"CJI Pro SSO setup — link expires in 5 min, ping me
when ready"*. Link is single-use-shaped (it 302s into a long-lived
session on WorkOS's side once the partner clicks it).

### 5. Partner completes setup

Inside WorkOS's hosted page, the partner:
1. Picks their IdP (Okta, Azure AD, Google Workspace, etc.)
2. Pastes IdP metadata URL or uploads XML
3. Configures attribute mapping (email → email is usually the only
   one we need for alpha)
4. Tests with a sample sign-in

When they finish, WorkOS fires webhook events to our
`/webhooks/workos` endpoint. With Phase B of MIL-67 (typed mapping),
these will land in `auth_events` as `connection.activated`. Until
Phase B ships, they show up as `workos.webhook` with
`reason='connection.activated'` (or whatever WorkOS's event-type
string is — check the audit log to confirm).

### 6. Cut the partner over

Once their connection is active, their users sign in via
`login.cjipro.com/` → AuthKit detects the email domain matches their
org → routes to the SAML IdP → no more magic-link emails for them.

You can revoke their magic-link access at this point if you want
SAML-only:

```bash
cd mil/auth/approvals
./scripts/remove_user.sh contact1@partnerbank.com
# they can still sign in via SSO; they're just no longer on the
# magic-link fallback allowlist
```

## Verifying activation

```bash
cd mil/auth/edge_bouncer
npx wrangler d1 execute mil-auth-audit --remote --json --command \
  "SELECT id, ts, event_type, reason, detail FROM auth_events
   WHERE event_type IN ('workos.webhook', 'connection.activated',
                        'connection.deactivated', 'connection.deleted',
                        'admin.portal_link_generated')
   ORDER BY id DESC LIMIT 30"
```

You'll see:
- `admin.portal_link_generated` (you, when you clicked Generate)
- `workos.webhook` with `reason='connection.activated'` (when the
  partner finishes setup)
- Subsequent `magic_link.callback.success` events from their users
  (the OAuth flow completion still hits our /callback regardless of
  whether the IdP was SAML or magic-link upstream)

## Failure modes

- **Generate returns 404** — bad organization id; double-check in
  the WorkOS dashboard.
- **Generate returns 401** — `WORKOS_CLIENT_SECRET` is wrong or
  rotated. Refresh in `wrangler secret put WORKOS_CLIENT_SECRET`.
- **Link expired before partner clicked** — generate a new one.
  WorkOS doesn't accept stale links.
- **Partner sets up SSO but their users still get magic-link emails**
  — check that the email domain on the user matches a domain
  registered on the WorkOS Organization. Domain mismatch → AuthKit
  falls back to magic-link.
- **Webhook events not arriving** — check `/webhooks/workos` is
  configured in WorkOS dashboard with the right URL + signing secret.
  See `MIL67_PASSKEYS.md` step 2.

## Out of scope for MIL-70

- Per-tenant audit log export (MIL-72)
- SCIM lifecycle hooks beyond what WorkOS surfaces in webhooks (MIL-71)
- Bulk user provisioning UI on our side (use partner's IdP for that)
