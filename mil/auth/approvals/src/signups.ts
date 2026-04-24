// MIL-66b — self-service signup request lifecycle.
//
// Pure application logic over D1. Each function is independently
// testable against the FakeD1. No Worker imports — keeps this lib
// reusable from any environment that can talk to D1.

import { canonicalEmail } from "./approvals";

export type SignupStatus = "pending" | "approved" | "denied";

export interface PendingSignup {
  id: number;
  email: string;
  requested_at: string;
  ip_hash: string | null;
  ua_hash: string | null;
  note: string | null;
  status: SignupStatus;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export type SubmitOutcome =
  | { kind: "created"; id: number }
  | { kind: "already-approved" }
  | { kind: "already-pending"; id: number }
  | { kind: "invalid-email" };

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isPlausibleEmail(raw: string): boolean {
  return EMAIL_REGEX.test(raw);
}

export async function submitRequest(
  db: D1Database,
  input: {
    email: string;
    note?: string;
    ipHash?: string;
    uaHash?: string;
  },
  now: Date = new Date(),
): Promise<SubmitOutcome> {
  const email = canonicalEmail(input.email);
  if (!isPlausibleEmail(email)) return { kind: "invalid-email" };

  // Already approved? No-op — they should just sign in.
  const approved = await db
    .prepare("SELECT 1 AS present FROM approved_users WHERE email = ? LIMIT 1")
    .bind(email)
    .first<{ present: number }>();
  if (approved?.present === 1) return { kind: "already-approved" };

  // Already pending? Return the existing id rather than duplicate.
  const pending = await db
    .prepare(
      "SELECT id FROM pending_signups WHERE email = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
    )
    .bind(email)
    .first<{ id: number }>();
  if (pending) return { kind: "already-pending", id: pending.id };

  const result = await db
    .prepare(
      `INSERT INTO pending_signups
         (email, requested_at, ip_hash, ua_hash, note, status)
       VALUES (?, ?, ?, ?, ?, 'pending')`,
    )
    .bind(
      email,
      now.toISOString(),
      input.ipHash ?? null,
      input.uaHash ?? null,
      input.note ?? null,
    )
    .run();

  const id =
    (result as { meta?: { last_row_id?: number } }).meta?.last_row_id ?? 0;
  return { kind: "created", id };
}

export async function listByStatus(
  db: D1Database,
  status: SignupStatus,
  limit = 100,
): Promise<PendingSignup[]> {
  const res = await db
    .prepare(
      `SELECT * FROM pending_signups
       WHERE status = ?
       ORDER BY requested_at DESC
       LIMIT ?`,
    )
    .bind(status, limit)
    .all<PendingSignup>();
  return res.results ?? [];
}

export type ReviewOutcome =
  | { kind: "ok" }
  | { kind: "not-found" }
  | { kind: "not-pending"; current_status: SignupStatus };

export async function approvePending(
  db: D1Database,
  id: number,
  adminEmail: string,
  now: Date = new Date(),
): Promise<ReviewOutcome> {
  const row = await db
    .prepare("SELECT email, status FROM pending_signups WHERE id = ?")
    .bind(id)
    .first<{ email: string; status: SignupStatus }>();
  if (!row) return { kind: "not-found" };
  if (row.status !== "pending") {
    return { kind: "not-pending", current_status: row.status };
  }

  const ts = now.toISOString();
  const admin = canonicalEmail(adminEmail);

  // Two writes: move the email into approved_users, then mark the
  // pending row reviewed. INSERT OR IGNORE on approved_users means
  // re-approving an already-approved email is still a clean transition.
  await db
    .prepare(
      `INSERT OR IGNORE INTO approved_users (email, approved_at, approved_by, note)
       VALUES (?, ?, ?, 'via signup request')`,
    )
    .bind(row.email, ts, admin)
    .run();
  await db
    .prepare(
      `UPDATE pending_signups
       SET status = 'approved', reviewed_at = ?, reviewed_by = ?
       WHERE id = ?`,
    )
    .bind(ts, admin, id)
    .run();
  return { kind: "ok" };
}

export async function denyPending(
  db: D1Database,
  id: number,
  adminEmail: string,
  now: Date = new Date(),
): Promise<ReviewOutcome> {
  const row = await db
    .prepare("SELECT status FROM pending_signups WHERE id = ?")
    .bind(id)
    .first<{ status: SignupStatus }>();
  if (!row) return { kind: "not-found" };
  if (row.status !== "pending") {
    return { kind: "not-pending", current_status: row.status };
  }
  await db
    .prepare(
      `UPDATE pending_signups
       SET status = 'denied', reviewed_at = ?, reviewed_by = ?
       WHERE id = ?`,
    )
    .bind(now.toISOString(), canonicalEmail(adminEmail), id)
    .run();
  return { kind: "ok" };
}

export async function revokeApproval(
  db: D1Database,
  email: string,
): Promise<{ kind: "ok" | "not-found" }> {
  const canonical = canonicalEmail(email);
  const existing = await db
    .prepare("SELECT 1 AS present FROM approved_users WHERE email = ?")
    .bind(canonical)
    .first<{ present: number }>();
  if (existing?.present !== 1) return { kind: "not-found" };

  await db
    .prepare("DELETE FROM approved_users WHERE email = ?")
    .bind(canonical)
    .run();
  return { kind: "ok" };
}

export async function listApproved(
  db: D1Database,
  limit = 200,
): Promise<
  Array<{ email: string; approved_at: string; approved_by: string; note: string | null }>
> {
  const res = await db
    .prepare(
      `SELECT email, approved_at, approved_by, note
       FROM approved_users
       ORDER BY approved_at DESC
       LIMIT ?`,
    )
    .bind(limit)
    .all<{
      email: string;
      approved_at: string;
      approved_by: string;
      note: string | null;
    }>();
  return res.results ?? [];
}
