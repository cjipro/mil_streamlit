// MIL-66b — admin allowlist (strict subset of approved_users).
//
// An email being in admin_users grants access to /admin endpoints.
// Membership in admin_users implies membership in approved_users by
// convention but is NOT enforced by the schema — application code
// must check both gates. (Why not FK? Deleting an approved_users row
// would CASCADE-remove the admin role, which is usually what you
// want, but the order of operations during revoke could briefly
// leave an "admin but not approved" state; explicit two-check is
// simpler to reason about.)

import { canonicalEmail } from "./approvals";

export async function isAdmin(
  db: D1Database,
  email: string | undefined | null,
): Promise<boolean> {
  if (!email) return false;
  const canonical = canonicalEmail(email);
  if (!canonical) return false;

  const row = await db
    .prepare("SELECT 1 AS present FROM admin_users WHERE email = ? LIMIT 1")
    .bind(canonical)
    .first<{ present: number }>();
  return row?.present === 1;
}
