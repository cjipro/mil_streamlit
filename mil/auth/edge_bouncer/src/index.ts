// MIL-61 — Edge Bouncer entrypoint
//
// Three responsibilities, in order:
//   1. Public allowlist — landing, privacy, security.txt, robots,
//      sitemap, .nojekyll → always pass through.
//   2. Session check — extract + verify __Secure-cjipro-session
//      JWT against WorkOS JWKS.
//   3. On miss — 302 to login.cjipro.com with return_to.
//
// ENFORCE=false: decide, log, always pass through. Default until
// MIL-63 ships the magic-link flow that actually sets the cookie.
//
// The Worker does NOT itself serve any content — it either passes
// the request to origin via `fetch(request)` or returns a 302.

import { isPublic, parsePatterns, type Matcher } from "./whitelist";
import {
  extractCookie,
  verifySession,
  type SessionCheck,
  type SessionConfig,
} from "./session";

export interface Env {
  ENFORCE: string;
  SESSION_COOKIE_NAME: string;
  JWKS_URL: string;
  EXPECTED_AUD: string;
  EXPECTED_ISS: string;
  LOGIN_URL: string;
  RETURN_TO_PARAM: string;
  JWKS_CACHE_TTL_SECONDS: string;
  PUBLIC_PATHS: string;
}

type Decision =
  | { action: "pass"; reason: "public" | "valid-session" }
  | { action: "redirect"; reason: "missing" | "invalid"; detail?: string };

// Pattern list is parsed per-request rather than cached in module
// scope because wrangler vars can hot-reload.
function publicMatchers(env: Env): Matcher[] {
  return parsePatterns(env.PUBLIC_PATHS);
}

function sessionConfig(env: Env): SessionConfig {
  return {
    jwksUrl: env.JWKS_URL,
    expectedIss: env.EXPECTED_ISS,
    expectedAud: env.EXPECTED_AUD,
    jwksCacheTtlSeconds: parseInt(env.JWKS_CACHE_TTL_SECONDS, 10) || 3600,
  };
}

function buildRedirect(request: Request, env: Env): Response {
  const url = new URL(request.url);
  const returnTo = url.pathname + url.search;
  const login = new URL(env.LOGIN_URL);
  login.searchParams.set(env.RETURN_TO_PARAM, returnTo);
  return Response.redirect(login.toString(), 302);
}

async function decide(request: Request, env: Env): Promise<Decision> {
  const url = new URL(request.url);
  if (isPublic(url.pathname, publicMatchers(env))) {
    return { action: "pass", reason: "public" };
  }
  const cookie = extractCookie(
    request.headers.get("cookie"),
    env.SESSION_COOKIE_NAME,
  );
  const result: SessionCheck = await verifySession(cookie, sessionConfig(env));
  if (result.kind === "valid") {
    return { action: "pass", reason: "valid-session" };
  }
  if (result.kind === "missing") {
    return { action: "redirect", reason: "missing" };
  }
  return { action: "redirect", reason: "invalid", detail: result.reason };
}

function logDecision(
  request: Request,
  decision: Decision,
  enforce: boolean,
): void {
  const url = new URL(request.url);
  const entry = {
    ts: new Date().toISOString(),
    enforce,
    method: request.method,
    host: url.host,
    path: url.pathname,
    action: decision.action,
    reason: decision.reason,
    detail: "detail" in decision ? decision.detail : undefined,
  };
  // Cloudflare Workers logs are picked up by observability=enabled
  // in wrangler.toml and surfaced via `wrangler tail` / Logpush.
  console.log(JSON.stringify(entry));
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const enforce = env.ENFORCE === "true";
    const decision = await decide(request, env);
    logDecision(request, decision, enforce);

    if (decision.action === "redirect" && enforce) {
      return buildRedirect(request, env);
    }
    // Pass through to origin for all other cases:
    //   - public allowlist match
    //   - valid session
    //   - enforce=false (shadow / monitor mode)
    return fetch(request);
  },
};
