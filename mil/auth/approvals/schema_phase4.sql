-- MIL-68 — sessions activity tracking
--
-- Add last_active_at to the existing sessions table. Bouncer writes
-- it on every pass.session decision (fire-and-forget via waitUntil
-- so the user response is never blocked). Admin dashboard reads it
-- to show "Last seen Xmin ago" per approved user.
--
-- ALTER ADD COLUMN is safe in SQLite — existing rows get NULL until
-- the next bouncer pass writes a value. The dashboard renders NULL
-- as "—" (never seen since this column was added).

ALTER TABLE sessions ADD COLUMN last_active_at TEXT;

CREATE INDEX IF NOT EXISTS idx_sessions_last_active
  ON sessions(last_active_at DESC);
