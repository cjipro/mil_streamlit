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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // Only GETs flow through magic-link. Everything else 405.
    if (method !== "GET") {
      return new Response("method not allowed", {
        status: 405,
        headers: { allow: "GET" },
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
      return renderErrorPage(outcome.status, outcome.reason);
    }

    if (path === "/logout") {
      return handleLogout(env);
    }

    if (path === "/") {
      return handleAuthorize(url, env, Date.now());
    }

    return new Response("not found", {
      status: 404,
      headers: { "content-type": "text/plain" },
    });
  },
};
