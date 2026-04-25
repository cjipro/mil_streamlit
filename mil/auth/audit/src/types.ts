// MIL-65 — shared event types for the auth audit log.
//
// Every auth event that flows through edge-bouncer or magic-link
// maps to exactly one AuthEventType. The string form is what lands
// in the D1 event_type column. Do not rename without a migration.

export type AuthEventType =
  // edge-bouncer decisions
  | "bouncer.pass.public"
  | "bouncer.pass.session"
  | "bouncer.redirect.missing"
  | "bouncer.redirect.invalid"
  | "bouncer.deny.not_approved"
  // magic-link flow
  | "magic_link.authorize"
  | "magic_link.callback.success"
  | "magic_link.callback.error"
  | "magic_link.logout"
  // MIL-66b — signup + admin
  | "signup.request"
  | "admin.approve"
  | "admin.deny"
  | "admin.revoke"
  // MIL-68 — boot active session for a user without removing approval
  | "admin.force_signout"
  // MIL-69 — Cloudflare WAF challenge/block reached the Worker
  // (only fires when Cloudflare passes through challenged traffic
  // post-solve; pre-challenge blocks never invoke the Worker)
  | "bouncer.rate_limited"
  // MIL-70 — SAML / SSO connection lifecycle (populated from WorkOS
  // webhook events once Phase B narrows workos.webhook). Reserved
  // typed slots so the runbook + dashboard can reference them today.
  | "connection.activated"
  | "connection.deactivated"
  | "connection.deleted"
  | "admin.portal_link_generated"
  // MIL-71 — SCIM (Directory Sync) lifecycle events. dsync.user.*
  // and dsync.group.* fire when the partner's IdP provisions or
  // deprovisions users. Routed in webhooks.ts: dsync.user.created
  // optionally auto-approves; dsync.user.deleted always revokes +
  // force-signs-out.
  | "dsync.user.created"
  | "dsync.user.updated"
  | "dsync.user.deleted"
  | "dsync.group.user_added"
  | "dsync.group.user_removed"
  | "dsync.user.auto_approved"
  | "dsync.user.auto_revoked"
  // MIL-72 — admin downloaded a per-tenant audit export
  | "admin.audit_export"
  // MIL-67a — WorkOS webhook ingestion. Generic catch-all for now;
  // Phase B will split out specific passkey events
  // (passkey.registered, passkey.used, etc.) once we observe what
  // event types WorkOS actually sends.
  | "workos.webhook";

// Input passed to logAuthEvent. The lib is responsible for turning
// the raw `ip` / `user_agent` / `session_sub` into salted hashes
// before insertion. Callers MUST NOT pre-hash these fields — passing
// a hex string would re-hash it and break user linkage across events.
export interface AuthEventInput {
  worker: "magic-link" | "edge-bouncer";
  event_type: AuthEventType;
  method?: string;
  host?: string;
  path?: string;
  enforce?: boolean;

  // Raw values — the lib hashes them with the daily salt.
  // None are required. Absent values become NULL in the row.
  session_sub?: string;
  ip?: string;
  user_agent?: string;

  country?: string;
  reason?: string;
  detail?: string;
}

// Row shape as stored in D1. Used by the verifier.
export interface AuthEventRow {
  id: number;
  ts: string;
  worker: string;
  event_type: string;
  method: string | null;
  host: string | null;
  path: string | null;
  enforce: number | null;
  user_hash: string | null;
  ip_hash: string | null;
  ua_hash: string | null;
  country: string | null;
  reason: string | null;
  detail: string | null;
  prev_hash: string;
  row_hash: string;
}

// The ordered list of columns that participate in the row hash.
// Keep in sync with hash.ts::hashRow — both read from this constant
// so there's one source of truth.
export const HASHED_COLUMNS = [
  "ts",
  "worker",
  "event_type",
  "method",
  "host",
  "path",
  "enforce",
  "user_hash",
  "ip_hash",
  "ua_hash",
  "country",
  "reason",
  "detail",
] as const;

export type HashedColumn = (typeof HASHED_COLUMNS)[number];
