import { describe, expect, test } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/env";
import { signState } from "../src/state";

const ENV: Env = {
  AUTHKIT_HOST: "ideal-log-65-staging.authkit.app",
  CLIENT_ID: "client_01KPY7CA07ZD1WG3DMQE1FZQE1",
  REDIRECT_URI: "https://magic-link.example.workers.dev/callback",
  DEFAULT_RETURN_TO: "/",
  COOKIE_NAME: "__Secure-cjipro-session",
  COOKIE_DOMAIN: ".cjipro.com",
  COOKIE_MAX_AGE_SECONDS: "3600",
  RETURN_TO_PARAM: "return_to",
  WORKOS_CLIENT_SECRET: "sk_test_example",
  STATE_SIGNING_KEY: "test-signing-key-0123456789abcdef",
};

function get(path: string): Request {
  return new Request(`https://login.cjipro.com${path}`);
}

describe("Worker router", () => {
  test("GET /healthz → 200 ok", async () => {
    const res = await worker.fetch(get("/healthz"), ENV);
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
  });

  test("GET /favicon.ico → 204", async () => {
    const res = await worker.fetch(get("/favicon.ico"), ENV);
    expect(res.status).toBe(204);
  });

  test("POST / → 405", async () => {
    const req = new Request("https://login.cjipro.com/", { method: "POST" });
    const res = await worker.fetch(req, ENV);
    expect(res.status).toBe(405);
  });

  test("GET /unknown → 404", async () => {
    const res = await worker.fetch(get("/unknown"), ENV);
    expect(res.status).toBe(404);
  });
});

describe("GET / — authorize redirect", () => {
  test("302 to AuthKit with signed state", async () => {
    const res = await worker.fetch(
      get("/?return_to=/briefing-v4/"),
      ENV,
    );
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    const url = new URL(loc);
    expect(url.origin).toBe(
      "https://ideal-log-65-staging.authkit.app",
    );
    expect(url.pathname).toBe("/oauth2/authorize");
    expect(url.searchParams.get("client_id")).toBe(ENV.CLIENT_ID);
    expect(url.searchParams.get("redirect_uri")).toBe(ENV.REDIRECT_URI);
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("provider")).toBe("authkit");
    expect(url.searchParams.get("state")).toBeTruthy();
  });

  test("invalid return_to falls back to DEFAULT_RETURN_TO", async () => {
    const res = await worker.fetch(
      get("/?return_to=https://evil.example.com/"),
      ENV,
    );
    expect(res.status).toBe(302);
    // We can't see the returnTo inside the signed state from the
    // outside — but the behaviour is covered by state.test.ts's
    // isValidReturnTo suite + callback.test.ts's fallback test.
  });

  test("no return_to param still works", async () => {
    const res = await worker.fetch(get("/"), ENV);
    expect(res.status).toBe(302);
  });
});

describe("GET /logout", () => {
  test("clears cookie + redirects", async () => {
    const res = await worker.fetch(get("/logout"), ENV);
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(ENV.DEFAULT_RETURN_TO);
    const sc = res.headers.get("set-cookie")!;
    expect(sc).toContain("__Secure-cjipro-session=");
    expect(sc).toContain("Max-Age=0");
    expect(sc).toContain("Domain=.cjipro.com");
  });
});

describe("GET /callback", () => {
  test("success → 302 + Set-Cookie", async () => {
    const state = await signState(
      { returnTo: "/briefing-v4/", ts: Date.now() },
      ENV.STATE_SIGNING_KEY,
    );
    // Stub globalThis.fetch for the WorkOS exchange call.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({ access_token: "eyJ.tok.sig", user: { id: "u1" } }),
        { status: 200, headers: { "content-type": "application/json" } },
      )) as typeof fetch;
    try {
      const res = await worker.fetch(
        get(`/callback?code=abc&state=${encodeURIComponent(state)}`),
        ENV,
      );
      expect(res.status).toBe(302);
      expect(res.headers.get("location")).toBe("/briefing-v4/");
      expect(res.headers.get("set-cookie")).toContain(
        "__Secure-cjipro-session=eyJ.tok.sig",
      );
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("bad state → error HTML page (400)", async () => {
    const res = await worker.fetch(
      get("/callback?code=abc&state=garbage"),
      ENV,
    );
    expect(res.status).toBe(400);
    expect(res.headers.get("content-type")).toContain("text/html");
    const body = await res.text();
    expect(body).toContain("Sign-in error");
  });

  test("missing params → 400", async () => {
    const res = await worker.fetch(get("/callback"), ENV);
    expect(res.status).toBe(400);
  });
});
