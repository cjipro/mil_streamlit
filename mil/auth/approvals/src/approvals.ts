// MIL-66a — approved-user allowlist lookup.
//
// Called from edge-bouncer after JWT verification succeeds. Returns
// true iff the JWT's email claim matches a row in approved_users.
//
// Case-insensitive: emails are stored lowercase, and the lookup
// lowercases the input. Empty/undefined input always returns false.

export async function isApproved(
  db: D1Database,
  email: string | undefined | null,
): Promise<boolean> {
  if (!email) return false;
  const canonical = email.trim().toLowerCase();
  if (!canonical) return false;

  const row = await db
    .prepare("SELECT 1 AS present FROM approved_users WHERE email = ? LIMIT 1")
    .bind(canonical)
    .first<{ present: number }>();

  return row?.present === 1;
}

// Admin helper — normalise an email before writing to the table.
// Useful in the add/remove scripts so operators can't accidentally
// create rows that the lookup won't find.
export function canonicalEmail(raw: string): string {
  return raw.trim().toLowerCase();
}
