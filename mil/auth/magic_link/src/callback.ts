// MIL-63 — callback orchestrator
//
// This module is pure logic — no Worker entrypoint here. Chunk 2
// wires this into a `fetch` handler.
//
// Input:  Request (the user's browser GET /callback?code=...&state=...)
// Output: Response — either a 302 with Set-Cookie + Location, or
//         an error response (4xx/5xx) that the caller renders.

import { buildSessionCookie, type CookieConfig } from "./cookie";
import { exchangeCode, type ExchangeConfig } from "./exchange";
import { looksForwarded, type ForwardDetectResult } from "./forward_detect";
import { isValidReturnTo, verifyState } from "./state";

export type CallbackConfig = {
  exchange: ExchangeConfig;
  cookie: CookieConfig;
  stateSigningKey: string;
  defaultReturnTo: string;
};

// MIL-146 — current request context for forwarded-use detection. Both
// optional. When omitted (older callers / tests that don't care), the
// detector silently no-ops.
export interface CallbackContext {
  ip?: string;
  userAgent?: string;
}

export type CallbackOutcome =
  | {
      kind: "redirect";
      location: string;
      setCookie: string;
      // MIL-65 — exposed so the Worker can audit-log the user's
      // sub claim. The token itself is never persisted; callers
      // extract `sub` and discard.
      accessToken: string;
      // MIL-66c — sub + email surfaced so the Worker can write a
      // sessions row mapping sub→email. Access tokens have sub but
      // no email; this is the only place we have both.
      userId?: string;
      userEmail?: string;
      // MIL-72 — organization_id for per-tenant audit scoping.
      organizationId?: string;
      // MIL-146 — non-null when the heuristic fires. Caller should
      // emit a magic_link.forwarded_use_detected audit event but MUST
      // NOT block the redirect: forwarding is supported.
      forward?: {
        ip_changed: boolean;
        ua_changed: boolean;
        time_delta_seconds: number;
      };
    }
  | { kind: "error"; status: number; reason: string; detail?: string };

export async function handleCallback(
  requestUrl: string,
  cfg: CallbackConfig,
  fetchImpl: typeof fetch = fetch,
  now: number = Date.now(),
  ctxArg: CallbackContext = {},
): Promise<CallbackOutcome> {
  const url = new URL(requestUrl);

  // The auth provider may redirect back with ?error=... on auth
  // failure (user cancelled, rate limit, etc). Surface that before
  // anything else. Reason code is "auth-error" (cjipro-namespaced) —
  // the internal provider name never reaches user-visible HTML.
  const providerError = url.searchParams.get("error");
  if (providerError) {
    return {
      kind: "error",
      status: 400,
      reason: "auth-error",
      detail: `${providerError}: ${url.searchParams.get("error_description") ?? ""}`,
    };
  }

  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code || !state) {
    return {
      kind: "error",
      status: 400,
      reason: "missing-params",
      detail: `code=${!!code} state=${!!state}`,
    };
  }

  // Verify state — integrity + freshness + return_to sanity.
  const verified = await verifyState(state, cfg.stateSigningKey, now);
  if (!verified.ok) {
    return { kind: "error", status: 400, reason: verified.reason };
  }
  const returnTo = isValidReturnTo(verified.payload.returnTo)
    ? verified.payload.returnTo
    : cfg.defaultReturnTo;

  // Exchange the code for a WorkOS-signed access_token JWT.
  const exchange = await exchangeCode(code, cfg.exchange, fetchImpl);
  if (!exchange.ok) {
    return {
      kind: "error",
      status: 502,
      reason: exchange.reason,
      detail: exchange.detail,
    };
  }

  const setCookie = buildSessionCookie(exchange.accessToken, cfg.cookie);

  // MIL-146 — forwarded-use detection. Compares IP /24 + UA family of
  // /authorize (carried inside state) against /callback (passed in).
  // Non-blocking: heuristic only informs the audit event, never stops
  // the cookie + redirect flow.
  const detect: ForwardDetectResult = looksForwarded(
    verified.payload.ip,
    verified.payload.ua,
    ctxArg.ip,
    ctxArg.userAgent,
  );
  const forward = detect.forwarded
    ? {
        ip_changed: detect.ip_changed,
        ua_changed: detect.ua_changed,
        time_delta_seconds: Math.max(
          0,
          Math.floor((now - verified.payload.ts) / 1000),
        ),
      }
    : undefined;

  return {
    kind: "redirect",
    location: returnTo,
    setCookie,
    accessToken: exchange.accessToken,
    userId: exchange.userId,
    userEmail: exchange.userEmail,
    organizationId: exchange.organizationId,
    forward,
  };
}
