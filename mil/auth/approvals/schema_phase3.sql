-- MIL-66c — sessions: sub → email mapping
--
-- WorkOS User Management access tokens carry `sub` but NOT `email`.
-- Approval gates need the email to look up approved_users / admin_users.
-- Solution: when /callback fires (the only place we have both sub AND
-- the user's email, via the WorkOS exchange response body), persist
-- the mapping. Bouncer + admin_gate then look it up by sub.
--
-- INSERT OR REPLACE on every callback: one row per WorkOS user, the
-- email is updated if the user changes their address upstream.
-- created_at is for diagnostics + cleanup; not enforced.

CREATE TABLE IF NOT EXISTS sessions (
  sub         TEXT PRIMARY KEY,    -- WorkOS user ID (stable across logins)
  email       TEXT NOT NULL,       -- canonical lowercase
  created_at  TEXT NOT NULL        -- ISO-8601 UTC
);
