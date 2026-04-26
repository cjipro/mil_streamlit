// MIL-152 — partner_profiles helpers over D1.
//
// Pure application logic — no Worker imports. Reusable from any env
// with a D1Database binding (magic-link /callback, app-cjipro /portal,
// admin endpoints, future tooling).
//
// Threat model: firm_slug is the routing key for /sonar/{slug}/.
// Self-set would let a user spoof firm context, so the only writer
// for firm_slug + firm_name is setFirm() (admin-only at the call site).
// confirmDetails() never touches firm fields.

import { canonicalEmail } from "./approvals";

export interface PartnerProfile {
  sub: string;
  display_name: string | null;
  role: string | null;
  firm_slug: string | null;
  firm_name: string | null;
  contact_email: string | null;
  contact_pref: string;
  last_confirmed_at: string | null;
  last_confirmed_hash: string | null;
  created_at: string;
  updated_at: string;
}

// Fields the user may self-affirm via POST /portal/confirm. Anything
// outside this set is admin-only. Kept as a const so the test suite
// can pin it; if you add a field, update both sides.
export type AffirmableField = "display_name" | "role" | "contact_email" | "contact_pref";

export const AFFIRMABLE_FIELDS: readonly AffirmableField[] = [
  "display_name",
  "role",
  "contact_email",
  "contact_pref",
] as const;

export const REAFFIRMATION_DAYS = 90;

export async function getProfile(
  db: D1Database,
  sub: string | undefined | null,
): Promise<PartnerProfile | null> {
  if (!sub) return null;
  const row = await db
    .prepare("SELECT * FROM partner_profiles WHERE sub = ? LIMIT 1")
    .bind(sub)
    .first<PartnerProfile>();
  return row ?? null;
}

