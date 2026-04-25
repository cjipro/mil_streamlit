// MIL-66c — sub → email mapping for WorkOS sessions.
//
// /callback is the only place we have both sub (from access_token JWT)
// and email (from the WorkOS authenticate response body). Write here,
// read at the gates. Lookup is O(1) via the PK.

import { canonicalEmail } from "./approvals";

export async function writeSession(
  db: D1Database,
  sub: string,
  email: string,
  now: Date = new Date(),
): Promise<void> {
  const canonical = canonicalEmail(email);
  await db
    .prepare(
      `INSERT OR REPLACE INTO sessions (sub, email, created_at) VALUES (?, ?, ?)`,
    )
    .bind(sub, canonical, now.toISOString())
    .run();
}

export async function lookupSessionEmail(
  db: D1Database,
  sub: string | undefined | null,
): Promise<string | undefined> {
  if (!sub) return undefined;
  const row = await db
    .prepare("SELECT email FROM sessions WHERE sub = ? LIMIT 1")
    .bind(sub)
    .first<{ email: string }>();
  return row?.email;
}

// MIL-68 — bump last_active_at on the sessions row for this sub.
// Fire-and-forget: callers wrap in ctx.waitUntil so the user response
// isn't blocked. Silent if no row exists for this sub (the gate would
// have already denied; nothing to record).
export async function recordActivity(
  db: D1Database,
  sub: string,
  now: Date = new Date(),
): Promise<void> {
  await db
    .prepare("UPDATE sessions SET last_active_at = ? WHERE sub = ?")
    .bind(now.toISOString(), sub)
    .run();
}

export interface ApprovedWithSession {
  email: string;
  approved_at: string;
  approved_by: string;
  note: string | null;
  last_active_at: string | null;
}

// MIL-68 — admin dashboard query: every approved user, optionally
// joined with the latest session row for that email. LEFT JOIN so
// users who haven't signed in yet still appear (last_active_at NULL).
export async function listApprovedWithSessions(
  db: D1Database,
  limit = 200,
): Promise<ApprovedWithSession[]> {
  const res = await db
    .prepare(
      `SELECT au.email, au.approved_at, au.approved_by, au.note,
              s.last_active_at
       FROM approved_users au
       LEFT JOIN sessions s ON s.email = au.email
       ORDER BY au.approved_at DESC
       LIMIT ?`,
    )
    .bind(limit)
    .all<ApprovedWithSession>();
  return res.results ?? [];
}

// MIL-68 — drop every session row matching this email. Effective
// revocation of any cached JWT held by that user (next bouncer hit
// will fail the sub→email lookup and deny). Different from
// revokeApproval which removes them from approved_users entirely;
// force_signout boots the live session but leaves them eligible to
// sign back in.
export async function forceSignout(
  db: D1Database,
  email: string,
): Promise<{ kind: "ok"; affected: number } | { kind: "not-found" }> {
  const canonical = canonicalEmail(email);
  const result = await db
    .prepare("DELETE FROM sessions WHERE email = ?")
    .bind(canonical)
    .run();
  const meta = (result as { meta?: { changes?: number } }).meta;
  const changes = meta?.changes ?? 0;
  if (changes === 0) return { kind: "not-found" };
  return { kind: "ok", affected: changes };
}
