-- MIL-72 — per-tenant audit export support.
--
-- Sessions get an organization_id column so the export query can
-- scope auth_events to a single partner. Populated by /callback
-- from the WorkOS exchange response (user.organization_id when
-- present; NULL for users not associated with a WorkOS Org —
-- typically alpha individual sign-ups).
--
-- ALTER ADD COLUMN is safe in SQLite — existing rows get NULL until
-- the user signs in again post-deploy. The export query treats NULL
-- organization_id as "global / un-tenanted".

ALTER TABLE sessions ADD COLUMN organization_id TEXT;

CREATE INDEX IF NOT EXISTS idx_sessions_org
  ON sessions(organization_id);
