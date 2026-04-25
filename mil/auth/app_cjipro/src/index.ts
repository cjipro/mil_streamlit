// MIL-84 — app.cjipro.com Worker entrypoint.
//
// Mirrors the edge-bouncer's auth-gate logic but serves content
// directly instead of passing through to a GitHub Pages origin.
// All four CJI products (Reckoner, Sonar, Pulse workspace, Lever)
// live under app.cjipro.com — this Worker is their shared shell.
//
// Decision flow (per request):
//   1. Public allowlist match → render directly (no auth needed).
//      MVP allowlist: /healthz, /favicon.ico, /.nojekyll, /robots.txt.
//   2. Extract __Secure-cjipro-session cookie. Verify against WorkOS
//      JWKS using the shared session.ts from edge_bouncer/.
//   3. On valid JWT, lookup sub→email in the sessions table, check
//      email against approved_users (MIL-66 gate).
//   4. Approved → render the requested surface via router.ts.
//      Not approved → 403 access-pending page (no loop to login).
//      Missing/invalid JWT → 302 to login.cjipro.com with return_to.
//
// ENFORCE=false (shadow mode, default): decisions logged via the
// audit lib but the Worker always renders. Gives us real traffic
// shape before flipping enforce — same playbook as MIL-61.

import {
  extractCookie,
  verifySession,
  type SessionCheck,
  type SessionConfig,
} from "../../edge_bouncer/src/session";
import { isPublic, parsePatterns, type Matcher } from "../../edge_bouncer/src/whitelist";
import { logAuthEvent } from "../../audit/src/audit";
import type { AuthEventInput, AuthEventType } from "../../audit/src/types";
import { isApproved } from "../../approvals/src/approvals";
import { lookupSessionEmail, recordActivity } from "../../approvals/src/sessions";
import { dispatch } from "./router";

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
  AUDIT_DB?: D1Database;
}

type Decision =
  | { action: "render"; reason: "public" | "valid-session"; sub?: string }
  | { action: "redirect"; reason: "missing" | "invalid"; detail?: string }
  | { action: "deny"; reason: "not-approved"; sub?: string; email?: string };

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

function buildDenyResponse(): Response {
  // Same shape as edge-bouncer's deny page — consistent UX so a user
  // who hits either gate sees the same "access pending" affordance.
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Access pending · CJI</title>
<style>
  :root { --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7; }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font:16px/1.55 ui-serif,Georgia,serif; }
  main { max-width:32rem; margin:6rem auto; padding:2rem; }
  h1 { font-weight:600; font-size:1.4rem; margin:0 0 0.75rem; }
  p { margin:0.5rem 0; color:var(--muted); }
  a { color:#003A5C; }
</style>
</head>
<body>
<main>
<h1>Access pending</h1>
<p>You're signed in, but this account isn't on the alpha access list yet.</p>
<p>Request access at
<a href="https://login.cjipro.com/request-access">login.cjipro.com/request-access</a>,
or email <a href="mailto:hello@cjipro.com">hello@cjipro.com</a>.</p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: 403,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function decide(request: Request, env: Env): Promise<Decision> {
  const url = new URL(request.url);
  if (isPublic(url.pathname, publicMatchers(env))) {
    return { action: "render", reason: "public" };
  }
  const cookie = extractCookie(
    request.headers.get("cookie"),
    env.SESSION_COOKIE_NAME,
  );
  const result: SessionCheck = await verifySession(cookie, sessionConfig(env));
  if (result.kind === "missing") {
    return { action: "redirect", reason: "missing" };
  }
  if (result.kind === "invalid") {
    return { action: "redirect", reason: "invalid", detail: result.reason };
  }

  const sub = typeof result.payload.sub === "string" ? result.payload.sub : undefined;
  // No D1 binding or no sub → fail closed (matches edge-bouncer).
  if (!env.AUDIT_DB || !sub) {
    return { action: "deny", reason: "not-approved", sub };
  }
  const email = await lookupSessionEmail(env.AUDIT_DB, sub);
  const approved = await isApproved(env.AUDIT_DB, email);
  if (!approved) {
    return { action: "deny", reason: "not-approved", sub, email };
  }
  return { action: "render", reason: "valid-session", sub };
}

function auditEventType(decision: Decision): AuthEventType {
  // We share the bouncer.* event-type prefix because the gate
  // semantics are identical; the `worker` column distinguishes
  // app-cjipro decisions from edge-bouncer decisions in audit reads.
  if (decision.action === "render" && decision.reason === "public") {
    return "bouncer.pass.public";
  }
  if (decision.action === "render" && decision.reason === "valid-session") {
    return "bouncer.pass.session";
  }
  if (decision.action === "redirect" && decision.reason === "missing") {
    return "bouncer.redirect.missing";
  }
  if (decision.action === "deny" && decision.reason === "not-approved") {
    return "bouncer.deny.not_approved";
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
    worker: "app-cjipro",
    event_type: auditEventType(decision),
    method: request.method,
    host: url.host,
    path: url.pathname,
    enforce,
    session_sub:
      decision.action === "render" || decision.action === "deny"
        ? decision.sub
        : undefined,
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
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      worker: "app-cjipro",
      enforce,
      method: request.method,
      host: url.host,
      path: url.pathname,
      action: decision.action,
      reason: decision.reason,
      detail: "detail" in decision ? decision.detail : undefined,
    }),
  );
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

    // Audit + last-active write — fire into waitUntil so they don't
    // gate the user response. Identical pattern to edge-bouncer.
    if (env.AUDIT_DB) {
      const db = env.AUDIT_DB;
      ctx.waitUntil(
        logAuthEvent(db, buildAuditInput(request, decision, enforce)).catch(
          (err) => {
            console.log(
              JSON.stringify({
                ts: new Date().toISOString(),
                worker: "app-cjipro",
                audit_error: err instanceof Error ? err.message : String(err),
              }),
            );
          },
        ),
      );
      if (
        decision.action === "render" &&
        decision.reason === "valid-session" &&
        decision.sub
      ) {
        const sub = decision.sub;
        ctx.waitUntil(
          recordActivity(db, sub).catch((err) => {
            console.log(
              JSON.stringify({
                ts: new Date().toISOString(),
                worker: "app-cjipro",
                activity_write_error:
                  err instanceof Error ? err.message : String(err),
              }),
            );
          }),
        );
      }
    }

    // Enforce: if the gate said redirect/deny and ENFORCE=true,
    // return that response now (no content render).
    if (decision.action === "redirect" && enforce) {
      return buildRedirect(request, env);
    }
    if (decision.action === "deny" && enforce) {
      return buildDenyResponse();
    }

    // ENFORCE=false (shadow) OR decision was "render" → dispatch to
    // router. Note that in shadow mode we render even for users who
    // would have been denied, so we get real traffic shape on the
    // surfaces themselves before flipping enforce.
    const handlerResponse = dispatch(request);
    return handlerResponse ?? new Response("internal error", { status: 500 });
  },
};
