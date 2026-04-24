# MIL-66a — Approved-user allowlist (Phase 1)

Phase 1 of MIL-66. After the edge-bouncer verifies a WorkOS JWT, it
additionally checks the `email` claim against this allowlist. If the
email isn't present, the user gets a 403 "Access pending" page instead
of the briefing.

## What this buys us (and what it doesn't)

- **Buys**: a real gate. Random people who find `login.cjipro.com`
  and sign up via AuthKit can no longer land on the briefing. The
  alpha cohort is now a closed set.
- **Does not buy**: a signup UX, a partner-onboarding flow, or an
  admin dashboard. Adding users is a shell-script step that only
  Hussain runs. Phase 2 (self-service signup + admin Streamlit page)
  is tracked separately.

## Data model

Single table in the same D1 (`mil-auth-audit`) as the audit log:

```sql
CREATE TABLE approved_users (
  email        TEXT PRIMARY KEY,  -- canonical lowercase
  approved_at  TEXT NOT NULL,     -- ISO-8601 UTC
  approved_by  TEXT NOT NULL,     -- free text
  note         TEXT
);
```

Emails are **case-insensitive** — the lookup lowercases both sides.
The `add_user.sh` helper lowercases at write time so the table
stores canonical form.

## Admin workflow

All three scripts run from anywhere; they `cd` to the edge-bouncer
Worker directory internally to pick up the `AUDIT_DB` binding.

```bash
# List the current allowlist
./scripts/list_users.sh

# Add an approved user
./scripts/add_user.sh user@example.com "hussain" "alpha cohort, barclays risk"

# Remove an approved user (revokes future access; audit history intact)
./scripts/remove_user.sh user@example.com
```

Revocation is immediate — the next request from a revoked user hits
the gate and gets the 403 page.

## Failure modes

- **Empty allowlist** — every authenticated user is denied. This is
  the explicit initial state before bootstrap. Seed BEFORE redeploying
  with `ENFORCE=true`.
- **AUDIT_DB binding missing** — the gate fails CLOSED (deny). If the
  D1 is unreachable we'd rather block than silently let everyone in.
- **Email claim missing from JWT** — deny (fail closed). WorkOS
  AuthKit includes `email` by default; if it ever stops, we want to
  know by seeing denies, not silent passes.
- **Shadow mode (`ENFORCE=false`)** — decisions are still computed
  and audit-logged, but denials don't 403 the user. Use this to
  verify the gate is working as expected before enforcement flips on.

## Seed command for bootstrap

Run once before flipping `ENFORCE=true` on edge-bouncer. Replace
emails with the actual alpha cohort:

```bash
./scripts/add_user.sh hussain.marketing@gmail.com "bootstrap" "project owner"
./scripts/add_user.sh hussain.x.ahmed@barclays.com "bootstrap" "alpha partner"
```

## Audit trail

Every denial writes a `bouncer.deny.not_approved` event to the audit
log with the user's hashed sub + email-bearing JWT. Query:

```bash
npx wrangler d1 execute mil-auth-audit --remote --command \
  "SELECT ts, path, reason, enforce FROM auth_events
   WHERE event_type = 'bouncer.deny.not_approved'
   ORDER BY id DESC LIMIT 20"
```
