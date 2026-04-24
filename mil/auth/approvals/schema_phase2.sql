-- MIL-66b — Phase 2 schema additions
--
-- Target:  same mil-auth-audit D1 as Phase 1.
-- Pattern: mutable admin data, alongside (but logically separate from)
--          the append-only audit log.
--
-- Three new tables:
--   1. pending_signups   — self-service access requests
--   2. admin_users       — who can approve/deny/revoke (strict subset
--                          of approved_users; being admin implies
--                          being approved)
--   3. signup_rate_limit — per-IP hour-window counter for
--                          POST /request-access throttling

-- Self-service signup requests. status transitions:
--   pending → approved  (admin approves; row copied into approved_users)
--   pending → denied    (admin denies; left here as record)
-- Re-submissions by the same email while a pending row exists are
-- rejected at the application layer (see signups.ts::submitRequest).
CREATE TABLE IF NOT EXISTS pending_signups (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT    NOT NULL,            -- canonical lowercase
  requested_at  TEXT    NOT NULL,            -- ISO-8601 UTC
  ip_hash       TEXT,                        -- sha256(ip || daily_salt)
  ua_hash       TEXT,                        -- sha256(ua)
  note          TEXT,                        -- optional user-supplied reason
  status        TEXT    NOT NULL DEFAULT 'pending',  -- pending|approved|denied
  reviewed_at   TEXT,                        -- set when status != 'pending'
  reviewed_by   TEXT                         -- admin email who reviewed
);

CREATE INDEX IF NOT EXISTS idx_pending_signups_status
  ON pending_signups(status, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_pending_signups_email
  ON pending_signups(email);

-- Admins. PK is email (canonical lowercase). Being in this table
-- AND in approved_users is the two-part gate for /admin access.
CREATE TABLE IF NOT EXISTS admin_users (
  email     TEXT PRIMARY KEY,
  added_at  TEXT NOT NULL,
  added_by  TEXT NOT NULL                    -- 'bootstrap' or another admin's email
);

-- Per-IP hour-window rate limit for POST /request-access.
-- Key: (ip_hash, window). window = 'YYYY-MM-DDTHH' (UTC hour).
-- Rows older than 24h can be GC'd by a housekeeping query; not
-- essential for correctness, only for table-size hygiene.
CREATE TABLE IF NOT EXISTS signup_rate_limit (
  ip_hash  TEXT NOT NULL,
  window   TEXT NOT NULL,                    -- 'YYYY-MM-DDTHH' UTC
  count    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ip_hash, window)
);
