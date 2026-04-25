-- MIL-71 — auto-approve organization allowlist.
--
-- WorkOS Organization IDs that are trusted to provision users
-- via SCIM. When a dsync.user.created event arrives for a user in
-- one of these orgs, we auto-add their email to approved_users.
--
-- Without this allowlist, dsync.user.created is audit-only — an
-- attacker who compromises a WorkOS organization can't auto-grant
-- themselves access to our system. The admin must explicitly opt
-- each org in via the dashboard or this table.

CREATE TABLE IF NOT EXISTS auto_approve_orgs (
  organization_id TEXT PRIMARY KEY,    -- WorkOS org_01... id
  added_at        TEXT NOT NULL,
  added_by        TEXT NOT NULL,
  note            TEXT
);
