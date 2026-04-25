// MIL-71 — auto-approve organization allowlist.
//
// Lookup function used by the SCIM event router (webhooks.ts) to
// decide whether to auto-add a newly-provisioned user to
// approved_users. Without an entry in auto_approve_orgs, the event
// is audit-only — admin still has to add the user manually.

export async function isAutoApproveOrg(
  db: D1Database,
  organizationId: string | undefined | null,
): Promise<boolean> {
  if (!organizationId) return false;
  const row = await db
    .prepare(
      "SELECT 1 AS present FROM auto_approve_orgs WHERE organization_id = ? LIMIT 1",
    )
    .bind(organizationId)
    .first<{ present: number }>();
  return row?.present === 1;
}

// Admin write — typically called from a script or one-off SQL.
// Idempotent: calling twice on the same org is a no-op.
export async function addAutoApproveOrg(
  db: D1Database,
  organizationId: string,
  addedBy: string,
  note: string | null = null,
  now: Date = new Date(),
): Promise<void> {
  await db
    .prepare(
      `INSERT OR IGNORE INTO auto_approve_orgs
        (organization_id, added_at, added_by, note)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(organizationId, now.toISOString(), addedBy, note)
    .run();
}

export async function removeAutoApproveOrg(
  db: D1Database,
  organizationId: string,
): Promise<{ kind: "ok"; affected: number } | { kind: "not-found" }> {
  const result = await db
    .prepare("DELETE FROM auto_approve_orgs WHERE organization_id = ?")
    .bind(organizationId)
    .run();
  const meta = (result as { meta?: { changes?: number } }).meta;
  const changes = meta?.changes ?? 0;
  if (changes === 0) return { kind: "not-found" };
  return { kind: "ok", affected: changes };
}
