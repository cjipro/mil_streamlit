-- MIL-65 — Immutable auth event audit log
--
-- Target:  Cloudflare D1 (SQLite dialect).
-- Pattern: append-only, row-hash chained, PII minimised via salted hashes.
--
-- Invariants (enforced in application code, not DDL):
--   1. No UPDATE, no DELETE — ever. The audit log is append-only.
--   2. Every row carries prev_hash + row_hash. Genesis row's prev_hash
--      is the literal string 'genesis'.
--   3. row_hash = sha256_hex(canonical_json(content) || '|' || prev_hash)
--      where content is every column EXCEPT id, prev_hash, row_hash.
--   4. No raw IPs, user agents, emails, or JWTs are stored. Only
--      sha256(value || daily_salt) hashes. Daily salts rotate the
--      correlation window to 24h.
--   5. Verifier (src/verify.ts) walks the chain and flags any row
--      whose recomputed row_hash ≠ stored row_hash, OR whose prev_hash
--      ≠ the prior row's row_hash.

CREATE TABLE IF NOT EXISTS auth_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts            TEXT    NOT NULL,             -- ISO-8601 UTC
  worker        TEXT    NOT NULL,             -- 'magic-link' | 'edge-bouncer'
  event_type    TEXT    NOT NULL,             -- see src/types.ts AuthEventType
  method        TEXT,                         -- GET, POST, ...
  host          TEXT,                         -- cjipro.com, login.cjipro.com
  path          TEXT,                         -- /briefing-v4, /callback, ...
  enforce       INTEGER,                      -- 0 | 1 (bouncer only)
  user_hash     TEXT,                         -- sha256(jwt_sub || daily_salt)
  ip_hash       TEXT,                         -- sha256(ip       || daily_salt)
  ua_hash       TEXT,                         -- sha256(ua)
  country       TEXT,                         -- cf.country, 2-letter
  reason        TEXT,                         -- short enum; see types.ts
  detail        TEXT,                         -- optional free-text
  prev_hash     TEXT    NOT NULL,
  row_hash      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_events_ts          ON auth_events(ts);
CREATE INDEX IF NOT EXISTS idx_auth_events_user        ON auth_events(user_hash);
CREATE INDEX IF NOT EXISTS idx_auth_events_worker_type ON auth_events(worker, event_type);

-- Daily salt table. First event of each UTC day generates the salt
-- via crypto.getRandomValues and inserts it here. Subsequent events
-- that day read it back. Salts are immutable once written.
CREATE TABLE IF NOT EXISTS audit_salts (
  date TEXT PRIMARY KEY,                      -- YYYY-MM-DD UTC
  salt TEXT NOT NULL                          -- 32 bytes hex (64 chars)
);
