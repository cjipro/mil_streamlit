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
import { isValidReturnTo, verifyState } from "./state";

export type CallbackConfig = {
  exchange: ExchangeConfig;
  cookie: CookieConfig;
  stateSigningKey: string;
  defaultReturnTo: string;
};

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
    }
  | { kind: "error"; status: number; reason: string; detail?: string };

export async function handleCallback(
  requestUrl: string,
  cfg: CallbackConfig,
  fetchImpl: typeof fetch = fetch,
  now: number = Date.now(),
): Promise<CallbackOutcome> {
  const url = new URL(requestUrl);

  // WorkOS may redirect back with ?error=... on auth failure (user
  // cancelled, rate limit, etc). Surface that before anything else.
  const wosError = url.searchParams.get("error");
  if (wosError) {
    return {
      kind: "error",
      status: 400,
      reason: "workos-error",
      detail: `${wosError}: ${url.searchParams.get("error_description") ?? ""}`,
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
  return {
    kind: "redirect",
    location: returnTo,
    setCookie,
    accessToken: exchange.accessToken,
    userId: exchange.userId,
    userEmail: exchange.userEmail,
  };
}
