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

// Minimal ExecutionContext stub — captures waitUntil promises so
// tests can await them if they need to, and no-ops passThroughOnException.
function testCtx(): ExecutionContext {
  const pending: Promise<unknown>[] = [];
  return {
    waitUntil(p: Promise<unknown>) {
      pending.push(p);
    },
    passThroughOnException() {},
    props: {},
  } as unknown as ExecutionContext;
}

describe("Worker router", () => {
  test("GET /healthz → 200 ok", async () => {
    const res = await worker.fetch(get("/healthz"), ENV, testCtx());
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
  });

  test("GET /favicon.ico → 204", async () => {
    const res = await worker.fetch(get("/favicon.ico"), ENV, testCtx());
    expect(res.status).toBe(204);
  });

  test("POST / → 405", async () => {
    const req = new Request("https://login.cjipro.com/", { method: "POST" });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(405);
  });

  test("GET /unknown → 404", async () => {
    const res = await worker.fetch(get("/unknown"), ENV, testCtx());
    expect(res.status).toBe(404);
  });
});

describe("GET / — authorize redirect", () => {
  test("302 to AuthKit with signed state", async () => {
    const res = await worker.fetch(
      get("/?return_to=/briefing-v4/"),
      ENV,
      testCtx(),
    );
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    const url = new URL(loc);
    expect(url.origin).toBe("https://api.workos.com");
    expect(url.pathname).toBe("/user_management/authorize");
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
      testCtx(),
    );
    expect(res.status).toBe(302);
    // We can't see the returnTo inside the signed state from the
    // outside — but the behaviour is covered by state.test.ts's
    // isValidReturnTo suite + callback.test.ts's fallback test.
  });

  test("no return_to param still works", async () => {
    const res = await worker.fetch(get("/"), ENV, testCtx());
    expect(res.status).toBe(302);
  });
});

