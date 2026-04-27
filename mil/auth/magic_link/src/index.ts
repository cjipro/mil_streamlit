// MIL-63 — magic-link Worker entrypoint
//
// Routes:
//   GET /           → build signed state, 302 to AuthKit /oauth2/authorize
//   GET /callback   → verify state, exchange code, set cookie, 302 to return_to
//   GET /logout     → confirm page (CSRF-tokened form POSTs back to /logout)
//   POST /logout    → MIL-161 lifecycle: delete sessions row, revoke
//                     WorkOS session, clear cookie, render done page
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
import {
  buildAuthkitLogoutUrl,
  buildCsrfToken,
  extractJwtSid,
  outcomeToAuditDetail,
  performLogout,
  verifyCsrfToken,
} from "./logout";
import {
  renderLogoutConfirm,
  renderLogoutCsrfFailed,
  renderLogoutDone,
} from "./logout_pages";
import { extractCookie } from "../../edge_bouncer/src/session";
import {
  FONTS_BLOCK,
  FONT_STACK_SANS,
  FONT_STACK_SERIF,
} from "../../fonts_block/src/fonts_block.generated";
import { extractJwtSub, logAuthEvent } from "../../audit/src/audit";
import type { AuthEventInput } from "../../audit/src/types";
import { checkAdmin, type AdminGateConfig } from "./admin_gate";
import {
  handleRequestAccessPost,
  readEmailParam,
  renderRequestForm,
} from "./request_access";
import {
  handleApiApprove,
  handleApiAuditExport,
  handleApiDeny,
  handleApiForceSignout,
  handleApiPartnerSetFirm,
  handleApiPortalLink,
  handleApiRevoke,
  handleApiSignups,
  renderDashboard,
  renderDenied,
} from "./admin_routes";
import { d1SaltStore, utcDateString } from "../../audit/src/salt";
import { writeSession } from "../../approvals/src/sessions";
import { ensureProfile } from "../../approvals/src/partner_profiles";
import { verifyWorkosWebhook, webhookAuditInput } from "./webhooks";
import { routeDsyncEvent } from "./dsync_router";

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
  request?: Request,
): Promise<Response> {
  const raw = url.searchParams.get(env.RETURN_TO_PARAM) ?? "";
  const returnTo = isValidReturnTo(raw) ? raw : env.DEFAULT_RETURN_TO;

  // MIL-146 — capture original-authorize IP + UA inside the HMAC-signed
  // state. Compared at /callback to flag forwarded magic-link clicks.
  // Optional — request is only available from the fetch entrypoint; tests
  // can call without it and the forward-detection just no-ops.
  const ip = request?.headers.get("cf-connecting-ip") ?? undefined;
  const ua = request?.headers.get("user-agent") ?? undefined;

  const state = await signState(
    { returnTo, ts: now, ip, ua },
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

// MIL-161 — GET /logout. If a session cookie is present, render a
// CSRF-tokened confirm form (POST → handleLogoutAction). If not, the
// user is already signed out — render the done page directly. Note
// no cookie is cleared on GET; cookies are only cleared on the POST
// path (or on the "already signed out" branch where there's nothing
// to clear anyway). This makes `<img src="/logout">` a no-op.
async function handleLogoutGet(request: Request, env: Env): Promise<Response> {
  const jwt = extractCookie(request.headers.get("cookie"), env.COOKIE_NAME);
  if (!jwt) {
    // Already signed out (or never signed in). Render the done page
    // with no outcome block — there's nothing to report.
    return new Response(renderLogoutDone(null), {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    });
  }
  const csrf = await buildCsrfToken(jwt, env.STATE_SIGNING_KEY);
  return new Response(
    renderLogoutConfirm(csrf, "https://app.cjipro.com/portal"),
    {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    },
  );
}

// MIL-161 — POST /logout. Verify the CSRF token, then run the full
// lifecycle: delete sessions row, revoke WorkOS session, clear cookie.
// Cookie is ALWAYS cleared on success, even if the WorkOS revoke or
// D1 delete fails — the user-visible cookie clear is the floor.
async function handleLogoutPost(
  request: Request,
  env: Env,
): Promise<{ response: Response; outcome: import("./logout").LogoutOutcome | null }> {
  const jwt = extractCookie(request.headers.get("cookie"), env.COOKIE_NAME);
  // No cookie on POST → nothing to do. Treat as success (idempotent).
  if (!jwt) {
    return {
      response: new Response(renderLogoutDone(null), {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      }),
      outcome: null,
    };
  }
  // Read CSRF from form body. Workers' Request.formData() handles
  // application/x-www-form-urlencoded and multipart equivalently.
  let formCsrf: string | null = null;
  try {
    const form = await request.formData();
    const raw = form.get("csrf");
    formCsrf = typeof raw === "string" ? raw : null;
  } catch {
    formCsrf = null;
  }
  const csrfOk = await verifyCsrfToken(formCsrf, jwt, env.STATE_SIGNING_KEY);
  if (!csrfOk) {
    return {
      response: new Response(renderLogoutCsrfFailed(), {
        status: 400,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      }),
      outcome: null,
    };
  }
  const outcome = await performLogout(jwt, {
    db: env.AUDIT_DB,
    workosApiKey: env.WORKOS_CLIENT_SECRET,
  });
  const setCookie = buildClearCookie(cookieConfigFromEnv(env));

  // MIL-161 v2 — server-side revoke alone leaves the AuthKit-domain
  // cookie alive in the browser, so the next /authorize hit silent-
  // auths the user back in. Send the browser through AuthKit's
  // front-channel logout URL so it clears its own cookie, then back
  // to /logout/done. If authKitHost is unset (e.g. test envs), fall
  // back to rendering the done page directly.
  const sid = extractJwtSid(jwt);
  const authkitLogoutUrl = buildAuthkitLogoutUrl(
    env.AUTHKIT_HOST,
    sid,
    "https://login.cjipro.com/logout/done",
  );
  if (authkitLogoutUrl) {
    return {
      response: new Response(null, {
        status: 302,
        headers: {
          location: authkitLogoutUrl,
          "cache-control": "no-store",
          "set-cookie": setCookie,
        },
      }),
      outcome,
    };
  }
  return {
    response: new Response(renderLogoutDone(outcome), {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
        "set-cookie": setCookie,
      },
    }),
    outcome,
  };
}

// MIL-138 — friendly user-facing reason mapping. The internal `reason`
// codes (used by audit logs + telemetry) are short enums like "expired"
// / "bad-signature" / "auth-error". On the user's screen we render a
// human-readable sentence rather than the raw code, so the UI carries
// no third-party-product names and no internal jargon. Adding a new
// reason without a mapping falls back to the generic message — the
// internal code is still recorded in the audit log unchanged.
export const REASON_MESSAGES: Record<string, string> = {
  "expired": "Your sign-in link has expired.",
  "bad-signature": "Your sign-in link couldn't be verified.",
  "missing-params": "We couldn't read your sign-in link.",
  "auth-error": "Your sign-in didn't complete.",
  "http-error": "We couldn't reach the sign-in service.",
  "network-error": "We couldn't reach the sign-in service.",
  "missing-access-token": "We couldn't complete your sign-in.",
};

export function renderErrorPage(status: number, reason: string): Response {
  const message =
    REASON_MESSAGES[reason] ?? "We couldn't complete your sign-in.";
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign-in error · CJI</title>
${FONTS_BLOCK}
<style>
  :root { --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7;
    --serif: ${FONT_STACK_SERIF};
    --sans: ${FONT_STACK_SANS}; }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font: 16px/1.55 var(--sans); }
  main { max-width:32rem; margin:6rem auto; padding:2rem; }
  h1 { font-family: var(--serif); font-weight:600; font-size:1.4rem; margin:0 0 0.75rem; }
  p { margin:0.5rem 0; color:var(--muted); }
  a { color:#003A5C; }
</style>
</head>
<body>
<main>
<h1>Sign-in error</h1>
<p>${message}</p>
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
    let path = url.pathname;
    const method = request.method;

    // MIL-83 — admin.cjipro.com is bound to this Worker as a second
    // custom domain. On that host the dashboard lives at root, so
    // rewrite /  → /admin and /api/* → /admin/api/* before route
    // matching. Auth endpoints (/, /callback, /logout, /webhooks/*,
    // /healthz, /favicon.ico) are NOT exposed on the admin host —
    // anything that doesn't match the admin path shape returns 404
    // to keep the host scoped to admin UI only. login.cjipro.com is
    // unaffected; /admin and /admin/api/* continue to work there.
    if (url.host === "admin.cjipro.com") {
      if (path === "/" || path === "") {
        path = "/admin";
      } else if (path.startsWith("/api/")) {
        path = "/admin" + path;
      } else if (!path.startsWith("/admin")) {
        return new Response("not found", {
          status: 404,
          headers: { "content-type": "text/plain" },
        });
      }
    }

    // MIL-66b/67a/161 — routes that accept POST: /request-access,
    // /admin/api/*, /webhooks/workos, /logout. Others are GET-only.
    const isPostPath =
      path === "/request-access" ||
      path === "/webhooks/workos" ||
      path === "/logout" ||
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
      // MIL-71 — route dsync.* events to typed handlers. Side
      // effects (auto_approve / auto_revoke) run synchronously so
      // the audit row reflects the outcome. Non-dsync events fall
      // through to the generic workos.webhook bucket.
      let dsyncOutcome = null;
      if (env.AUDIT_DB) {
        try {
          dsyncOutcome = await routeDsyncEvent(env.AUDIT_DB, result.event);
        } catch (err) {
          console.log(
            JSON.stringify({
              ts: new Date().toISOString(),
              dsync_route_error:
                err instanceof Error ? err.message : String(err),
              event_id: result.rawId,
              event_type: result.rawType,
            }),
          );
        }
      }

      const baseAudit = baseAuditInput(request, path);
      const auditEvent =
        dsyncOutcome?.eventType
          ? {
              ...baseAudit,
              worker: "magic-link" as const,
              event_type: dsyncOutcome.eventType,
              reason: dsyncOutcome.email ?? result.rawType,
              detail: dsyncOutcome.detail ?? result.rawId,
            }
          : webhookAuditInput(result.event, baseAudit);
      audit(env, ctx, auditEvent);

      // 200 = "we accepted the event". Don't echo the body — WorkOS
      // expects a small ack; their retry policy backs off on 2xx.
      return new Response(`ok ${result.rawId}`, {
        status: 200,
        headers: { "content-type": "text/plain" },
      });
    }

    // --- MIL-66b: self-service signup + admin dashboard ---
    if (path === "/request-access") {
      if (method === "GET") {
        const prefilledEmail = readEmailParam(url);
        return renderRequestForm({ email: prefilledEmail });
      }
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
        return renderDenied({ kind: "misconfigured" }, request);
      }
      const check = await checkAdmin(request, env.AUDIT_DB, cfg);
      if (check.kind !== "ok") return renderDenied(check, request);
      const adminEmail = check.email;

      if (path === "/admin") return renderDashboard(adminEmail);
      if (path === "/admin/api/signups" && method === "GET") {
        return handleApiSignups(env.AUDIT_DB);
      }
      if (path === "/admin/api/audit_export" && method === "GET") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.audit_export",
          session_sub: adminEmail,
          detail: url.searchParams.get("org") ?? "",
        });
        return handleApiAuditExport(url, env.AUDIT_DB);
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
      // MIL-152 — admin attaches firm_slug + firm_name to a sub.
      if (path === "/admin/api/partner_set_firm" && method === "POST") {
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "admin.partner_firm_set",
          session_sub: adminEmail,
        });
        return handleApiPartnerSetFirm(request, env.AUDIT_DB);
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
        undefined,
        Date.now(),
        // MIL-146 — pass the /callback request's IP + UA so handleCallback
        // can compare against the IP + UA captured at /authorize (carried
        // inside the HMAC-signed state token). Non-blocking; informs the
        // forwarded_use_detected audit event only.
        {
          ip: request.headers.get("cf-connecting-ip") ?? undefined,
          userAgent: request.headers.get("user-agent") ?? undefined,
        },
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
            writeSession(
              db,
              sub,
              outcome.userEmail,
              outcome.organizationId,
            ).catch((err) => {
              console.log(
                JSON.stringify({
                  ts: new Date().toISOString(),
                  session_write_error:
                    err instanceof Error ? err.message : String(err),
                }),
              );
            }),
          );
          // MIL-152 — first-touch partner_profiles row. Idempotent;
          // INSERT OR IGNORE means this never overwrites a profile
          // that already carries admin-set firm fields or self-affirmed
          // display_name/role. Same fail-open posture as writeSession.
          ctx.waitUntil(
            ensureProfile(db, sub, outcome.userEmail).catch((err) => {
              console.log(
                JSON.stringify({
                  ts: new Date().toISOString(),
                  partner_profile_write_error:
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
        // MIL-146 — fires AFTER the success row so the timeline reads
        // success-then-forward-flag rather than the opposite. detail
        // carries the heuristic outcome so partner-portal queries
        // ("was this sign-in forwarded?") can filter on it.
        if (outcome.forward) {
          audit(env, ctx, {
            ...baseAuditInput(request, path),
            event_type: "magic_link.forwarded_use_detected",
            session_sub: sub,
            detail: JSON.stringify(outcome.forward),
          });
        }
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

    if (path === "/logout/done") {
      // MIL-161 v2 — AuthKit redirects here after clearing its own
      // session cookie. By this point our cookie was already cleared
      // on the original POST /logout response. Stateless render — no
      // outcome detail (it didn't survive the AuthKit redirect; the
      // audit row carries the full lifecycle record).
      return new Response(renderLogoutDone(null), {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      });
    }

    if (path === "/logout") {
      // MIL-161 — GET shows the confirm page (no cookie clear here),
      // POST runs the lifecycle (delete sessions row + WorkOS revoke +
      // cookie clear). Audit fires on POST only — GET is a render,
      // not a state change.
      if (method === "GET") {
        return handleLogoutGet(request, env);
      }
      if (method === "POST") {
        const { response, outcome } = await handleLogoutPost(request, env);
        audit(env, ctx, {
          ...baseAuditInput(request, path),
          event_type: "magic_link.logout",
          detail: outcome ? outcomeToAuditDetail(outcome) : "no-cookie",
          reason:
            outcome === null
              ? "no-cookie-or-csrf-failed"
              : outcome.sessions_row_deleted === "error" ||
                outcome.workos_session_revoked === "error"
                ? "partial"
                : "complete",
        });
        return response;
      }
      // Other methods → 405. Stops accidental DELETE/PUT scanners
      // from spinning up the lifecycle.
      return new Response("method not allowed", {
        status: 405,
        headers: { "content-type": "text/plain", "allow": "GET, POST" },
      });
    }

    if (path === "/") {
      audit(env, ctx, {
        ...baseAuditInput(request, path),
        event_type: "magic_link.authorize",
      });
      return handleAuthorize(url, env, Date.now(), request);
    }

    return new Response("not found", {
      status: 404,
      headers: { "content-type": "text/plain" },
    });
  },
};
