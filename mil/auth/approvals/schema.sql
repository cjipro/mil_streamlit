-- MIL-66a — Approved-user allowlist (Phase 1 signup gate)
--
-- Target:  same D1 as mil-auth-audit (mutable admin data lives
--          alongside the immutable audit log; keeps one D1 binding).
-- Pattern: mutable allowlist. Not hash-chained. Admin adds/removes
--          rows via wrangler d1 execute (scripts/ helpers wrap it).
--
-- Case-insensitivity: emails are lowercased at INSERT time. The
-- bouncer lookup also lowercases the JWT email claim. `email` is PK.

CREATE TABLE IF NOT EXISTS approved_users (
  email        TEXT    PRIMARY KEY,        -- canonical lowercase
  approved_at  TEXT    NOT NULL,           -- ISO-8601 UTC
  approved_by  TEXT    NOT NULL,           -- free text: human or 'bootstrap'
  note         TEXT                        -- optional context (partner org, cohort)
);

CREATE INDEX IF NOT EXISTS idx_approved_users_approved_at
  ON approved_users(approved_at);
