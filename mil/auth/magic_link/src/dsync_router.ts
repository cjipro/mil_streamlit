// MIL-71 — SCIM (Directory Sync) event router.
//
// Called from /webhooks/workos AFTER signature verification. Inspects
// the event.event string and routes dsync.* events to side effects:
//
//   dsync.user.created  → if user's organization is in auto_approve_orgs,
//                          add to approved_users + audit dsync.user.auto_approved.
//                          Otherwise audit-only as dsync.user.created.
//   dsync.user.updated  → audit-only (Phase B may track email changes).
//   dsync.user.deleted  → revoke from approved_users + force_signout +
//                          audit dsync.user.auto_revoked.
//   dsync.group.user_added/removed → audit-only.
//   anything else dsync.* → audit-only as dsync.user.<event_subtype>.
//
// Returns the AuthEventType to log so the caller can write the audit
// row. Returning an event type doesn't mean the side-effect ran — that
// happened inline. The returned type IS what gets written.

import { canonicalEmail } from "../../approvals/src/approvals";
import { isAutoApproveOrg } from "../../approvals/src/auto_approve";
import { forceSignout } from "../../approvals/src/sessions";
import { revokeApproval } from "../../approvals/src/signups";
import type { AuthEventType } from "../../audit/src/types";
import type { WorkosEvent } from "./webhooks";

export interface DsyncRoutingOutcome {
  // The event_type to write into the audit row for this delivery.
  // For dsync.* events this is the typed name; for non-dsync events
  // the caller falls back to "workos.webhook".
  eventType: AuthEventType | null;
  // Side-effect outcome — useful for the audit detail field.
  detail?: string;
  // Email extracted from the event payload (when present); the
  // caller can stamp it into the audit row's reason.
  email?: string;
}

export async function routeDsyncEvent(
  db: D1Database,
  event: WorkosEvent,
  now: Date = new Date(),
): Promise<DsyncRoutingOutcome | null> {
  if (!event.event.startsWith("dsync.")) return null;

  const data = event.data as Record<string, unknown>;
  const email = extractEmail(data);
  const orgId = extractOrgId(data);

  switch (event.event) {
    case "dsync.user.created": {
      if (!email) {
        return { eventType: "dsync.user.created", detail: "no-email-in-payload" };
      }
      if (orgId && (await isAutoApproveOrg(db, orgId))) {
        await db
          .prepare(
            `INSERT OR IGNORE INTO approved_users (email, approved_at, approved_by, note)
             VALUES (?, ?, 'scim', 'auto-approved via SCIM dsync')`,
          )
          .bind(canonicalEmail(email), now.toISOString())
          .run();
        return {
          eventType: "dsync.user.auto_approved",
          email,
          detail: orgId,
        };
      }
      return {
        eventType: "dsync.user.created",
        email,
        detail: orgId ? `pending:${orgId}` : "no-org-in-payload",
      };
    }

    case "dsync.user.updated": {
      // Phase B can track email changes here. For now, audit-only.
      return { eventType: "dsync.user.updated", email };
    }

    case "dsync.user.deleted": {
      if (!email) {
        return { eventType: "dsync.user.deleted", detail: "no-email-in-payload" };
      }
      // Revoke approval AND force-signout. Either may be a no-op if
      // the user wasn't on the allowlist or had no live session;
      // both are idempotent so re-runs are safe.
      const revoke = await revokeApproval(db, email);
      const signout = await forceSignout(db, email);
      const detail = `revoke:${revoke.kind} signout:${signout.kind}`;
      return {
        eventType: "dsync.user.auto_revoked",
        email,
        detail,
      };
    }

    case "dsync.group.user_added":
      return { eventType: "dsync.group.user_added", email };

    case "dsync.group.user_removed":
      return { eventType: "dsync.group.user_removed", email };

    default:
      // Unknown dsync.* event — fall back to the generic
      // workos.webhook bucket by returning null eventType but a
      // useful detail. The caller will then route via webhooks.ts.
      return null;
  }
}

// WorkOS payload shapes vary by event subtype. The user object
// typically lives at data.user or data itself, depending on event.
// We dig defensively — if neither shape matches, return undefined.
function extractEmail(data: Record<string, unknown>): string | undefined {
  const direct = data.email;
  if (typeof direct === "string") return direct;
  const user = data.user;
  if (user && typeof user === "object") {
    const userEmail = (user as Record<string, unknown>).email;
    if (typeof userEmail === "string") return userEmail;
    const emails = (user as Record<string, unknown>).emails;
    if (Array.isArray(emails) && emails.length > 0) {
      const first = emails[0] as Record<string, unknown>;
      if (typeof first.value === "string") return first.value;
    }
  }
  // SCIM standard schema sometimes uses primary_email
  const primary = data.primary_email;
  if (typeof primary === "string") return primary;
  return undefined;
}

function extractOrgId(data: Record<string, unknown>): string | undefined {
  if (typeof data.organization_id === "string") return data.organization_id;
  const dir = data.directory;
  if (dir && typeof dir === "object") {
    const dirOrg = (dir as Record<string, unknown>).organization_id;
    if (typeof dirOrg === "string") return dirOrg;
  }
  if (typeof data.organization === "string") return data.organization;
  return undefined;
}
