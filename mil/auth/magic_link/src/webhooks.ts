// MIL-67a — WorkOS webhook signature verification.
//
// WorkOS signs every webhook delivery with HMAC-SHA256. The header
// `WorkOS-Signature` looks like `t=<unix_ms>,v1=<hex_hmac>` where the
// HMAC is computed over `<unix_ms>.<raw_request_body>` keyed by the
// secret you set when creating the endpoint in the WorkOS dashboard
// (NOT the same value as WORKOS_API_KEY). NB the `t` value is unix
// milliseconds, not seconds — Stripe-style intuition will fail here.
//
// The replay window check rejects deliveries older than 5 minutes
// (per WorkOS guidance) — protects against an attacker who recorded
// a real signed request and tries to replay it later.

import type { AuthEventInput } from "../../audit/src/types";

export type WebhookCheck =
  | { kind: "ok"; event: WorkosEvent; rawType: string; rawId: string }
  | { kind: "rejected"; reason: string; status: number };

export interface WorkosEvent {
  id: string;
  event: string; // event type name e.g. "user.created"
  data: Record<string, unknown>;
  created_at?: string;
}

const REPLAY_WINDOW_MS = 5 * 60 * 1000; // 5 minutes

export interface VerifyConfig {
  secret: string;
  // Injection points for tests.
  now?: () => number; // unix-milliseconds — WorkOS sends `t=` in ms
  decoder?: TextDecoder;
}

export async function verifyWorkosWebhook(
  rawBody: string,
  signatureHeader: string | null,
  cfg: VerifyConfig,
): Promise<WebhookCheck> {
  if (!cfg.secret) {
    return { kind: "rejected", reason: "missing-secret", status: 503 };
  }
  if (!signatureHeader) {
    return { kind: "rejected", reason: "missing-signature-header", status: 401 };
  }

  const parts = parseSignatureHeader(signatureHeader);
  if (!parts) {
    return { kind: "rejected", reason: "malformed-signature-header", status: 401 };
  }
  const { t, v1 } = parts;

  const ts = parseInt(t, 10);
  if (!Number.isFinite(ts)) {
    return { kind: "rejected", reason: "non-numeric-timestamp", status: 401 };
  }
  const nowMs = (cfg.now ?? (() => Date.now()))();
  const skew = Math.abs(nowMs - ts);
  if (skew > REPLAY_WINDOW_MS) {
    return {
      kind: "rejected",
      reason: `replay-window-exceeded:${skew}ms`,
      status: 401,
    };
  }

  // HMAC payload uses the *raw* `t` string from the header, not the
  // parsed integer — avoids drift if WorkOS ever ships fractional or
  // padded timestamps. For pure integers the two are identical.
  const expected = await computeHmacHex(cfg.secret, `${t}.${rawBody}`);
  if (!constantTimeEqual(expected, v1.toLowerCase())) {
    return { kind: "rejected", reason: "signature-mismatch", status: 401 };
  }

  // Signature good. Try to parse the body as the WorkOS event shape.
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    return { kind: "rejected", reason: "non-json-body", status: 400 };
  }
  if (!isWorkosEvent(parsed)) {
    return { kind: "rejected", reason: "missing-event-fields", status: 400 };
  }

  return {
    kind: "ok",
    event: parsed,
    rawType: parsed.event,
    rawId: parsed.id,
  };
}

function parseSignatureHeader(
  header: string,
): { t: string; v1: string } | null {
  let t: string | undefined;
  let v1: string | undefined;
  for (const seg of header.split(",")) {
    const trimmed = seg.trim();
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq);
    const val = trimmed.slice(eq + 1);
    if (key === "t") t = val;
    else if (key === "v1") v1 = val;
  }
  if (!t || !v1) return null;
  return { t, v1 };
}

async function computeHmacHex(secret: string, payload: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return bufToHex(sig);
}

function bufToHex(buf: ArrayBuffer): string {
  const view = new Uint8Array(buf);
  let out = "";
  for (let i = 0; i < view.length; i++) {
    out += view[i].toString(16).padStart(2, "0");
  }
  return out;
}

// Length-then-byte-by-byte equal. Avoids early exit on first mismatch.
function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

function isWorkosEvent(v: unknown): v is WorkosEvent {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.event === "string" &&
    typeof o.data === "object" &&
    o.data !== null
  );
}

// Builder for the audit event we record. Kept here next to the parser
// so any future event-type-specific routing has one place to grow.
export function webhookAuditInput(
  event: WorkosEvent,
  base: Pick<
    AuthEventInput,
    "method" | "host" | "path" | "ip" | "user_agent" | "country"
  >,
): AuthEventInput {
  return {
    ...base,
    worker: "magic-link",
    event_type: "workos.webhook",
    reason: event.event,
    detail: event.id,
  };
}
