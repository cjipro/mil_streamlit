// MIL-84 + MIL-93 Phase A — pathname → handler dispatch for app.cjipro.com.
//
// MVP routes:
//   /                              → 302 to /reckoner
//   /reckoner                      → MIL-92 Reckoner default surface
//   /reckoner?mode=ask             → MIL-93 Reckoner ask-mode (UI shell)
//   /healthz                       → liveness probe (public allowlist)
//   /favicon.ico                   → empty 204
//
// Future:
//   /sonar/{client_slug}/{date}/   → MIL-86 Sonar URL migration
//   /pulse                         → Pulse workspace (post-MVP)
//   /lever                         → Lever workspace (post-MVP)
//   /reckoner POST (mode=ask)      → MIL-93 Phase B: live retrieval

import { renderReckonerHtml, mvpSnapshot, type ReckonerMode } from "./reckoner";

export type RouteHandler = (request: Request) => Response;

function htmlResponse(html: string, status = 200): Response {
  return new Response(html, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "strict-origin-when-cross-origin",
    },
  });
}

function notFoundResponse(pathname: string): Response {
  const html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Not found · CJI</title>
<meta name="robots" content="noindex,nofollow">
<style>body{font:16px/1.55 Georgia,serif;color:#0A1E2A;background:#FAFAF7;
margin:0;padding:0}main{max-width:32rem;margin:6rem auto;padding:2rem}
h1{font-weight:600;font-size:1.4rem;margin:0 0 0.75rem}
p{color:#6B7A85}a{color:#003A5C}</style></head>
<body><main><h1>Not found</h1>
<p>No surface lives at <code>${pathname.replace(/[<>&"']/g, "")}</code> on this domain.</p>
<p><a href="/reckoner">Go to Reckoner</a></p></main></body></html>`;
  return htmlResponse(html, 404);
}

function parseMode(url: URL): ReckonerMode {
  const raw = url.searchParams.get("mode");
  return raw === "ask" ? "ask" : "default";
}

function reckonerHandler(request: Request): Response {
  const url = new URL(request.url);
  return htmlResponse(renderReckonerHtml(mvpSnapshot(), parseMode(url)));
}

function rootRedirect(request: Request): Response {
  return Response.redirect(new URL("/reckoner", request.url).toString(), 302);
}

function healthzHandler(_request: Request): Response {
  return new Response("ok", {
    status: 200,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

function faviconHandler(_request: Request): Response {
  // Empty 204 keeps proxy IT-team scanners quiet without shipping a binary.
  return new Response(null, { status: 204 });
}

export function dispatch(request: Request): Response | null {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === "/" || path === "") return rootRedirect(request);
  if (path === "/reckoner" || path === "/reckoner/") return reckonerHandler(request);
  if (path === "/healthz") return healthzHandler(request);
  if (path === "/favicon.ico") return faviconHandler(request);
  if (path === "/robots.txt") {
    return new Response("User-agent: *\nDisallow: /\n", {
      status: 200,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
  if (path === "/.nojekyll") {
    return new Response("", { status: 200 });
  }
  return notFoundResponse(path);
}
