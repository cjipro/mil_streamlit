// MIL-63 — magic-link Worker entrypoint
//
// Routes:
//   GET /           → build signed state, 302 to AuthKit /oauth2/authorize
//   GET /callback   → verify state, exchange code, set cookie, 302 to return_to
//   GET /logout     → clear cookie, 302 to /
//   GET /healthz    → 200 "ok" (for deployment smoke tests)
//   GET /favicon.ico → 204 (browser probe, don't treat as auth trigger)
//   (fallback)      → 404
//
// This Worker does NOT serve the MIL-59 placeholder HTML. When
// login.cjipro.com routes flip to this Worker (chunk 3), the
// placeholder goes away — the hostname becomes a pure auth
// endpoint. cjipro.com (apex) retains the public landing page.

import { buildAuthorizeUrl } from "./authorize";
import { buildClearCookie, type CookieConfig } from "./cookie";
import { handleCallback, type CallbackConfig } from "./callback";
import type { Env } from "./env";
import { isValidReturnTo, signState } from "./state";
import { extractJwtSub, logAuthEvent } from "../../audit/src/audit";
import type { AuthEventInput } from "../../audit/src/types";
import { checkAdmin, type AdminGateConfig } from "./admin_gate";
import {
  handleRequestAccessPost,
  renderRequestForm,
} from "./request_access";
import {
  handleApiApprove,
  handleApiDeny,
  handleApiForceSignout,
  handleApiPortalLink,
  handleApiRevoke,
  handleApiSignups,
  renderDashboard,
  renderDenied,
} from "./admin_routes";
import { d1SaltStore, utcDateString } from "../../audit/src/salt";
import { writeSession } from "../../approvals/src/sessions";
import { verifyWorkosWebhook, webhookAuditInput } from "./webhooks";

function cookieConfigFromEnv(env: Env): CookieConfig {
  return {
    name: env.COOKIE_NAME,
    domain: env.COOKIE_DOMAIN,
    maxAgeSeconds: parseInt(env.COOKIE_MAX_AGE_SECONDS, 10) || 3600,
  };
}

function callbackConfigFromEnv(env: Env): CallbackConfig {
  return {
    exchange: {
      clientId: env.CLIENT_ID,
      clientSecret: env.WORKOS_CLIENT_SECRET,
    },
    cookie: cookieConfigFromEnv(env),
    stateSigningKey: env.STATE_SIGNING_KEY,
    defaultReturnTo: env.DEFAULT_RETURN_TO,
  };
}

async function handleAuthorize(
  url: URL,
  env: Env,
  now: number,
): Promise<Response> {
  const raw = url.searchParams.get(env.RETURN_TO_PARAM) ?? "";
  const returnTo = isValidReturnTo(raw) ? raw : env.DEFAULT_RETURN_TO;

  const state = await signState(
    { returnTo, ts: now },
    env.STATE_SIGNING_KEY,
  );

  const authorizeUrl = buildAuthorizeUrl(
    {
      clientId: env.CLIENT_ID,
      redirectUri: env.REDIRECT_URI,
    },
    state,
  );

  return Response.redirect(authorizeUrl, 302);
}

function handleLogout(env: Env): Response {
  const setCookie = buildClearCookie(cookieConfigFromEnv(env));
  return new Response(null, {
    status: 302,
    headers: {
      location: env.DEFAULT_RETURN_TO,
      "set-cookie": setCookie,
    },
  });
}

