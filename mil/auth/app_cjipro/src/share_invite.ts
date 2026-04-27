// MIL-145 — POST /api/share-invite handler.
//
// Flow: an authenticated partner clicks "Send invite to admin queue" on
// the share-affordance form on a Sonar briefing. We create a pending_signups
// row tagged with the invite source (firm_slug from the briefing context +
// inviter email in the note) and 303 back to the briefing with
// ?invite_sent=<recipient>. The router-side renderInviteSentBanner picks
// that param up on the next GET and shows a confirmation strip above the
// briefing.
//
// Standard form-POST flow — no inline JS on the briefing page, CSP-clean.
//
// Auth: caller of this module is the dispatch layer in index.ts which
// only routes here when the request is on app.cjipro.com AND has a valid
// session AND is approved. The handler trusts the inviter info from
// dispatch and never reads it from the form body — defense against
// inviter-spoofing.

import { sha256Hex } from "../../audit/src/hash";
import {
  isPlausibleEmail,
  submitRequest,
  type SubmitOutcome,
} from "../../approvals/src/signups";
import {
  checkAndIncrement,
  DEFAULT_RATE_LIMIT,
} from "../../approvals/src/rate_limit";
import { SUBJECTS } from "./subjects.generated";

export interface ShareInviteEnv {
  AUDIT_DB: D1Database;
}

export interface ShareInviteIdentity {
  sub: string;
  email: string;
}

export interface ShareInviteResult {
  response: Response;
  outcomeKind: SubmitOutcome["kind"] | "rate-limited" | "missing-fields";
  recipientEmail: string | null;
  sourceFirmSlug: string | null;
}

const SLUG_RE = /^[a-z0-9-]+$/;

function buildBackToBriefing(
  sourceFirmSlug: string | null,
  recipientEmail: string,
): string {
  // MIL-145 — recipient lands on the SAME firm's briefing they originally
  // shared from. If sourceFirmSlug is unrecognised (tampered or removed
  // from clients.yaml), fall back to /portal — never blindly redirect to
  // an attacker-controlled URL.
  if (
    sourceFirmSlug &&
    SLUG_RE.test(sourceFirmSlug) &&
    SUBJECTS.some((s) => s.slug === sourceFirmSlug)
  ) {
    return `/sonar/${sourceFirmSlug}/?invite_sent=${encodeURIComponent(recipientEmail)}`;
  }
  return "/portal";
}

function htmlError(status: number, message: string): Response {
  return new Response(message, {
    status,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export async function handleShareInvite(
  request: Request,
  env: ShareInviteEnv,
  identity: ShareInviteIdentity,
  dailySalt: string | null,
): Promise<ShareInviteResult> {
  const formData = await request.formData();
  const recipientEmailRaw = (formData.get("recipient_email") ?? "").toString().trim();
  const sourceFirmSlugRaw = (formData.get("source_firm_slug") ?? "").toString().trim();

  // Source firm slug — sanitise via shape regex AND membership in SUBJECTS
  // so a tampered value never reaches the redirect target or the audit
  // detail. Never trusted as authorisation; the inviter's session is
  // what gates their access to this endpoint in dispatch.
  const sourceFirmSlug =
    SLUG_RE.test(sourceFirmSlugRaw) &&
    SUBJECTS.some((s) => s.slug === sourceFirmSlugRaw)
      ? sourceFirmSlugRaw
      : null;

  if (!recipientEmailRaw) {
    return {
      response: htmlError(400, "Missing recipient email."),
      outcomeKind: "missing-fields",
      recipientEmail: null,
      sourceFirmSlug,
    };
  }

  // Per-IP rate-limit before the D1 insert. Same DEFAULT_RATE_LIMIT that
  // gates /request-access — sharing volume should match access-request
  // volume (low). An over-rate inviter gets a 429.
  const ip = request.headers.get("cf-connecting-ip");
  const ipHash = ip && dailySalt ? await sha256Hex(ip + dailySalt) : undefined;
  const ua = request.headers.get("user-agent");
  const uaHash = ua ? await sha256Hex(ua) : undefined;

  const allowed = await checkAndIncrement(
    env.AUDIT_DB,
    ipHash,
    new Date(),
    DEFAULT_RATE_LIMIT,
  );
  if (!allowed) {
    return {
      response: htmlError(
        429,
        "You've sent a few invites recently. Wait an hour and try again.",
      ),
      outcomeKind: "rate-limited",
      recipientEmail: recipientEmailRaw,
      sourceFirmSlug,
    };
  }

  // Pre-validate the email shape. submitRequest does the same check but
  // we want a clean redirect path (302) rather than a 400 when the user
  // typo'd — the briefing page will render with a "we received it"
  // banner regardless of outcome (consistent UX, no enumeration leak).
  if (!isPlausibleEmail(recipientEmailRaw)) {
    return {
      response: htmlError(400, "That doesn't look like a valid email."),
      outcomeKind: "invalid-email",
      recipientEmail: recipientEmailRaw,
      sourceFirmSlug,
    };
  }

  // Note carries inviter context so the admin reviewing the queue can
  // see WHO invited WHOM into WHICH firm's workspace — the firm context
  // is the key signal MIL-145 was filed for.
  const firmLabel =
    SUBJECTS.find((s) => s.slug === sourceFirmSlug)?.display ?? sourceFirmSlug ?? "(unspecified)";
  const note = `Invited by ${identity.email} to ${firmLabel} workspace via Sonar briefing share.`;

  const outcome = await submitRequest(
    env.AUDIT_DB,
    {
      email: recipientEmailRaw,
      note,
      ipHash,
      uaHash,
    },
  );

  // Always redirect with the same banner regardless of outcome —
  // already-pending and already-approved are both "we received your
  // invite" from the inviter's perspective. No enumeration leak.
  const location = buildBackToBriefing(sourceFirmSlug, recipientEmailRaw);
  return {
    response: new Response(null, {
      status: 303,
      headers: {
        location,
        "cache-control": "no-store",
      },
    }),
    outcomeKind: outcome.kind,
    recipientEmail: recipientEmailRaw,
    sourceFirmSlug,
  };
}
