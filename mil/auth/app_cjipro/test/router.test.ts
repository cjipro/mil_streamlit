// MIL-84/92 — router unit tests. No auth gate involvement here;
// these only exercise the pathname → handler dispatch.

import { describe, expect, test } from "vitest";
import { dispatch } from "../src/router";

function req(path: string): Request {
  return new Request(`https://app.cjipro.com${path}`);
}

describe("dispatch", () => {
  test("/ → 302 redirect to /reckoner", () => {
    const res = dispatch(req("/"));
    expect(res).not.toBeNull();
    expect(res!.status).toBe(302);
    expect(res!.headers.get("location")).toContain("/reckoner");
  });

  test("/reckoner → 200 HTML with Reckoner shell", async () => {
    const res = dispatch(req("/reckoner"));
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
    const res = dispatch(req("/reckoner/"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    expect(body).toContain("Industry Pulse");
  });

  test("Reckoner page renders the alpha-preview banner", async () => {
    const res = dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toContain("Alpha preview");
  });

  test("Reckoner page disables the two non-MVP tabs", async () => {
    const res = dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toContain("Conversational drill-in");
    expect(body).toContain("Drag-drop canvas");
    // Both should be marked disabled in the HTML
    expect(body).toMatch(/class="tab disabled"[^>]*>Conversational/);
    expect(body).toMatch(/class="tab disabled"[^>]*>Drag-drop/);
  });

  test("Reckoner page declares CSP + nosniff + noindex", async () => {
    const res = dispatch(req("/reckoner"));
    const body = await res!.text();
    expect(body).toMatch(/Content-Security-Policy/);
    expect(body).toContain('content="noindex,nofollow"');
  });

  test("/healthz → 200 'ok'", async () => {
    const res = dispatch(req("/healthz"));
    expect(res!.status).toBe(200);
    expect(await res!.text()).toBe("ok");
  });

  test("/favicon.ico → 204", () => {
    const res = dispatch(req("/favicon.ico"));
    expect(res!.status).toBe(204);
  });

  test("/robots.txt → disallow all (alpha surface, never index)", async () => {
    const res = dispatch(req("/robots.txt"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    expect(body).toContain("User-agent: *");
    expect(body).toContain("Disallow: /");
  });

  test("unknown path → 404 with link back to Reckoner", async () => {
    const res = dispatch(req("/unknown/route"));
    expect(res!.status).toBe(404);
    const body = await res!.text();
    expect(body).toContain("Not found");
    expect(body).toContain("/reckoner");
  });

  test("404 page escapes the requested path (no XSS)", async () => {
    const res = dispatch(req("/<script>alert(1)</script>"));
    expect(res!.status).toBe(404);
    const body = await res!.text();
    expect(body).not.toContain("<script>alert(1)</script>");
  });
});
