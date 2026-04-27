// MIL-161 — sign-out lifecycle (real, not just cookie clear).
//
// The pre-MIL-161 /logout path cleared the __Secure-cjipro-session
// cookie + audited and returned. That left three real session-lifecycle
// surfaces alive:
//   1. The `sessions` D1 row (sub→email mapping). Bouncer gate kept
//      passing on cached JWTs until natural expiry.
//   2. The WorkOS AuthKit SSO session at the AuthKit domain. Next
//      sign-in attempt silently re-authed without a passcode prompt.
//   3. The WorkOS access token at WorkOS itself. Short-lived (~10min)
//      but valid until exp.
// Plus a CSRF gap: GET /logout could be triggered by `<img src=...>`
// embedded on any open-web page.
//
// This module owns the action half (extract sid, delete D1 row, revoke
// WorkOS session, build outcome record). The render half lives in
// logout_pages.ts. The wiring (GET → confirm page, POST → this) is in
// index.ts.

import { extractJwtSub } from "../../audit/src/audit";
import { deleteSessionBySub } from "../../approvals/src/sessions";

export interface LogoutOutcome {
  // Did we successfully delete the sessions row? "skipped" when the
  // cookie was missing or unparseable (no sub to key on). "not-found"
  // means the row was already gone — counts as success for the user.
  sessions_row_deleted: "deleted" | "not-found" | "skipped" | "error";
  sessions_row_error: string | null;
  // Did WorkOS confirm the session is revoked? "skipped" when no `sid`
  // claim was present in the JWT (old token shape) or AUDIT_DB-only
  // installs without WORKOS_CLIENT_SECRET. "error" carries the http
  // status or thrown error message in `workos_revoke_error`.
  workos_session_revoked: "revoked" | "skipped" | "error";
  workos_revoke_error: string | null;
  // Stable for the audit event detail JSON. The cookie clear is always
  // returned to the user regardless of the above — none of these
  // failures block the response.
  cookie_cleared: true;
}

// WorkOS access tokens carry both `sub` (user) and `sid` (session).
// We need `sid` to revoke the WorkOS session — `sub` alone identifies
// the user but not which login session. Extract without verifying
// signature; we trust the cookie was set by us.
export function extractJwtSid(jwt: string): string | undefined {
  const parts = jwt.split(".");
  if (parts.length !== 3) return undefined;
  try {
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const json = atob(padded);
    const claims = JSON.parse(json) as { sid?: unknown };
    return typeof claims.sid === "string" ? claims.sid : undefined;
  } catch {
    return undefined;
  }
}

// CSRF protection for POST /logout.
//
// The cookie itself is HttpOnly + SameSite=Lax. SameSite=Lax allows
// top-level form submissions to carry the cookie, so a same-site POST
// from a confirm page works. To stop a cross-origin form-POST from
// bouncing through the user's browser, the confirm page embeds a
// short-lived HMAC-signed token tied to the cookie value. POST
// handler recomputes and compares constant-time.
//
// The token is bound to the JWT bytes — if the cookie rotates between
// GET and POST (e.g. via /callback in another tab), the POST token
// won't validate. That's acceptable: the user can re-click sign-out.

const CSRF_VERSION = "v1";

export async function buildCsrfToken(
  jwt: string,
  signingKey: string,
): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(signingKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    enc.encode(`${CSRF_VERSION}|${jwt}`),
  );
  return CSRF_VERSION + "." + base64UrlEncode(new Uint8Array(sig));
}

