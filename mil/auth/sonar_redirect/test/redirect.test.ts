// MIL-95 sonar.cjipro.com redirect Worker tests.

import { describe, expect, test } from "vitest";
import worker, { type Env } from "../src/index";

const TARGET = "https://app.cjipro.com/reckoner?mode=ask";

function req(path: string, method = "GET"): Request {
  return new Request(`https://sonar.cjipro.com${path}`, { method });
}

const ENV = {} as Env;

describe("sonar.cjipro.com 301 stub", () => {
  test("/ → 301 to app.cjipro.com/reckoner", async () => {
    const res = await worker.fetch(req("/"), ENV);
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("/anything/path → 301 to same target", async () => {
    const res = await worker.fetch(req("/some/deep/path"), ENV);
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("/api/ask → 301 (legacy API path also retires)", async () => {
    const res = await worker.fetch(req("/api/ask", "POST"), ENV);
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("response body has clickable fallback for non-redirect-following clients", async () => {
    const res = await worker.fetch(req("/"), ENV);
    const body = await res.text();
    expect(body).toContain(TARGET);
    expect(body).toContain("Moved");
  });

  test("cache-control allows CDN caching for a day", async () => {
    const res = await worker.fetch(req("/"), ENV);
    expect(res.headers.get("cache-control")).toContain("max-age=86400");
  });
});
