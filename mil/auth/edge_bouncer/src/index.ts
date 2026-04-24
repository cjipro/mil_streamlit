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
import { logAuthEvent } from "../../audit/src/audit";
import type { AuthEventInput, AuthEventType } from "../../audit/src/types";

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
  // MIL-65 — audit log binding. Optional: the Worker runs without it
  // (degraded to console.log only) so a missing D1 doesn't take the
  // auth path down. Populate via wrangler.toml [[d1_databases]].
  AUDIT_DB?: D1Database;
}

type Decision =
  | { action: "pass"; reason: "public" | "valid-session"; sub?: string }
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
    const sub = typeof result.payload.sub === "string" ? result.payload.sub : undefined;
    return { action: "pass", reason: "valid-session", sub };
  }
  if (result.kind === "missing") {
    return { action: "redirect", reason: "missing" };
  }
  return { action: "redirect", reason: "invalid", detail: result.reason };
}

function auditEventType(decision: Decision): AuthEventType {
  if (decision.action === "pass" && decision.reason === "public") {
    return "bouncer.pass.public";
  }
  if (decision.action === "pass" && decision.reason === "valid-session") {
    return "bouncer.pass.session";
  }
  if (decision.action === "redirect" && decision.reason === "missing") {
    return "bouncer.redirect.missing";
  }
  return "bouncer.redirect.invalid";
}

function buildAuditInput(
  request: Request,
  decision: Decision,
  enforce: boolean,
): AuthEventInput {
  const url = new URL(request.url);
  const cf = (request as Request & { cf?: IncomingRequestCfProperties }).cf;
  return {
    worker: "edge-bouncer",
    event_type: auditEventType(decision),
    method: request.method,
    host: url.host,
    path: url.pathname,
    enforce,
    session_sub: decision.action === "pass" ? decision.sub : undefined,
    ip: request.headers.get("cf-connecting-ip") ?? undefined,
    user_agent: request.headers.get("user-agent") ?? undefined,
    country: cf?.country ?? undefined,
    reason: decision.reason,
    detail: decision.action === "redirect" ? decision.detail : undefined,
  };
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
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<Response> {
    const enforce = env.ENFORCE === "true";
    const decision = await decide(request, env);
    logDecision(request, decision, enforce);

    // MIL-65 — fire the audit write into the waitUntil pool so it
    // never gates the user response. A D1 failure is swallowed by
    // the .catch here and logged; auth still flows.
    if (env.AUDIT_DB) {
      const db = env.AUDIT_DB;
      ctx.waitUntil(
        logAuthEvent(db, buildAuditInput(request, decision, enforce)).catch(
          (err) => {
            console.log(
              JSON.stringify({
                ts: new Date().toISOString(),
                audit_error: err instanceof Error ? err.message : String(err),
              }),
            );
          },
        ),
      );
    }

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