export async function verifyCsrfToken(
  token: string | null | undefined,
  jwt: string,
  signingKey: string,
): Promise<boolean> {
  if (!token) return false;
  const dot = token.indexOf(".");
  if (dot < 0) return false;
  const ver = token.slice(0, dot);
  if (ver !== CSRF_VERSION) return false;
  const expected = await buildCsrfToken(jwt, signingKey);
  return constantTimeEqual(token, expected);
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

function base64UrlEncode(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

// AuthKit front-channel logout URL.
//
// The server-to-server `revokeWorkosSession` call invalidates the
// session record at WorkOS, but it does NOT clear the AuthKit-domain
// cookie sitting in the user's browser. When the user clicks "Sign in
// again", AuthKit reads that cookie, validates against WorkOS, and
// silent-auths them straight back in (the very footgun MIL-161 was
// filed to fix).
//
// The cure is to send the browser through AuthKit's own logout URL.
// AuthKit clears its session cookies on its domain, then 302s back to
// the application's configured Homepage URL.
//
// Endpoint shape (verified 2026-04-27 via chrome-devtools probe against
// ideal-log-65-staging.authkit.app):
//   • Path is `/api/logout`. The earlier-shipped path
//     `/user_management/sessions/logout` returns 404 — it is a WorkOS
//     API path, not an AuthKit path, and was a guess.
//   • Query: `session_id=<sid>` (so AuthKit knows which session to
//     terminate). If `sid` is missing, AuthKit clears whatever session
//     cookie it finds for this browser.
//   • AuthKit IGNORES `return_to`, `post_logout_redirect_uri`, and
//     similar OIDC-style params. Passing `redirect_uri` is actively
//     dangerous — AuthKit treats it as a sign-in flow start, not a
//     post-logout target.
//   • Post-logout landing is governed by the WorkOS application's
//     Homepage URL — set it in WorkOS Dashboard → Application →
//     Configuration → Branded URLs to `https://login.cjipro.com/logout/done`.
//     If unset, the user lands on
//     `error.workos.com/user_management/app-homepage-url-not-found`
//     after the cookie clear (cookie clear still happens, only UX is
//     broken).
//
// `returnTo` is retained in the signature so callers can pass our
// done-page URL for documentation / future-fallback purposes, but it
// is not appended to the URL.
//
// Defensive: if `authKitHost` is unset we return null and the caller
// should fall back to rendering the done page directly.
export function buildAuthkitLogoutUrl(
  authKitHost: string | undefined,
  sid: string | undefined,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _returnTo: string,
): string | null {
  if (!authKitHost) return null;
  // authKitHost in env is the bare domain (`ideal-log-65-staging.authkit.app`);
  // build https URL without trusting any prefix.
  const host = authKitHost.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const params = new URLSearchParams();
  if (sid) params.set("session_id", sid);
  const qs = params.toString();
  return `https://${host}/api/logout${qs ? "?" + qs : ""}`;
}

// WorkOS session revocation.
// API: POST https://api.workos.com/user_management/sessions/{sid}/revoke
// Auth: Bearer <WORKOS_CLIENT_SECRET> (the same sk_*** value used for
//       the OAuth code exchange — WorkOS uses one credential for both
//       per CLAUDE.md note).
// Failure mode: log the error in the outcome but never block the
// response. The D1 row deletion is the load-bearing security control;
// the WorkOS revoke is belt-and-braces.
export async function revokeWorkosSession(
  sid: string,
  apiKey: string,
  fetcher: typeof fetch = fetch,
): Promise<{ kind: "ok" } | { kind: "error"; detail: string }> {
  const url = `https://api.workos.com/user_management/sessions/${encodeURIComponent(sid)}/revoke`;
  let res: Response;
  try {
    res = await fetcher(url, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${apiKey}`,
        "content-type": "application/json",
      },
    });
  } catch (err) {
    return {
      kind: "error",
      detail: `network: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
  // 200 OK or 204 No Content both indicate success. 404 is also
  // success-shaped — the session is already gone, which is what we
  // want. Anything else is a real error worth recording.
  if (res.ok || res.status === 404) return { kind: "ok" };
  let body = "";
  try {
    body = (await res.text()).slice(0, 200);
  } catch {
    /* ignore */
  }
  return { kind: "error", detail: `http_${res.status}: ${body}` };
}

export interface PerformLogoutDeps {
  db: D1Database | undefined;
  workosApiKey: string | undefined;
  fetcher?: typeof fetch;
}

// Orchestrator. Given a JWT (or undefined if no cookie), perform the
// three lifecycle steps in order — each best-effort, none blocking —
// and return a structured outcome the caller can audit + render.
export async function performLogout(
  jwt: string | undefined | null,
  deps: PerformLogoutDeps,
): Promise<LogoutOutcome> {
  const outcome: LogoutOutcome = {
    sessions_row_deleted: "skipped",
    sessions_row_error: null,
    workos_session_revoked: "skipped",
    workos_revoke_error: null,
    cookie_cleared: true,
  };
  if (!jwt) return outcome; // no session to revoke; cookie clear is enough.

  const sub = extractJwtSub(jwt);
  if (sub && deps.db) {
    try {
      const result = await deleteSessionBySub(deps.db, sub);
      outcome.sessions_row_deleted =
        result.kind === "ok" ? "deleted" : "not-found";
    } catch (err) {
      outcome.sessions_row_deleted = "error";
      outcome.sessions_row_error =
        err instanceof Error ? err.message : String(err);
    }
  }

  const sid = extractJwtSid(jwt);
  if (sid && deps.workosApiKey) {
    const revoke = await revokeWorkosSession(
      sid,
      deps.workosApiKey,
      deps.fetcher,
    );
    if (revoke.kind === "ok") {
      outcome.workos_session_revoked = "revoked";
    } else {
      outcome.workos_session_revoked = "error";
      outcome.workos_revoke_error = revoke.detail;
    }
  }

  return outcome;
}

// Compact JSON for the audit `detail` column. Audit row hash is taken
// over this string verbatim (HASHED_COLUMNS includes detail), so the
// shape is stable — any future field additions go at the end.
export function outcomeToAuditDetail(outcome: LogoutOutcome): string {
  return JSON.stringify({
    s: outcome.sessions_row_deleted,
    s_err: outcome.sessions_row_error,
    w: outcome.workos_session_revoked,
    w_err: outcome.workos_revoke_error,
    c: outcome.cookie_cleared,
  });
}
