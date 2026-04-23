// MIL-63 — OAuth state parameter
//
// The state param survives two hops (client → AuthKit → client
// callback) and MUST carry enough info to return the user to the
// originally-requested URL after login, AND be tamper-resistant so
// an attacker cannot forge a callback that phones home to an
// arbitrary return_to.
//
// Approach: HMAC-signed JSON payload.
//   payload = { r: returnTo, t: unix-timestamp-ms }
//   state   = base64url(payload) + "." + base64url(hmac-sha256(payload))
//
// A shared secret (STATE_SIGNING_KEY) signs both sides. Any change
// to payload invalidates the signature. A max-age bound (default
// 10 min) prevents replay of stale states.

export type StatePayload = {
  returnTo: string;
  ts: number;
};

const MAX_STATE_AGE_MS = 10 * 60 * 1000;

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

export async function signState(
  payload: StatePayload,
  secret: string,
): Promise<string> {
  const bodyBytes = new TextEncoder().encode(JSON.stringify(payload));
  const key = await hmacKey(secret);
  const sigBuf = await crypto.subtle.sign("HMAC", key, bodyBytes);
  return `${b64urlEncode(bodyBytes)}.${b64urlEncode(new Uint8Array(sigBuf))}`;
}

export type StateVerifyResult =
  | { ok: true; payload: StatePayload }
  | { ok: false; reason: "malformed" | "bad-signature" | "expired" };

export async function verifyState(
  state: string,
  secret: string,
  now: number = Date.now(),
  maxAgeMs: number = MAX_STATE_AGE_MS,
): Promise<StateVerifyResult> {
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

  let payload: StatePayload;
  try {
    payload = JSON.parse(new TextDecoder().decode(bodyBytes));
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (
    typeof payload.returnTo !== "string" ||
    typeof payload.ts !== "number"
  ) {
    return { ok: false, reason: "malformed" };
  }
  if (now - payload.ts > maxAgeMs) return { ok: false, reason: "expired" };
  return { ok: true, payload };
}

// return_to validation — prevents open-redirect abuse of the login
// flow ("malicious.example.com" as a return target).
//
// Rules:
//   - Must be a path (starts with "/"), not an absolute URL
//   - Must not start with "//" (protocol-relative URL)
//   - Must not contain ".." (path traversal paranoia — not a real
//     security bound, just a defensive signal that the input is
//     being massaged)
//
// If invalid, callers should fall back to DEFAULT_RETURN_TO.
export function isValidReturnTo(returnTo: string): boolean {
  if (typeof returnTo !== "string" || returnTo.length === 0) return false;
  if (!returnTo.startsWith("/")) return false;
  if (returnTo.startsWith("//")) return false;
  if (returnTo.includes("..")) return false;
  return true;
}
