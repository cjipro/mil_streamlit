// MIL-87 — /briefing-v4 cutover. The legacy path 301-redirects to
// the public sanitised sample at /insights/sample-briefing/. Fires
// BEFORE decide() so ENFORCE state, session presence, and
// approved_users state are all irrelevant — the path is gone.

import { beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("../src/session", async () => {
  const actual = await vi.importActual<typeof import("../src/session")>(
    "../src/session",
  );
  return { ...actual, verifySession: vi.fn() };
});

import worker, { type Env } from "../src/index";
import { verifySession } from "../src/session";

beforeEach(() => {
  vi.mocked(verifySession).mockReset();
  // Default: behave like the real module — no token = missing.
  vi.mocked(verifySession).mockImplementation(async (token) => {
    if (!token) return { kind: "missing" };
    return { kind: "valid", payload: { sub: "u_test" } };
  });
});

function envWith(enforce: boolean): Env {
  return {
    ENFORCE: enforce ? "true" : "false",
    SESSION_COOKIE_NAME: "__Secure-cjipro-session",
    JWKS_URL: "https://ideal-log-65-staging.authkit.app/oauth2/jwks",
    EXPECTED_AUD: "client_x",
    EXPECTED_ISS: "https://ideal-log-65-staging.authkit.app",
    LOGIN_URL: "https://login.cjipro.com/",
    RETURN_TO_PARAM: "return_to",
    JWKS_CACHE_TTL_SECONDS: "3600",
    PUBLIC_PATHS: "=/,=/privacy",
  };
}

function testCtx(): ExecutionContext {
  return {
    waitUntil(_: Promise<unknown>) {},
    passThroughOnException() {},
    props: {},
  } as unknown as ExecutionContext;
}

const TARGET = "https://cjipro.com/insights/sample-briefing/";

describe("MIL-87 legacy /briefing-v4 redirect", () => {
  test("/briefing-v4 → 301 to sample-briefing (no trailing slash)", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4"),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("/briefing-v4/ → 301 to sample-briefing", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/"),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("/briefing-v4/index.html → 301 to sample-briefing", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/index.html"),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("redirect fires under ENFORCE=true too (no auth bypass needed)", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/"),
      envWith(true),
      testCtx(),
    );
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });

  test("/briefing (V1) NOT redirected — still actively served", async () => {
    // V1 is load-bearing (V2/V3/V4 patch its HTML). Do not collapse
    // /briefing into the cutover.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin v1", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        new Request("https://cjipro.com/briefing"),
        envWith(false),
        testCtx(),
      );
      // shadow mode passes through to origin
      expect(res.status).toBe(200);
      expect(await res.text()).toBe("origin v1");
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("/briefing-v3/ NOT redirected — still actively served", async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin v3", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        new Request("https://cjipro.com/briefing-v3/"),
        envWith(false),
        testCtx(),
      );
      expect(res.status).toBe(200);
      expect(await res.text()).toBe("origin v3");
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("/briefing-v40 (substring trap) NOT redirected", async () => {
    // Defensive: startsWith("/briefing-v4/") prevents catching paths
    // that merely start with the literal "/briefing-v4" substring.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        new Request("https://cjipro.com/briefing-v40"),
        envWith(false),
        testCtx(),
      );
      expect(res.status).toBe(200);
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("redirect preserved even with valid cookie (path is gone)", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: { cookie: "__Secure-cjipro-session=anything" },
      }),
      envWith(true),
      testCtx(),
    );
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe(TARGET);
  });
});
