// MIL-149 — direct WorkOS Magic Auth on login.cjipro.com
//
// Replaces the AuthKit-domain hop in the sign-in flow. Corp proxies
// that block *.authkit.app on URL-category filters (the failure mode
// MIL-149 was filed for) can no longer break sign-in for partner
// users — every byte the browser sees comes from login.cjipro.com.
//
// Flow:
//   GET  /sign-in/                  → email entry form
//   POST /sign-in/email             → POST api.workos.com/user_management/magic_auth/send
//                                   → renders code form with HMAC-signed state
//   POST /sign-in/code              → POST api.workos.com/user_management/authenticate
//                                     with grant_type=magic_auth_code
//                                   → set __Secure-cjipro-session cookie, 302 to return_to
//
// State tokens follow MIL-63's HMAC pattern (same STATE_SIGNING_KEY,
// same 10-min TTL). They live in a hidden form input across the
// email→code hop and carry { email, returnTo, ts }.
//
// Notes:
//  • The b64url + HMAC helpers mirror state.ts. Keeping them here
//    rather than refactoring state.ts isolates MIL-149 surface area.
//    Follow-up could extract a shared crypto_util.ts.
//  • WorkOS Magic Auth send endpoint takes an Authorization: Bearer
//    header with the API key; the authenticate endpoint takes
//    client_id+client_secret in the JSON body. Both shapes are
//    documented behaviour, not chosen by us.
//  • Email-existence is intentionally NOT leaked: the send endpoint
//    returns the same status whether or not the email is already
//    registered. We surface a generic "check your email" message
//    on success regardless.

import { isPlausibleEmail } from "../../approvals/src/signups";

const SEND_URL = "https://api.workos.com/user_management/magic_auth/send";
const AUTHENTICATE_URL =
  "https://api.workos.com/user_management/authenticate";

const MAX_STATE_AGE_MS = 10 * 60 * 1000;
// Verified against WorkOS Node SDK serializer 2026-04-28 — the
// canonical string uses hyphens ("magic-auth"), not underscores.
// Earlier draft used "magic_auth" and produced "code didn't match"
// for every valid code on staging.
const MAGIC_AUTH_GRANT_TYPE =
  "urn:workos:oauth:grant-type:magic-auth:code";

// ---- email validation (re-exported from approvals/signups for callers) ----

export { isPlausibleEmail };

// ---- state token (separate type from MIL-63's OAuth state) -----------------

export type SignInState = {
  kind: "signin";
  email: string;
  returnTo: string;
  ts: number;
};

export type SignInStateVerifyResult =
  | { ok: true; payload: SignInState }
  | { ok: false; reason: "malformed" | "bad-signature" | "expired" };

// ---- crypto helpers (b64url + HMAC) ---------------------------------------

function b64urlEncode(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function b64urlDecode(s: string): Uint8Array {
  const padded = s.replaceAll("-", "+").replaceAll("_", "/");
  const pad = padded.length % 4;
  const full = pad ? padded + "=".repeat(4 - pad) : padded;
  const bin = atob(full);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function constantTimeEq(a: Uint8Array, b: Uint8Array): boolean {
  if (a.byteLength !== b.byteLength) return false;
  let diff = 0;
  for (let i = 0; i < a.byteLength; i++) diff |= a[i]! ^ b[i]!;
  return diff === 0;
}

export async function signSignInState(
  payload: SignInState,
  secret: string,
): Promise<string> {
  const bodyBytes = new TextEncoder().encode(JSON.stringify(payload));
  const key = await hmacKey(secret);
  const sigBuf = await crypto.subtle.sign("HMAC", key, bodyBytes);
  return `${b64urlEncode(bodyBytes)}.${b64urlEncode(new Uint8Array(sigBuf))}`;
}

export async function verifySignInState(
  state: string,
  secret: string,
  now: number = Date.now(),
  maxAgeMs: number = MAX_STATE_AGE_MS,
): Promise<SignInStateVerifyResult> {
  const dot = state.indexOf(".");
  if (dot < 0) return { ok: false, reason: "malformed" };
  const bodyEnc = state.slice(0, dot);
  const sigEnc = state.slice(dot + 1);
  let bodyBytes: Uint8Array;
  let sigBytes: Uint8Array;
  try {
    bodyBytes = b64urlDecode(bodyEnc);
    sigBytes = b64urlDecode(sigEnc);
  } catch {
    return { ok: false, reason: "malformed" };
  }

  const key = await hmacKey(secret);
  const expectedBuf = await crypto.subtle.sign("HMAC", key, bodyBytes);
  if (!constantTimeEq(sigBytes, new Uint8Array(expectedBuf))) {
    return { ok: false, reason: "bad-signature" };
  }

  let payload: SignInState;
  try {
    payload = JSON.parse(new TextDecoder().decode(bodyBytes));
  } catch {
    return { ok: false, reason: "malformed" };
  }

  // Type guards. A tampered or stale-format payload should fail closed.
  if (
    payload.kind !== "signin" ||
    typeof payload.email !== "string" ||
    typeof payload.returnTo !== "string" ||
    typeof payload.ts !== "number"
  ) {
    return { ok: false, reason: "malformed" };
  }
  if (now - payload.ts > maxAgeMs) return { ok: false, reason: "expired" };
  return { ok: true, payload };
}

// ---- WorkOS API: send Magic Auth code ------------------------------------

export type SendCodeResult =
  | { ok: true }
  | {
      ok: false;
      status: number;
      reason: "http-error" | "network-error" | "invalid-email";
      detail?: string;
    };

export async function sendMagicAuthCode(
  email: string,
  apiKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SendCodeResult> {
  if (!isPlausibleEmail(email)) {
    return { ok: false, status: 400, reason: "invalid-email" };
  }
  let res: Response;
  try {
    res = await fetchImpl(SEND_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ email }),
    });
  } catch (e) {
    return {
      ok: false,
      status: 0,
      reason: "network-error",
      detail: e instanceof Error ? e.message : String(e),
    };
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = text.slice(0, 200);
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      if (typeof parsed.error_description === "string") {
        detail = parsed.error_description;
      } else if (typeof parsed.error === "string") {
        detail = parsed.error;
      }
    } catch {
      // leave detail as raw text slice
    }
    return { ok: false, status: res.status, reason: "http-error", detail };
  }
  // Body shape is { id: "magic_auth_..." } but we don't need the id —
  // verifying the code only requires email + code + client credentials.
  // Drain the body so the connection can be reused.
  await res.text().catch(() => "");
  return { ok: true };
}