function renderErrorPage(status: number, reason: string): Response {
  // Minimal, information-light error page. Reason is surfaced
  // (it's already a short enum like "expired" / "bad-signature" /
  // "workos-error") but detail is intentionally suppressed.
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign-in error · CJI Pro</title>
<style>
  :root { --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7; }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font:16px/1.55 ui-serif,Georgia,serif; }
  main { max-width:32rem; margin:6rem auto; padding:2rem; }
  h1 { font-weight:600; font-size:1.4rem; margin:0 0 0.75rem; }
  p { margin:0.5rem 0; color:var(--muted); }
  code { font-family:ui-monospace,Menlo,monospace; font-size:0.85em;
    background:#fff; padding:0.1em 0.35em; border-radius:3px; }
  a { color:#003A5C; }
</style>
</head>
<body>
<main>
<h1>Sign-in error</h1>
<p>We couldn't complete your sign-in. Reason: <code>${reason}</code>.</p>
<p>Your invitation link may have expired. <a href="/">Start over</a>
or contact <a href="mailto:hello@cjipro.com">hello@cjipro.com</a>.</p>
</main>
</body>
</html>`;
  return new Response(html, {
    status,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function baseAuditInput(
  request: Request,
  path: string,
): Pick<AuditInputShape, "worker" | "method" | "host" | "path" | "ip" | "user_agent" | "country"> {
  const url = new URL(request.url);
  const cf = (request as Request & { cf?: IncomingRequestCfProperties }).cf;
  return {
    worker: "magic-link",
    method: request.method,
    host: url.host,
    path,
    ip: request.headers.get("cf-connecting-ip") ?? undefined,
    user_agent: request.headers.get("user-agent") ?? undefined,
    country: cf?.country ?? undefined,
  };
}

type AuditInputShape = AuthEventInput;

function audit(
  env: Env,
  ctx: ExecutionContext,
  input: AuthEventInput,
): void {
  if (!env.AUDIT_DB) return;
  const db = env.AUDIT_DB;
  ctx.waitUntil(
    logAuthEvent(db, input).catch((err) => {
      console.log(
        JSON.stringify({
          ts: new Date().toISOString(),
          audit_error: err instanceof Error ? err.message : String(err),
        }),
      );
    }),
  );
}

function adminGateConfigFromEnv(env: Env): AdminGateConfig | null {
  if (!env.JWKS_URL || !env.EXPECTED_AUD || !env.EXPECTED_ISS) return null;
  return {
    jwksUrl: env.JWKS_URL,
    expectedIss: env.EXPECTED_ISS,
    expectedAud: env.EXPECTED_AUD,
    jwksCacheTtlSeconds:
      parseInt(env.JWKS_CACHE_TTL_SECONDS ?? "3600", 10) || 3600,
    cookieName: env.COOKIE_NAME,
  };
}

async function currentSalt(env: Env, now: Date): Promise<string | null> {
  if (!env.AUDIT_DB) return null;
  try {
    return await d1SaltStore(env.AUDIT_DB).getOrCreate(utcDateString(now));
  } catch {
    return null;
  }
}

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // MIL-66b/67a — routes that accept POST: /request-access,
    // /admin/api/*, /webhooks/workos. Others are GET-only.
    const isPostPath =
      path === "/request-access" ||
      path === "/webhooks/workos" ||
      path.startsWith("/admin/api/");
    if (method !== "GET" && !(isPostPath && method === "POST")) {
      return new Response("method not allowed", {
        status: 405,
        headers: { allow: isPostPath ? "GET, POST" : "GET" },
      });
    }

    // --- MIL-67a: WorkOS webhook ingestion ---
    if (path === "/webhooks/workos" && method === "POST") {
      const rawBody = await request.text();
      const sig = request.headers.get("workos-signature");
      const result = await verifyWorkosWebhook(rawBody, sig, {
        secret: env.WORKOS_WEBHOOK_SECRET ?? "",
      });
      if (result.kind === "rejected") {
        // Log the rejection so we can see attack attempts vs. genuine
        // misconfiguration in the tail. Don't audit-log — these are
        // unauthenticated requests; recording them in the chain would
        // pollute the auth event timeline.
        console.log(
          JSON.stringify({
            ts: new Date().toISOString(),
            webhook_rejected: result.reason,
            status: result.status,
          }),
        );
        return new Response(result.reason, {
          status: result.status,
          headers: { "content-type": "text/plain" },
        });
      }
      audit(
        env,
        ctx,
        webhookAuditInput(result.event, baseAuditInput(request, path)),
      );
      // 200 = "we accepted the event". Don't echo the body — WorkOS
      // expects a small ack; their retry policy backs off on 2xx.
      return new Response(`ok ${result.rawId}`, {
        status: 200,
        headers: { "content-type": "text/plain" },
      });
    }

    // --- MIL-66b: self-service signup + admin dashboard ---
    if (path === "/request-access") {
      if (method === "GET") return renderRequestForm();
      // POST
      const salt = await currentSalt(env, new Date());
      const res = await handleRequestAccessPost(request, env.AUDIT_DB, salt);
      // Audit after the write so we capture the actual outcome (via
      // status code — 200 ok, 400 invalid-email, 429 rate-limited).
      audit(env, ctx, {
        ...baseAuditInput(request, path),
        event_type: "signup.request",
        reason: `http_${res.status}`,
      });
      return res;
    }

    if (path === "/admin" || path.startsWith("/admin/api/")) {
      const cfg = adminGateConfigFromEnv(env);
      if (!cfg || !env.AUDIT_DB) {
        return renderDenied({ kind: "misconfigured" });
      }
      const check = await checkAdmin(request, env.AUDIT_DB, cfg);
      if (check.kind !== "ok") return renderDenied(check);
      const adminEmail = check.email;

      if (path === "/admin") return renderDashboard(adminEmail);
      if (path === "/admin/api/signups" && method === "GET") {
        return handleApiSignups(env.AUDIT_DB);
      }
      if (path === "/admin/api/approve" && method === "POST") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.approve",
          session_sub: adminEmail,
        });
        return handleApiApprove(request, env.AUDIT_DB, adminEmail);
      }
      if (path === "/admin/api/deny" && method === "POST") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.deny",
          session_sub: adminEmail,
        });
        return handleApiDeny(request, env.AUDIT_DB, adminEmail);
      }
      if (path === "/admin/api/revoke" && method === "POST") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.revoke",
          session_sub: adminEmail,
        });
        return handleApiRevoke(request, env.AUDIT_DB);
      }
      if (path === "/admin/api/force_signout" && method === "POST") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.force_signout",
          session_sub: adminEmail,
        });
        return handleApiForceSignout(request, env.AUDIT_DB);
      }
      if (path === "/admin/api/portal_link" && method === "POST") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.portal_link_generated",
          session_sub: adminEmail,
        });
        return handleApiPortalLink(request, env.WORKOS_CLIENT_SECRET);
      }
      return new Response("not found", {
        status: 404,
        headers: { "content-type": "text/plain" },
      });
    }

    if (path === "/healthz") {
      return new Response("ok", {
        status: 200,
        headers: { "content-type": "text/plain" },
      });
    }

    if (path === "/favicon.ico") {
      return new Response(null, { status: 204 });
    }

    if (path === "/callback") {
      const outcome = await handleCallback(
        request.url,
        callbackConfigFromEnv(env),
      );
      if (outcome.kind === "redirect") {
        const sub = outcome.userId ?? extractJwtSub(outcome.accessToken);
        // MIL-66c — record the sub→email mapping so the bouncer + admin
        // gate can resolve email at request time. Fire-and-forget; a D1
        // failure here doesn't block the user from being signed in (they
        // get the cookie anyway), it only means the gate would deny on
        // their next request — which is the correct fail-closed posture.
        if (env.AUDIT_DB && sub && outcome.userEmail) {
          const db = env.AUDIT_DB;
          ctx.waitUntil(
            writeSession(db, sub, outcome.userEmail).catch((err) => {
              console.log(
                JSON.stringify({
                  ts: new Date().toISOString(),
                  session_write_error:
                    err instanceof Error ? err.message : String(err),
                }),
              );
            }),
          );
        }
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "magic_link.callback.success",
          session_sub: sub,
        });
        return new Response(null, {
          status: 302,
          headers: {
            location: outcome.location,
            "set-cookie": outcome.setCookie,
          },
        });
      }
      console.log(
        JSON.stringify({
          ts: new Date().toISOString(),
          route: "/callback",
          error: outcome.reason,
          detail: outcome.detail,
        }),
      );
      audit(env, ctx, {
        ...baseAuditInput(request, path),
        event_type: "magic_link.callback.error",
        reason: outcome.reason,
        detail: outcome.detail,
      });
      return renderErrorPage(outcome.status, outcome.reason);
    }

    if (path === "/logout") {
      audit(env, ctx, {
        ...baseAuditInput(request, path),
        event_type: "magic_link.logout",
      });
      return handleLogout(env);
    }

    if (path === "/") {
      audit(env, ctx, {
        ...baseAuditInput(request, path),
        event_type: "magic_link.authorize",
      });
      return handleAuthorize(url, env, Date.now());
    }

    return new Response("not found", {
      status: 404,
      headers: { "content-type": "text/plain" },
    });
  },
};
