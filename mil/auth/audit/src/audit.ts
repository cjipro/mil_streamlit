// MIL-65 — logAuthEvent is the ONE entry point callers should use.
//
// Pattern:
//   ctx.waitUntil(logAuthEvent(env.AUDIT_DB, input));
//
// Always call via waitUntil from a Worker so the audit write never
// delays the user response. The function is idempotent on write
// (auto-increment id) but NOT on retry — a second call with the same
// input produces a second row. That's intentional; we want a full
// arrival record, not a deduplicated one.

import { hashRow, sha256Hex } from "./hash";
import { d1SaltStore, utcDateString, type SaltStore } from "./salt";
import { HASHED_COLUMNS, type AuthEventInput } from "./types";

export interface LogOptions {
  // Injectable for tests.
  saltStore?: SaltStore;
  now?: Date;
}

export async function logAuthEvent(
  db: D1Database,
  input: AuthEventInput,
  opts: LogOptions = {},
): Promise<void> {
  const now = opts.now ?? new Date();
  const salts = opts.saltStore ?? d1SaltStore(db);
  const salt = await salts.getOrCreate(utcDateString(now));

  const user_hash = input.session_sub
    ? await sha256Hex(input.session_sub + salt)
    : null;
  const ip_hash = input.ip ? await sha256Hex(input.ip + salt) : null;
  const ua_hash = input.user_agent ? await sha256Hex(input.user_agent) : null;

  const content: Record<string, unknown> = {
    ts: now.toISOString(),
    worker: input.worker,
    event_type: input.event_type,
    method: input.method ?? null,
    host: input.host ?? null,
    path: input.path ?? null,
    enforce: typeof input.enforce === "boolean" ? (input.enforce ? 1 : 0) : null,
    user_hash,
    ip_hash,
    ua_hash,
    country: input.country ?? null,
    reason: input.reason ?? null,
    detail: input.detail ?? null,
  };

  // Read the tail of the chain. Two concurrent writers can observe the
  // same prev_hash and both insert with it; the verifier detects that
  // (second row's prev_hash won't match the first row's row_hash) and
  // flags it as a chain fork, which is true and worth surfacing rather
  // than hiding behind a lock. In practice auth volume is low enough
  // that collisions will be rare.
  const prev = await db
    .prepare("SELECT row_hash FROM auth_events ORDER BY id DESC LIMIT 1")
    .first<{ row_hash: string }>();
  const prev_hash = prev?.row_hash ?? "genesis";

  const row_hash = await hashRow(content, prev_hash);

  const cols = [...HASHED_COLUMNS, "prev_hash", "row_hash"];
  const placeholders = cols.map(() => "?").join(", ");
  const values = HASHED_COLUMNS.map((c) => content[c] ?? null);
  values.push(prev_hash, row_hash);

  await db
    .prepare(
      `INSERT INTO auth_events (${cols.join(", ")}) VALUES (${placeholders})`,
    )
    .bind(...values)
    .run();
}

// Helper for the magic-link Worker: given an access_token JWT string,
// extract `sub` without verifying the signature. We only use it as a
// stable user identifier for hashing — verification is the bouncer's
// job, not the audit log's.
export function extractJwtSub(jwt: string): string | undefined {
  const parts = jwt.split(".");
  if (parts.length !== 3) return undefined;
  try {
    // base64url → base64
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const json = atob(padded);
    const claims = JSON.parse(json) as { sub?: unknown };
    return typeof claims.sub === "string" ? claims.sub : undefined;
  } catch {
    return undefined;
  }
}
