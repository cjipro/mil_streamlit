-- MIL-152 — partner_profiles table.
--
-- Per-sub partner attributes that don't belong on the sessions row
-- (which is "did this user authenticate" — narrow-purpose). The
-- portal (MIL-151) and partner workspace (MIL-144) need:
--   display_name + role  — self-affirmed (FCA Consumer Duty 2.0
--                          periodic touchpoint), free text
--   firm_slug + firm_name — admin-set, NOT user-editable. Routes
--                           the partner to /sonar/{firm_slug}/.
--                           Self-set would let an attacker spoof
--                           firm context and read another firm's
--                           briefing — same fail-closed posture as
--                           the approved_users allowlist.
--   contact_email + contact_pref — defaults to sessions.email; user
--                                   may override on confirm flow.
--   last_confirmed_at + last_confirmed_hash — drives the 90-day
--                          re-affirmation prompt. The hash is
--                          sha256 of the canonicalised affirmed
--                          payload so the admin dashboard can tell
--                          a real change from a no-op reaffirm.
--
-- Lifecycle: row is INSERTed (idempotent) on first /callback for a
-- new sub with contact_email = session.email + everything else NULL.
-- Admin populates firm_slug/firm_name via the partner_set_firm API.
-- User populates display_name/role via POST /portal/confirm.

CREATE TABLE IF NOT EXISTS partner_profiles (
  sub TEXT PRIMARY KEY,
  display_name TEXT,
  role TEXT,
  firm_slug TEXT,
  firm_name TEXT,
  contact_email TEXT,
  contact_pref TEXT NOT NULL DEFAULT 'email-only',
  last_confirmed_at TEXT,
  last_confirmed_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_partner_profiles_firm_slug
  ON partner_profiles(firm_slug);
