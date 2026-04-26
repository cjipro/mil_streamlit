// MIL-87 + MIL-143 — /briefing-v4 cutover, cookie-aware.
//
// Cold visitors (no session cookie) → 302 to the sanitised public
// sample at /insights/sample-briefing/. Warm partners (cookie present
// — validity not checked at this layer; the destination bouncer
// re-auths) → 302 to app.cjipro.com/sonar/barclays/, the real
// authenticated briefing.
//
// Status is 302 + Cache-Control: no-store rather than the original
// MIL-87 301, because the destination is per-request (cookie state
// can change). 301 caches per-URL, which would lock a browser into
// whichever destination it saw first regardless of later auth state.
//
// Fires BEFORE decide() so ENFORCE state and the approved-users gate
// are both irrelevant — this layer is about path-level routing, not
// authorisation.

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

const COLD_TARGET = "https://cjipro.com/insights/sample-briefing/";
const WARM_TARGET = "https://app.cjipro.com/sonar/barclays/";

describe("MIL-87 + MIL-143 — cold visitor (no session cookie) → sample-briefing", () => {
  test("/briefing-v4 → 302 to sample-briefing (no trailing slash)", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4"),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(COLD_TARGET);
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  test("/briefing-v4/ → 302 to sample-briefing", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/"),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(COLD_TARGET);
  });

  test("/briefing-v4/index.html → 302 to sample-briefing", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/index.html"),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(COLD_TARGET);
  });

  test("redirect fires under ENFORCE=true too (no auth bypass needed)", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/"),
      envWith(true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(COLD_TARGET);
  });

  test("multiple unrelated cookies but no session cookie → cold-routed", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: { cookie: "cf_clearance=abc; _ga=GA1.2.xyz; locale=en-GB" },
      }),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(COLD_TARGET);
  });

  test("empty cookie header → cold-routed", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: { cookie: "" },
      }),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(COLD_TARGET);
  });
});

describe("MIL-143 — warm visitor (session cookie present) → real briefing", () => {
  test("session cookie present (valid value) → 302 to app.cjipro.com/sonar/barclays/", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: { cookie: "__Secure-cjipro-session=signed.jwt.token" },
      }),
      envWith(true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(WARM_TARGET);
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  test("session cookie present alongside other cookies → warm-routed", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: {
          cookie:
            "cf_clearance=xyz; __Secure-cjipro-session=anything; locale=en-GB",
        },
      }),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(WARM_TARGET);
  });

  test("expired/stale session cookie still warm-routes (validity not checked here)", async () => {
    // Per MIL-143 panel verdict: an expired cookie still routes warm
    // because the user was a partner. The destination bouncer at
    // app.cjipro.com handles the actual session validation and will
    // either pass them through or redirect to login as appropriate.
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: { cookie: "__Secure-cjipro-session=expired-or-malformed" },
      }),
      envWith(true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(WARM_TARGET);
  });

  test("warm-routing fires under ENFORCE=false (shadow) too — routing is independent of enforcement", async () => {
    const res = await worker.fetch(
      new Request("https://cjipro.com/briefing-v4/", {
        headers: { cookie: "__Secure-cjipro-session=anything" },
      }),
      envWith(false),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(WARM_TARGET);
  });
});

describe("MIL-87 + MIL-143 — paths that must NOT be touched", () => {
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

  test("/briefing-v40 (substring trap) NOT redirected — even with session cookie", async () => {
    // Defensive: startsWith("/briefing-v4/") prevents catching paths
    // that merely start with the literal "/briefing-v4" substring.
    // The cookie-aware refactor must not regress this.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        new Request("https://cjipro.com/briefing-v40", {
          headers: { cookie: "__Secure-cjipro-session=anything" },
        }),
        envWith(false),
        testCtx(),
      );
      expect(res.status).toBe(200);
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
