// MIL-84 + MIL-93 Phase A + MIL-86 — pathname → handler dispatch for app.cjipro.com.
//
// MVP routes:
//   /                              → 302 to /reckoner
//   /reckoner                      → MIL-92 Reckoner default surface
//   /reckoner?mode=ask             → MIL-93 Reckoner ask-mode (UI shell)
//   /sonar                         → MIL-86 redirect to /sonar/{default_client}/
//   /sonar/{client_slug}/          → MIL-86 latest Sonar briefing for slug
//   /sonar/{client_slug}/{date}/   → MIL-86 historical Sonar briefing
//   /healthz                       → liveness probe (public allowlist)
//   /favicon.ico                   → empty 204
//
// Future:
//   /pulse                         → Pulse workspace (post-MVP)
//   /lever                         → Lever workspace (post-MVP)
//   /reckoner POST (mode=ask)      → MIL-93 Phase B: live retrieval

import { renderReckonerHtml, mvpSnapshot, type ReckonerMode } from "./reckoner";

export type RouteHandler = (request: Request) => Response | Promise<Response>;

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

// ── MIL-86 — /sonar/{client_slug}/{date}/ Sonar briefing routes ─────────────
//
// Read-through to the GitHub Pages origin (cjipro.com/sonar/...). The
// app.cjipro.com Worker auth-gates these paths via index.ts decide() —
// by the time sonarHandler runs, the request is already either public-
// allowlisted (impossible for /sonar/*) or carries a valid session
// cookie + approved-user gate.
//
// Soft launch (MIL-86 spec): no org-membership check yet — clients.yaml
// workos_org_id is empty for all clients today. Any approved alpha user
// can view any /sonar/{slug}/. The org-membership filter lands when the
// first non-Barclays subject arrives (a separate ticket).

const SONAR_SLUG_RE  = /^[a-z0-9-]+$/;
const SONAR_DATE_RE  = /^\d{4}-\d{2}-\d{2}$/;
const SONAR_ORIGIN   = "https://cjipro.com";
const DEFAULT_CLIENT = "barclays";

function sonarSplit(pathname: string): string[] {
  // Split /sonar/foo/bar/  → ["sonar","foo","bar"]; trailing slash stripped.
  return pathname.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
}

async function sonarHandler(request: Request, fetcher: typeof fetch = fetch): Promise<Response> {
  const url = new URL(request.url);
  const parts = sonarSplit(url.pathname);

  // /sonar (or /sonar/) → redirect to default client's latest briefing.
  if (parts.length === 1) {
    return Response.redirect(
      new URL(`/sonar/${DEFAULT_CLIENT}/`, request.url).toString(),
      302,
    );
  }

  const slug = parts[1];
  if (!SONAR_SLUG_RE.test(slug)) {
    return notFoundResponse(url.pathname);
  }

  const date: string | undefined = parts[2];
  if (date !== undefined && !SONAR_DATE_RE.test(date)) {
    return notFoundResponse(url.pathname);
  }

  // Origin path — kept symmetric with publish_v4 --target-path layout:
  //   latest:     /sonar/{slug}/index.html
  //   historical: /sonar/{slug}/{date}/index.html
  const originPath = date
    ? `/sonar/${slug}/${date}/index.html`
    : `/sonar/${slug}/index.html`;
  const originUrl = `${SONAR_ORIGIN}${originPath}`;

  let upstream: Response;
  try {
    upstream = await fetcher(originUrl, {
      cf: { cacheTtl: 60, cacheEverything: true },
    } as RequestInit);
  } catch {
    return notFoundResponse(url.pathname);
  }
  if (!upstream.ok) {
    return notFoundResponse(url.pathname);
  }
  const html = await upstream.text();
  return htmlResponse(html);
}

export async function dispatch(request: Request): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === "/" || path === "") return rootRedirect(request);
  if (path === "/reckoner" || path === "/reckoner/") return reckonerHandler(request);
  if (path === "/sonar" || path === "/sonar/" || path.startsWith("/sonar/")) {
    return sonarHandler(request);
  }
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

// Exported for tests — lets the test stub `fetcher` without touching globals.
export { sonarHandler as _sonarHandler };