// ---- WorkOS API: verify Magic Auth code ----------------------------------

export type VerifyCodeSuccess = {
  ok: true;
  accessToken: string;
  refreshToken?: string;
  userId?: string;
  userEmail?: string;
  organizationId?: string;
  rawBody: Record<string, unknown>;
};

export type VerifyCodeFailure = {
  ok: false;
  status: number;
  reason:
    | "http-error"
    | "network-error"
    | "invalid-code"
    | "missing-access-token";
  detail?: string;
};

export type VerifyCodeResult = VerifyCodeSuccess | VerifyCodeFailure;

export async function verifyMagicAuthCode(
  email: string,
  code: string,
  cfg: { clientId: string; clientSecret: string },
  fetchImpl: typeof fetch = fetch,
): Promise<VerifyCodeResult> {
  let res: Response;
  try {
    res = await fetchImpl(AUTHENTICATE_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        grant_type: MAGIC_AUTH_GRANT_TYPE,
        code,
        email,
        client_id: cfg.clientId,
        client_secret: cfg.clientSecret,
      }),
    });
  } catch (e) {
    return {
      ok: false,
      status: 0,
      reason: "network-error",
      detail: e instanceof Error ? e.message : String(e),
    };
  }

  const rawText = await res.text();
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawText) as Record<string, unknown>;
  } catch {
    return {
      ok: false,
      status: res.status,
      reason: "http-error",
      detail: `non-JSON body: ${rawText.slice(0, 120)}`,
    };
  }

  if (!res.ok) {
    // Distinguish "user typed the wrong/expired code" from real
    // server errors so the form can show "code didn't match" rather
    // than a generic failure. WorkOS surfaces these via the `code`
    // field on 4xx responses.
    const errorCode = typeof body.code === "string" ? body.code : "";
    const detail =
      typeof body.error_description === "string"
        ? body.error_description
        : typeof body.error === "string"
          ? body.error
          : rawText.slice(0, 200);
    if (
      res.status === 401 ||
      res.status === 422 ||
      errorCode === "invalid_credentials" ||
      errorCode === "authentication_failed" ||
      errorCode === "invalid_authentication_code"
    ) {
      return {
        ok: false,
        status: res.status,
        reason: "invalid-code",
        detail,
      };
    }
    return { ok: false, status: res.status, reason: "http-error", detail };
  }

  const accessToken = body.access_token;
  if (typeof accessToken !== "string" || accessToken.length === 0) {
    return {
      ok: false,
      status: res.status,
      reason: "missing-access-token",
    };
  }

  const refreshToken =
    typeof body.refresh_token === "string" ? body.refresh_token : undefined;
  const userId =
    body.user && typeof body.user === "object" && "id" in body.user
      ? String((body.user as { id: unknown }).id)
      : undefined;
  const userEmail =
    body.user &&
    typeof body.user === "object" &&
    "email" in body.user &&
    typeof (body.user as { email: unknown }).email === "string"
      ? (body.user as { email: string }).email
      : undefined;
  let organizationId: string | undefined;
  if (typeof body.organization_id === "string") {
    organizationId = body.organization_id;
  } else if (
    body.user &&
    typeof body.user === "object" &&
    typeof (body.user as { organization_id?: unknown }).organization_id ===
      "string"
  ) {
    organizationId = (body.user as { organization_id: string }).organization_id;
  }

  return {
    ok: true,
    accessToken,
    refreshToken,
    userId,
    userEmail,
    organizationId,
    rawBody: body,
  };
}
