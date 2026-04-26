// MIL-95 — sonar.cjipro.com retirement Worker
//
// Sonar product moved into Reckoner ask-mode at app.cjipro.com under MIL-93B.
// sonar.cjipro.com retires by 301-redirecting every path (including /api/*)
// to the Reckoner ask-mode surface. Tunnel ingress for sonar.cjipro.com is
// removed in the same change so the redirect is the only thing the host
// serves.
//
// Why 301 (permanent), not 302: bookmarked Streamlit chat URLs and any
// cached search results should update; the move is permanent. /api/* is
// also redirected — any browser that was hitting the legacy API directly
// gets pointed at the Reckoner UI; programmatic callers will see 301 with
// a Location header and can re-target.

const TARGET = "https://app.cjipro.com/reckoner?mode=ask";

export interface Env {
  // No env. Hard-coded target — this Worker has one job.
}

export default {
  async fetch(_request: Request, _env: Env): Promise<Response> {
    return new Response(
      `<!DOCTYPE html><html><head><meta charset="utf-8">` +
      `<meta http-equiv="refresh" content="0; url=${TARGET}">` +
      `<title>Moved · CJI Reckoner</title></head>` +
      `<body><p>This URL has moved to ` +
      `<a href="${TARGET}">app.cjipro.com/reckoner</a>.</p></body></html>`,
      {
        status: 301,
        headers: {
          "location": TARGET,
          "content-type": "text/html; charset=utf-8",
          "cache-control": "public, max-age=86400",
        },
      },
    );
  },
};
