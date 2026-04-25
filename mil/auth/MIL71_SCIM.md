# MIL-71 — SCIM (Directory Sync) Auto-Provisioning

When a partner removes a user from their IdP (Okta/Azure AD/Google
Workspace), WorkOS fires `dsync.user.deleted` to our webhook. We
auto-revoke + force-signout that user with no admin intervention.

When a partner ADDS a user, we audit the event but do NOT auto-grant
access by default — the partner's WorkOS organization has to be
explicitly opted in to auto-approval (see "Auto-approve safety"
below). This prevents an attacker who compromises a WorkOS org from
auto-granting themselves access to our system.

## Setup per partner organization

This builds on MIL-70's onboarding flow. After the partner has SAML
working:

### 1. Have the partner enable SCIM in WorkOS Admin Portal

Generate a fresh setup link for them with intent=`dsync` (use the
admin dashboard's "Partner SSO setup link" form). Their IT pastes
the SCIM endpoint + bearer token from the Admin Portal into their
IdP's SCIM provisioning config.

### 2. Decide whether to auto-approve

Before flipping auto-approve, decide: **do you trust this partner's
IdP to govern who gets access to CJI Pro?**

- **YES** (partner has good off-boarding hygiene, contractual SLA
  on access removal, etc.): mark their org auto-approve, every
  newly-provisioned user gets immediate access.
- **NO** (partner is a brand-new alpha, or IdP turns over fast):
  leave it off. SCIM provisioning becomes audit-only — admin still
  manually adds users via the dashboard's signup-approval flow.

Either way, SCIM **deprovisioning** is always automatic. Removing
access is never gated on the org's auto-approve status.

### 3. Mark org auto-approve (if YES)

```bash
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cd mil/auth/edge_bouncer
npx wrangler d1 execute mil-auth-audit --remote --command \
  "INSERT OR IGNORE INTO auto_approve_orgs \
    (organization_id, added_at, added_by, note) VALUES \
    ('org_01HXYZ...', '$TS', 'hussain@cjipro', 'partner bank — SCIM trusted')"
```

### 4. Test with one provision + one deprovision

Have the partner provision a test user from their IdP. Within a few
seconds you should see in the audit log:

```bash
npx wrangler d1 execute mil-auth-audit --remote --json --command \
  "SELECT id, ts, event_type, reason, detail FROM auth_events
   WHERE event_type LIKE 'dsync.%'
   ORDER BY id DESC LIMIT 10"
```

| event_type | reason | detail |
|---|---|---|
| `dsync.user.auto_approved` | the user's email | the org_id |
| (or) `dsync.user.created` | the user's email | `pending:<org_id>` |

For deprovision, the partner removes the user from their IdP. You
should then see:

| event_type | reason | detail |
|---|---|---|
| `dsync.user.auto_revoked` | the user's email | `revoke:ok signout:ok` |

If you see `revoke:not-found signout:not-found`, the user wasn't
actually on our allowlist when they were removed — usually because
the partner provisioned them before MIL-71 shipped, or the org isn't
auto-approve. Check by querying `approved_users` directly.

## Event routing semantics

| WorkOS event | Side effect | Audit event_type |
|---|---|---|
| `dsync.user.created` (org auto-approve) | Add to approved_users | `dsync.user.auto_approved` |
| `dsync.user.created` (org NOT auto-approve) | none | `dsync.user.created` |
| `dsync.user.created` (no email in payload) | none | `dsync.user.created` (detail=`no-email-in-payload`) |
| `dsync.user.updated` | none (Phase B will track email changes) | `dsync.user.updated` |
| `dsync.user.deleted` | revokeApproval + forceSignout | `dsync.user.auto_revoked` |
| `dsync.group.user_added` | none | `dsync.group.user_added` |
| `dsync.group.user_removed` | none | `dsync.group.user_removed` |
| `dsync.<other>` | none | `workos.webhook` (generic fallback) |

Side-effect functions are idempotent — re-delivery from WorkOS is
safe.

## Auto-approve safety

The threat model: an attacker who compromises a partner's WorkOS
account could provision themselves a user and inherit access to our
system. The auto_approve_orgs allowlist requires admin opt-in per
org, so this attack only works against orgs you've explicitly
trusted. For untrusted orgs, the worst the attacker can do is fill
the audit log with `dsync.user.created` rows that never grant access.

The OPPOSITE risk — an attacker provisioning a `dsync.user.deleted`
event to lock out a real user — is mitigated by WorkOS's webhook
signature verification. Without the signing secret (already
required since MIL-67a), the attacker can't fake events.

## Backfilling an org you forgot to mark auto-approve

If you marked an org auto-approve AFTER they'd already provisioned
users, those users are sitting in audit_events as
`dsync.user.created` (status: pending) but not in approved_users.

Backfill them with a single query:

```bash
cd mil/auth/edge_bouncer
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
npx wrangler d1 execute mil-auth-audit --remote --command \
  "INSERT OR IGNORE INTO approved_users (email, approved_at, approved_by, note) \
   SELECT DISTINCT lower(reason), '$TS', 'scim-backfill', 'auto-approve backfill' \
   FROM auth_events \
   WHERE event_type = 'dsync.user.created' \
     AND detail LIKE 'pending:org_01HXYZ%' \
     AND reason LIKE '%@%'"
```

## Removing auto-approve

```bash
cd mil/auth/edge_bouncer
npx wrangler d1 execute mil-auth-audit --remote --command \
  "DELETE FROM auto_approve_orgs WHERE organization_id = 'org_01HXYZ...'"
```

Existing approved users from that org keep their access. Future
SCIM provisioning becomes audit-only again.
