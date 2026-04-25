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