// Idempotent first-touch write at /callback time. If a row already
// exists for this sub, this is a no-op — never overwrites self-affirmed
// or admin-set fields. INSERT OR IGNORE keeps us safe across races.
export async function ensureProfile(
  db: D1Database,
  sub: string,
  email: string,
  now: Date = new Date(),
): Promise<void> {
  const ts = now.toISOString();
  await db
    .prepare(
      `INSERT OR IGNORE INTO partner_profiles
        (sub, contact_email, created_at, updated_at)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(sub, canonicalEmail(email), ts, ts)
    .run();
}

// Admin-only — sets the firm pair atomically. Used by alpha onboarding.
// Idempotent: re-setting the same values still bumps updated_at but is
// otherwise a no-op. Doesn't pre-create the partner_profiles row — the
// admin should set firm only AFTER the user has signed in at least once
// (which guarantees ensureProfile() has run); if the row is missing,
// this errors at the SQL UPDATE — caught by the caller.
export async function setFirm(
  db: D1Database,
  sub: string,
  firmSlug: string,
  firmName: string,
  now: Date = new Date(),
): Promise<{ kind: "ok" } | { kind: "not-found" }> {
  // Validate slug shape — same regex as the sonar router uses to route.
  if (!/^[a-z0-9-]+$/.test(firmSlug)) {
    throw new Error(`invalid firm_slug: ${firmSlug}`);
  }
  const result = await db
    .prepare(
      `UPDATE partner_profiles
       SET firm_slug = ?, firm_name = ?, updated_at = ?
       WHERE sub = ?`,
    )
    .bind(firmSlug, firmName, now.toISOString(), sub)
    .run();
  const meta = (result as { meta?: { changes?: number } }).meta;
  if ((meta?.changes ?? 0) === 0) return { kind: "not-found" };
  return { kind: "ok" };
}

// User self-affirmation. Returns the changed-field list so the caller
// (POST /portal/confirm) can name them in the audit row's detail. The
// hash is over the canonicalised payload, NOT including null fields,
// so a "confirm with same values" still bumps last_confirmed_at but
// produces an identical hash — admin dashboard distinguishes refresh
// from substantive change.
export interface ConfirmInput {
  display_name?: string | null;
  role?: string | null;
  contact_email?: string | null;
  contact_pref?: string | null;
}

export interface ConfirmOutcome {
  prev_hash: string | null;
  new_hash: string;
  fields_changed: AffirmableField[];
}

export async function confirmDetails(
  db: D1Database,
  sub: string,
  input: ConfirmInput,
  now: Date = new Date(),
): Promise<ConfirmOutcome | { kind: "not-found" }> {
  const existing = await getProfile(db, sub);
  if (!existing) return { kind: "not-found" };

  // Reject any input that names a non-affirmable key — caller must
  // route admin updates through setFirm().
  for (const k of Object.keys(input)) {
    if (!AFFIRMABLE_FIELDS.includes(k as AffirmableField)) {
      throw new Error(`field "${k}" is not user-affirmable`);
    }
  }

  // Build the post-update payload. Any key not in input keeps its
  // existing value. Any key in input with `undefined` is also untouched
  // (lets caller pass partial PATCH-like payloads); only an explicit
  // null clears a field.
  const next = {
    display_name: pick(input.display_name, existing.display_name),
    role: pick(input.role, existing.role),
    contact_email: input.contact_email !== undefined
      ? (input.contact_email ? canonicalEmail(input.contact_email) : null)
      : existing.contact_email,
    contact_pref: pick(input.contact_pref, existing.contact_pref),
  };

  const newHash = await canonicalHash(next);
  const ts = now.toISOString();

  const fieldsChanged = AFFIRMABLE_FIELDS.filter(
    (f) => normalise(next[f]) !== normalise((existing as Record<string, unknown>)[f]),
  );

  // Capture prev_hash + ensure detached from the row reference BEFORE
  // the UPDATE — D1 may return rows by-reference (the FakeD1 does), so
  // reading existing.last_confirmed_hash after the .run() would alias
  // to the freshly-written hash.
  const prevHash = existing.last_confirmed_hash;

  await db
    .prepare(
      `UPDATE partner_profiles
       SET display_name = ?, role = ?, contact_email = ?, contact_pref = ?,
           last_confirmed_at = ?, last_confirmed_hash = ?, updated_at = ?
       WHERE sub = ?`,
    )
    .bind(
      next.display_name,
      next.role,
      next.contact_email,
      next.contact_pref,
      ts,
      newHash,
      ts,
      sub,
    )
    .run();

  return {
    prev_hash: prevHash,
    new_hash: newHash,
    fields_changed: fieldsChanged,
  };
}

function pick<T>(
  inputVal: T | null | undefined,
  existingVal: T | null,
): T | null {
  if (inputVal === undefined) return existingVal;
  return inputVal;
}

function normalise(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v.trim().toLowerCase();
  return String(v);
}

// Canonicalisation rule: sort keys, normalise (trim+lowercase) string
// values, JSON.stringify, sha256-hex. Re-confirming with whitespace-
// or case-different values still produces the same hash — that's
// intentional: "Hussain Ahmed " and "hussain ahmed" are the same
// affirmed identity.
export async function canonicalHash(payload: ConfirmInput): Promise<string> {
  const keys = AFFIRMABLE_FIELDS.slice().sort();
  const canonical: Record<string, string | null> = {};
  for (const k of keys) {
    const v = (payload as Record<string, unknown>)[k];
    canonical[k] = v === null || v === undefined
      ? null
      : (typeof v === "string" ? v.trim().toLowerCase() : String(v));
  }
  const json = JSON.stringify(canonical);
  const buf = new TextEncoder().encode(json);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function needsReaffirmation(
  profile: PartnerProfile | null,
  now: Date = new Date(),
): boolean {
  if (!profile) return true;
  if (!profile.last_confirmed_at) return true;
  const last = Date.parse(profile.last_confirmed_at);
  if (Number.isNaN(last)) return true;
  const ageMs = now.getTime() - last;
  return ageMs > REAFFIRMATION_DAYS * 24 * 60 * 60 * 1000;
}
