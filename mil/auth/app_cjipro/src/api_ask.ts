// MIL-93 Phase B — /api/ask reverse-proxy
//
// Forwards POST /api/ask to the Python chat backend (mil/chat/api_server.py)
// reachable via the Cloudflare Tunnel. The auth gate in index.ts has
// already decided() before this handler runs, so by the time we're here
// the request either passed the approved-user check (API_ENFORCE=true)
// or we're in shadow mode and the gate logged-but-passed.
//
// We forward the body verbatim and inject:
//   - X-CJI-Scope:  product surface label (reckoner | sonar | all). The
//                   backend reads this to switch Barclays-default and
//                   firm-specific refusal behaviour.
//   - Cf-Access-Authenticated-User-Email: the partner_id the backend
//                   stamps into audit + feedback rows. We use the email
//                   resolved from the session sub during the auth pass
//                   if it's available.
//
// We do NOT forward Cookie or Host — Cookie carries the JWT (already
// validated upstream) and Host would mis-route the upstream call.

export interface ApiAskEnv {
  ASK_BACKEND_URL: string;     // e.g. https://chat-backend.cjipro.com/api/ask
  ASK_BACKEND_SCOPE: string;   // e.g. reckoner | sonar | all
}

export interface ApiAskCallerIdentity {
  email?: string;              // resolved during auth gate
}

const HOP_HEADERS = new Set([
  "cookie",
  "host",
  "content-length", // recomputed by the upstream fetcher
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "te",
  "trailer",
]);

function buildUpstreamHeaders(
  request: Request,
  env: ApiAskEnv,
  identity: ApiAskCallerIdentity,
): Headers {
  const out = new Headers();
  for (const [key, value] of request.headers.entries()) {
    if (HOP_HEADERS.has(key.toLowerCase())) continue;
    if (key.toLowerCase() === "x-cji-scope") continue; // we set this ourselves
    out.set(key, value);
  }
  out.set("X-CJI-Scope", env.ASK_BACKEND_SCOPE || "all");
  if (identity.email) {
    out.set("Cf-Access-Authenticated-User-Email", identity.email);
  }
  return out;
}

export async function apiAskHandler(
  request: Request,
  env: ApiAskEnv,
  identity: ApiAskCallerIdentity = {},
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  if (request.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "method_not_allowed", method: request.method }),
      {
        status: 405,
        headers: {
          "content-type": "application/json; charset=utf-8",
          "allow": "POST",
        },
      },
    );
  }

  if (!env.ASK_BACKEND_URL) {
    return new Response(
      JSON.stringify({ error: "backend_unconfigured" }),
      {
        status: 500,
        headers: { "content-type": "application/json; charset=utf-8" },
      },
    );
  }

  const body = await request.arrayBuffer();
  const upstreamHeaders = buildUpstreamHeaders(request, env, identity);

  let upstream: Response;
  try {
    upstream = await fetcher(env.ASK_BACKEND_URL, {
      method: "POST",
      headers: upstreamHeaders,
      body,
    });
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: "backend_unreachable",
        detail: err instanceof Error ? err.message : String(err),
      }),
      {
        status: 502,
        headers: { "content-type": "application/json; charset=utf-8" },
      },
    );
  }

  // Stream upstream response back unchanged. Strip hop-by-hop headers so
  // we don't leak them through Cloudflare's edge.
  const respHeaders = new Headers();
  for (const [key, value] of upstream.headers.entries()) {
    if (HOP_HEADERS.has(key.toLowerCase())) continue;
    respHeaders.set(key, value);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: respHeaders,
  });
}