describe("GET /logout (MIL-161)", () => {
  // Pre-MIL-161 behaviour was: GET /logout → 302 + clear-cookie. That
  // contract is gone — GET now renders a confirm page; the cookie is
  // only cleared on POST. This closes the CSRF gap (an `<img src="/logout">`
  // embedded on any open-web page would have signed the user out).

  test("no cookie → 302 to cjipro.com (idempotent, MIL-149 cleanup)", async () => {
    const res = await worker.fetch(get("/logout"), ENV, testCtx());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://cjipro.com/");
    // No Set-Cookie on the cookie-less GET — there was nothing to clear.
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  test("with cookie → renders confirm form with CSRF token", async () => {
    const req = new Request("https://login.cjipro.com/logout", {
      method: "GET",
      headers: { cookie: "__Secure-cjipro-session=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1XzAxIn0.sig" },
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(200);
    expect(res.headers.get("set-cookie")).toBeNull(); // GET never clears
    const body = await res.text();
    expect(body).toContain("Sign out of CJI?");
    expect(body).toContain('method="POST"');
    expect(body).toContain('name="csrf"');
    expect(body).toContain("v1.");
  });

  // MIL-162 — explicit ← Back affordance on the confirm form so a user
  // who reached /logout by misclick (or `<img src="/logout">` rendering
  // a confirm page) has a labelled escape, not just a Cancel button
  // tucked next to Sign out.
  test("MIL-162: confirm page renders ← Back link to /portal", async () => {
    const req = new Request("https://login.cjipro.com/logout", {
      method: "GET",
      headers: { cookie: "__Secure-cjipro-session=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1XzAxIn0.sig" },
    });
    const res = await worker.fetch(req, ENV, testCtx());
    const body = await res.text();
    expect(body).toContain('class="back-link"');
    expect(body).toContain("&larr; Back");
  });
});

describe("POST /logout (MIL-161 + MIL-149 cleanup 2026-04-28)", () => {
  test("missing cookie → 302 to cjipro.com (idempotent, no lifecycle)", async () => {
    const req = new Request("https://login.cjipro.com/logout", {
      method: "POST",
      body: new URLSearchParams({ csrf: "v1.whatever" }),
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://cjipro.com/");
    // No cookie clear when there was no cookie to begin with.
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  test("missing CSRF token → 400 csrf-failed page", async () => {
    const req = new Request("https://login.cjipro.com/logout", {
      method: "POST",
      headers: { cookie: "__Secure-cjipro-session=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1XzAxIn0.sig" },
      body: new URLSearchParams({}),
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(400);
    const body = await res.text();
    expect(body).toContain("Couldn't complete sign out");
    // Cookie MUST NOT be cleared on CSRF failure — that would let a
    // bad CSRF attempt force-sign-out the user.
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  test("DELETE / PUT → 405 method-not-allowed", async () => {
    const req = new Request("https://login.cjipro.com/logout", {
      method: "DELETE",
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(405);
    expect(res.headers.get("allow")).toBe("GET, POST");
  });
});

describe("POST /logout direct redirect (MIL-149 cleanup 2026-04-28)", () => {
  // Replaces the MIL-161 v2 AuthKit front-channel hop. Rationale:
  //   • DIRECT_SIGNIN=true routes all sign-ins through Magic Auth API
  //     (server-to-server JSON), so AuthKit never sets a session
  //     cookie in the user agent. There's nothing for /api/logout to
  //     clear.
  //   • WorkOS's /api/logout silently drops return_to and falls back
  //     to a dashboard-configured Homepage URL with poor discoverability.
  //     Users who hit /logout were landing on error.workos.com instead
  //     of cjipro.com.
  //   • Owning the post-logout hop ourselves removes the dashboard
  //     dependency entirely.

  test("valid POST with sid → 302 to cjipro.com, cookie cleared, Clear-Site-Data set", async () => {
    const { buildCsrfToken } = await import("../src/logout");

    const b64url = (s: string) =>
      btoa(s).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
    const jwt = `${b64url('{"alg":"HS256"}')}.${b64url('{"sub":"u_01","sid":"sess_77"}')}.sig`;
    const csrf = await buildCsrfToken(jwt, ENV.STATE_SIGNING_KEY);

    const req = new Request("https://login.cjipro.com/logout", {
      method: "POST",
      headers: { cookie: `__Secure-cjipro-session=${jwt}` },
      body: new URLSearchParams({ csrf }),
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://cjipro.com/");

    // Cookie clear on the same response — bouncer denies on the next
    // request to any *.cjipro.com surface.
    const sc = res.headers.get("set-cookie");
    expect(sc).toContain("__Secure-cjipro-session=");
    expect(sc).toContain("Max-Age=0");

    // Defence-in-depth: cookies + storage only. No "cache" (would nuke
    // back-button + shared briefing URLs). No "executionContexts"
    // (kills any future BroadcastChannel('auth') sign-out fan-out).
    const csd = res.headers.get("clear-site-data") ?? "";
    expect(csd).toContain('"cookies"');
    expect(csd).toContain('"storage"');
    expect(csd).not.toContain("cache");
    expect(csd).not.toContain("executionContexts");

    // No AuthKit domain in the response chain — the front-channel hop
    // is gone.
    expect(res.headers.get("location")).not.toContain("authkit.app");
    expect(res.headers.get("location")).not.toContain("/api/logout");
  });

  test("valid POST without sid → same 302 (AuthKit hop removed entirely)", async () => {
    const { buildCsrfToken } = await import("../src/logout");
    const b64url = (s: string) =>
      btoa(s).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
    const jwt = `${b64url('{"alg":"HS256"}')}.${b64url('{"sub":"u_01"}')}.sig`;
    const csrf = await buildCsrfToken(jwt, ENV.STATE_SIGNING_KEY);

    const req = new Request("https://login.cjipro.com/logout", {
      method: "POST",
      headers: { cookie: `__Secure-cjipro-session=${jwt}` },
      body: new URLSearchParams({ csrf }),
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://cjipro.com/");
    expect(res.headers.get("location")).not.toContain("authkit.app");
  });
});

describe("GET /logout/done (MIL-161 + MIL-162 + MIL-149 cleanup)", () => {
  // 2026-04-28 — replaced the rendered "You're signed out" page with a
  // 302 to cjipro.com. The bare confirmation page on login.cjipro.com
  // was a dead-end terminal state; the public homepage is a better
  // landing for users who just signed out (and obviates the MIL-162
  // ← Back affordance — there's nothing to go back to). The audit row
  // still carries the lifecycle outcome.
  test("302 to cjipro.com homepage", async () => {
    const res = await worker.fetch(get("/logout/done"), ENV, testCtx());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://cjipro.com/");
  });

  test("does not Set-Cookie (the original POST already cleared it)", async () => {
    const res = await worker.fetch(get("/logout/done"), ENV, testCtx());
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  test("cache-control: no-store on the redirect", async () => {
    const res = await worker.fetch(get("/logout/done"), ENV, testCtx());
    expect(res.headers.get("cache-control")).toBe("no-store");
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
        testCtx(),
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
      testCtx(),
    );
    expect(res.status).toBe(400);
    expect(res.headers.get("content-type")).toContain("text/html");
    const body = await res.text();
    expect(body).toContain("Sign-in error");
  });

  test("missing params → 400", async () => {
    const res = await worker.fetch(get("/callback"), ENV, testCtx());
    expect(res.status).toBe(400);
  });
});

// MIL-83 — admin.cjipro.com host routing. The dashboard lives at
// root on this host; auth endpoints and other paths are scoped out.
// Admin gating still applies — without AUDIT_DB + JWKS env, the
// admin route returns the misconfigured-denied page (200 HTML), not
// a 404. That's the same behaviour login.cjipro.com/admin shows in
// these tests, which proves the host rewrite plumbed through.
describe("admin.cjipro.com host routing (MIL-83)", () => {
  function adminGet(path: string): Request {
    return new Request(`https://admin.cjipro.com${path}`);
  }

  test("GET / → routed to admin dashboard handler", async () => {
    // No AUDIT_DB binding in test ENV → admin gate denies with 403.
    // The status proves the request reached the gated handler (not
    // 404, not 405, not the public authorize redirect at 302).
    const res = await worker.fetch(adminGet("/"), ENV, testCtx());
    expect(res.status).toBe(403);
    expect(res.headers.get("content-type")).toContain("text/html");
  });

  test("GET /api/signups → routed to admin API handler", async () => {
    const res = await worker.fetch(adminGet("/api/signups"), ENV, testCtx());
    expect(res.status).toBe(403);
  });

  test("GET /admin still works on admin host (backwards-compat)", async () => {
    const res = await worker.fetch(adminGet("/admin"), ENV, testCtx());
    expect(res.status).toBe(403);
  });

  test("GET /healthz → 404 on admin host (auth endpoints scoped out)", async () => {
    const res = await worker.fetch(adminGet("/healthz"), ENV, testCtx());
    expect(res.status).toBe(404);
  });

  test("GET /callback → 404 on admin host", async () => {
    const res = await worker.fetch(adminGet("/callback?code=x&state=y"), ENV, testCtx());
    expect(res.status).toBe(404);
  });

  test("GET /logout → 404 on admin host", async () => {
    const res = await worker.fetch(adminGet("/logout"), ENV, testCtx());
    expect(res.status).toBe(404);
  });

  test("POST /webhooks/workos → 404 on admin host", async () => {
    const req = new Request("https://admin.cjipro.com/webhooks/workos", {
      method: "POST",
      body: "{}",
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(404);
  });

  test("GET /unknown-path → 404 on admin host", async () => {
    const res = await worker.fetch(adminGet("/totally-fake"), ENV, testCtx());
    expect(res.status).toBe(404);
  });

  test("login.cjipro.com /healthz still 200 (no host bleed-through)", async () => {
    const res = await worker.fetch(get("/healthz"), ENV, testCtx());
    expect(res.status).toBe(200);
  });

  // MIL-83 — confirms the no-session denied path on admin host emits an
  // ABSOLUTE Location to login.cjipro.com (not "/?return_to=/admin").
  // A relative location would loop: /  → path-rewrite to /admin →
  // no-session → 302 / → / rewrites to /admin → loop. This requires
  // the in-test admin gate to actually reach the no-session branch,
  // which means AUDIT_DB must be present in ENV. Without AUDIT_DB the
  // gate short-circuits at the misconfigured branch (covered above).
  // Skipped in this suite because stubbing AUDIT_DB requires plumbing
  // a fake D1 client; the renderDenied unit logic is exercised below.
  test("renderDenied no-session on admin host returns absolute login.cjipro.com URL", async () => {
    const { renderDenied } = await import("../src/admin_routes");
    const adminReq = new Request("https://admin.cjipro.com/anything");
    const res = renderDenied({ kind: "no-session" }, adminReq);
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://login.cjipro.com/?return_to=/admin",
    );
  });

  test("renderDenied no-session on login host stays relative", async () => {
    const { renderDenied } = await import("../src/admin_routes");
    const loginReq = new Request("https://login.cjipro.com/admin");
    const res = renderDenied({ kind: "no-session" }, loginReq);
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("/?return_to=/admin");
  });
});

// MIL-149 — direct WorkOS Magic Auth on login.cjipro.com.
// Smoke tests at the HTTP layer. The unit tests in sign_in.test.ts
// cover the WorkOS API integration with a fetchImpl stub; here we
// exercise the routes themselves end-to-end without touching the
// network (only the paths that don't make WorkOS calls — invalid
// email short-circuits, bad state short-circuits, GET-only renders).
describe("MIL-149 /sign-in/ routes", () => {
  test("GET /sign-in/ → 200 with email form", async () => {
    const res = await worker.fetch(get("/sign-in/"), ENV, testCtx());
    expect(res.status).toBe(200);
    const html = await res.text();
    expect(html).toContain("Sign in");
    expect(html).toContain('action="/sign-in/email"');
    expect(html).toContain('name="email"');
    expect(res.headers.get("content-type")).toContain("text/html");
  });

  test("GET /sign-in (no trailing slash) → 301 /sign-in/", async () => {
    const res = await worker.fetch(get("/sign-in"), ENV, testCtx());
    expect(res.status).toBe(301);
    expect(res.headers.get("location")).toBe("/sign-in/");
  });

  test("GET /sign-in/?return_to=/briefing-v4/ keeps return_to in form", async () => {
    const res = await worker.fetch(
      get("/sign-in/?return_to=/briefing-v4/"),
      ENV,
      testCtx(),
    );
    expect(res.status).toBe(200);
    const html = await res.text();
    expect(html).toContain('name="return_to"');
    expect(html).toContain('value="/briefing-v4/"');
  });

  test("GET /sign-in/?return_to=https://evil.example.com/ drops invalid return_to", async () => {
    const res = await worker.fetch(
      get("/sign-in/?return_to=https://evil.example.com/"),
      ENV,
      testCtx(),
    );
    expect(res.status).toBe(200);
    const html = await res.text();
    // No hidden return_to input rendered when the value is rejected.
    expect(html).not.toContain('name="return_to"');
    expect(html).not.toContain("evil.example.com");
  });

  test("POST /sign-in/email with malformed email → 400 + re-rendered form with error", async () => {
    const body = new URLSearchParams({ email: "not-an-email" }).toString();
    const req = new Request("https://login.cjipro.com/sign-in/email", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(400);
    const html = await res.text();
    // escapeHtml encodes the apostrophe in "doesn't" → "doesn&#39;t",
    // so assert on the apostrophe-free portion of the message.
    expect(html).toContain("look like a valid email");
    expect(html).toContain('id="email-err" role="alert"');
    expect(html).toContain('aria-invalid="true"');
    // Email value preserved in the field for re-entry.
    expect(html).toContain('value="not-an-email"');
  });

  test("POST /sign-in/code with garbage state → 400 expired page", async () => {
    const body = new URLSearchParams({
      code: "123456",
      state: "garbage-not-a-real-state-token",
    }).toString();
    const req = new Request("https://login.cjipro.com/sign-in/code", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    });
    const res = await worker.fetch(req, ENV, testCtx());
    expect(res.status).toBe(400);
    const html = await res.text();
    expect(html).toContain("Sign-in expired");
  });

  test("GET /sign-in/email → 404 (POST-only handler, falls through)", async () => {
    // The global method gate only 405s non-GET-non-POST methods;
    // GETs always pass through and fall to 404 if no matching path
    // handler exists. This mirrors how /request-access GETs reach
    // their renderer and /webhooks/workos GETs 404. Documenting it
    // here so a future "rationalise method handling" change knows
    // this was the intended behaviour, not an oversight.
    const res = await worker.fetch(get("/sign-in/email"), ENV, testCtx());
    expect(res.status).toBe(404);
  });

  test("DIRECT_SIGNIN=true: GET / 302s to /sign-in/ (not AuthKit)", async () => {
    const directEnv: Env = { ...ENV, DIRECT_SIGNIN: "true" };
    const res = await worker.fetch(
      get("/?return_to=/briefing-v4/"),
      directEnv,
      testCtx(),
    );
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    expect(loc.startsWith("/sign-in/")).toBe(true);
    expect(loc).toContain("return_to=");
    expect(loc).toContain(encodeURIComponent("/briefing-v4/"));
  });

  test("DIRECT_SIGNIN=false (default): GET / still 302s to AuthKit (no behaviour change)", async () => {
    // Same env as the existing GET / authorize test above. Asserting
    // explicitly here so a future flag flip can't silently regress
    // the AuthKit path while DIRECT_SIGNIN is off.
    const res = await worker.fetch(get("/"), ENV, testCtx());
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    expect(loc).toContain("api.workos.com/user_management/authorize");
  });

  test("DIRECT_SIGNIN=true with invalid return_to drops the param (no open redirect)", async () => {
    const directEnv: Env = { ...ENV, DIRECT_SIGNIN: "true" };
    const res = await worker.fetch(
      get("/?return_to=https://evil.example.com/"),
      directEnv,
      testCtx(),
    );
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    expect(loc).toBe("/sign-in/");
    expect(loc).not.toContain("evil.example.com");
  });
});
