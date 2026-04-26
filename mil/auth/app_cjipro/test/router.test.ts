// MIL-84/92 — router unit tests. No auth gate involvement here;
// these only exercise the pathname → handler dispatch.

import { describe, expect, test } from "vitest";
import { dispatch } from "../src/router";

function req(path: string): Request {
  return new Request(`https://app.cjipro.com${path}`);
}

describe("dispatch", () => {
  test("/ → 302 redirect to /reckoner", async () => {
    const res = await dispatch(req("/"));
    expect(res).not.toBeNull();
    expect(res!.status).toBe(302);
    expect(res!.headers.get("location")).toContain("/reckoner");
  });

  test("/reckoner → 200 HTML with Reckoner shell", async () => {
    const res = await dispatch(req("/reckoner"));
    expect(res).not.toBeNull();
    expect(res!.status).toBe(200);
    expect(res!.headers.get("content-type")).toContain("text/html");
    const body = await res!.text();
    expect(body).toContain("Reckoner");
    expect(body).toContain("Industry Pulse");
    expect(body).toContain("Anomalies");
    expect(body).toContain("Decisions Surfaced");
  });

  test("/reckoner/ (trailing slash) routes the same", async () => {
    const res = await dispatch(req("/reckoner/"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    expect(body).toContain("Industry Pulse");
  });

  test("Reckoner page renders the alpha-preview banner", async () => {
    const res = await dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toContain("Alpha preview");
  });

  test("Reckoner page disables Drag-drop canvas tab (Conversational is alpha)", async () => {
    const res = await dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toContain("Conversational drill-in");
    expect(body).toContain("Drag-drop canvas");
    // Drag-drop is still the only fully-disabled tab
    expect(body).toMatch(/class="tab disabled"[^>]*>Drag-drop/);
    // Conversational drill-in is now an active <a> link to ?mode=ask
    expect(body).toMatch(/href="\/reckoner\?mode=ask"[^>]*>Conversational/);
  });

  test("/reckoner?mode=ask renders the live ask-mode UI", async () => {
    const res = await dispatch(req("/reckoner?mode=ask"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    expect(body).toContain("Ask Reckoner");
    expect(body).toContain("In scope");
    expect(body).toContain("Out of scope");
    // The ask-form textarea is present
    expect(body).toMatch(/<textarea[^>]*name="query"/);
    // Phase B: submit is enabled, response container present, fetch wired
    const submitMatch = body.match(/<button[^>]*id="ask-submit"[^>]*>/);
    expect(submitMatch).not.toBeNull();
    expect(submitMatch![0]).not.toMatch(/\bdisabled\b/);
    expect(body).toContain('id="ask-response"');
    expect(body).toContain('fetch("/api/ask"');
  });

  test("/reckoner?mode=ask shows Conversational tab as active", async () => {
    const res = await dispatch(req("/reckoner?mode=ask"));
    const body = await res!.text();
    expect(body).toMatch(/class="tab active"[^>]*aria-current="page"[^>]*>Conversational/);
    // Default surface should NOT be active
    expect(body).not.toMatch(/class="tab active"[^>]*>Default surface/);
  });

  test("/reckoner (no mode) shows Default surface tab as active", async () => {
    const res = await dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toMatch(/class="tab active"[^>]*aria-current="page"[^>]*>Default surface/);
  });

  test("/reckoner?mode=invalid falls back to default surface", async () => {
    const res = await dispatch(req("/reckoner?mode=invalid"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    // Should render the default body (Industry Pulse), not ask-mode
    expect(body).toContain("Industry Pulse");
    expect(body).not.toContain("Ask Reckoner");
  });

  test("Reckoner page declares CSP + nosniff + noindex", async () => {
    const res = await dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toMatch(/Content-Security-Policy/);
    expect(body).toContain('content="noindex,nofollow"');
  });

  test("/healthz → 200 'ok'", async () => {
    const res = await dispatch(req("/healthz"));
    expect(res!.status).toBe(200);
    expect(await res!.text()).toBe("ok");
  });

  test("/favicon.ico → 204", async () => {
    const res = await dispatch(req("/favicon.ico"));
    expect(res!.status).toBe(204);
  });

  test("/robots.txt → disallow all (alpha surface, never index)", async () => {
    const res = await dispatch(req("/robots.txt"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    expect(body).toContain("User-agent: *");
    expect(body).toContain("Disallow: /");
  });

  test("unknown path → 404 with link back to Reckoner", async () => {
    const res = await dispatch(req("/unknown/route"));
    expect(res!.status).toBe(404);
    const body = await res!.text();
    expect(body).toContain("Not found");
    expect(body).toContain("/reckoner");
  });

  test("404 page escapes the requested path (no XSS)", async () => {
    const res = await dispatch(req("/<script>alert(1)</script>"));
    expect(res!.status).toBe(404);
    const body = await res!.text();
    expect(body).not.toContain("<script>alert(1)</script>");
  });
});

// ── MIL-86 Sonar route tests ─────────────────────────────────────────────────
import { _sonarHandler } from "../src/router";

function sonarReq(path: string): Request {
  return new Request(`https://app.cjipro.com${path}`);
}

function makeFetchStub(response: { status: number; body?: string }): typeof fetch {
  return (async () => {
    return new Response(response.body ?? "", { status: response.status });
  }) as typeof fetch;
}

describe("sonarHandler — MIL-86", () => {
  test("/sonar redirects to /sonar/barclays/ (default subject)", async () => {
    const res = await _sonarHandler(sonarReq("/sonar"));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("/sonar/barclays/");
  });

  test("/sonar/ (trailing slash) also redirects to /sonar/barclays/", async () => {
    const res = await _sonarHandler(sonarReq("/sonar/"));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("/sonar/barclays/");
  });

  test("/sonar/barclays/ fetches latest from origin and serves it through", async () => {
    const fakeHtml = "<!DOCTYPE html><html><body>BRIEFING</body></html>";
    let originUrlSeen = "";
    const fetcher = (async (url: string) => {
      originUrlSeen = url;
      return new Response(fakeHtml, { status: 200 });
    }) as typeof fetch;

    const res = await _sonarHandler(sonarReq("/sonar/barclays/"), fetcher);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    expect(originUrlSeen).toBe("https://cjipro.com/sonar/barclays/index.html");
    expect(await res.text()).toContain("BRIEFING");
  });

  test("/sonar/barclays/2026-04-26/ fetches dated path from origin", async () => {
    let originUrlSeen = "";
    const fetcher = (async (url: string) => {
      originUrlSeen = url;
      return new Response("<html>HISTORICAL</html>", { status: 200 });
    }) as typeof fetch;

    const res = await _sonarHandler(sonarReq("/sonar/barclays/2026-04-26/"), fetcher);
    expect(res.status).toBe(200);
    expect(originUrlSeen).toBe("https://cjipro.com/sonar/barclays/2026-04-26/index.html");
  });

  test("/sonar/barclays/notadate/ rejects malformed date with 404", async () => {
    const res = await _sonarHandler(sonarReq("/sonar/barclays/notadate/"));
    expect(res.status).toBe(404);
  });

  test("/sonar/<bad>/ rejects non-slug-shaped client_slug with 404", async () => {
    const res = await _sonarHandler(sonarReq("/sonar/Bad_Slug/"));
    // Underscore is not in [a-z0-9-]
    expect(res.status).toBe(404);
  });

  test("/sonar/barclays/ origin 404 propagates as our 404 (not a partial render)", async () => {
    const fetcher = makeFetchStub({ status: 404, body: "" });
    const res = await _sonarHandler(sonarReq("/sonar/barclays/"), fetcher);
    expect(res.status).toBe(404);
  });

  test("origin throw is caught and returns 404 (not 500)", async () => {
    const fetcher = (async () => {
      throw new Error("origin unreachable");
    }) as typeof fetch;
    const res = await _sonarHandler(sonarReq("/sonar/barclays/"), fetcher);
    expect(res.status).toBe(404);
  });

  test("dispatch routes /sonar through to sonarHandler", async () => {
    const res = await dispatch(sonarReq("/sonar"));
    expect(res!.status).toBe(302);
    expect(res!.headers.get("location")).toContain("/sonar/barclays/");
  });
});
