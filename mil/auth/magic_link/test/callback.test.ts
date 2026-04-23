import { describe, expect, test } from "vitest";
import { handleCallback, type CallbackConfig } from "../src/callback";
import { signState } from "../src/state";

const CFG: CallbackConfig = {
  exchange: {
    clientId: "client_01KPY7CA07ZD1WG3DMQE1FZQE1",
    clientSecret: "sk_test_example_secret",
  },
  cookie: {
    name: "__Secure-cjipro-session",
    domain: ".cjipro.com",
    maxAgeSeconds: 3600,
  },
  stateSigningKey: "test-signing-key-0123456789abcdef",
  defaultReturnTo: "/",
};

function stubFetch(
  status: number,
  body: Record<string, unknown>,
): typeof fetch {
  return (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;
}

describe("handleCallback — happy path", () => {
  test("valid state + successful exchange yields 302 + Set-Cookie", async () => {
    const state = await signState(
      { returnTo: "/briefing-v4/", ts: Date.now() },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?code=abc&state=${encodeURIComponent(state)}`;
    const stub = stubFetch(200, {
      access_token: "eyJhbGc.token.sig",
      user: { id: "user_123" },
    });
    const out = await handleCallback(url, CFG, stub);
    expect(out.kind).toBe("redirect");
    if (out.kind === "redirect") {
      expect(out.location).toBe("/briefing-v4/");
      expect(out.setCookie).toContain("__Secure-cjipro-session=eyJhbGc.token.sig");
      expect(out.setCookie).toContain("Domain=.cjipro.com");
      expect(out.setCookie).toContain("HttpOnly");
    }
  });

  test("invalid return_to falls back to default", async () => {
    const state = await signState(
      { returnTo: "//evil.example.com/x", ts: Date.now() },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?code=abc&state=${encodeURIComponent(state)}`;
    const stub = stubFetch(200, { access_token: "tok" });
    const out = await handleCallback(url, CFG, stub);
    expect(out.kind).toBe("redirect");
    if (out.kind === "redirect") {
      expect(out.location).toBe(CFG.defaultReturnTo);
    }
  });
});

describe("handleCallback — failure modes", () => {
  test("missing code → 400", async () => {
    const state = await signState(
      { returnTo: "/", ts: Date.now() },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?state=${encodeURIComponent(state)}`;
    const out = await handleCallback(url, CFG);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      expect(out.status).toBe(400);
      expect(out.reason).toBe("missing-params");
    }
  });

  test("missing state → 400", async () => {
    const url = `https://login.cjipro.com/callback?code=abc`;
    const out = await handleCallback(url, CFG);
    expect(out.kind).toBe("error");
  });

  test("WorkOS returns ?error= → 400 with reason", async () => {
    const url =
      "https://login.cjipro.com/callback?error=access_denied&error_description=user%20cancelled";
    const out = await handleCallback(url, CFG);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      expect(out.reason).toBe("workos-error");
      expect(out.detail).toContain("access_denied");
    }
  });

  test("bad-signature state → 400", async () => {
    const url =
      "https://login.cjipro.com/callback?code=abc&state=not.a.valid.signed.state";
    const out = await handleCallback(url, CFG);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      // parser may classify as malformed or bad-signature depending
      // on where the random string fails — both are 400s
      expect(out.status).toBe(400);
    }
  });

  test("expired state → 400 expired", async () => {
    const state = await signState(
      { returnTo: "/", ts: Date.now() - 20 * 60 * 1000 },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?code=abc&state=${encodeURIComponent(state)}`;
    const out = await handleCallback(url, CFG);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      expect(out.reason).toBe("expired");
    }
  });

  test("WorkOS HTTP 400 on exchange → 502 with detail", async () => {
    const state = await signState(
      { returnTo: "/", ts: Date.now() },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?code=bad&state=${encodeURIComponent(state)}`;
    const stub = stubFetch(400, {
      error: "invalid_grant",
      error_description: "code already used",
    });
    const out = await handleCallback(url, CFG, stub);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      expect(out.status).toBe(502);
      expect(out.reason).toBe("http-error");
      expect(out.detail).toContain("code already used");
    }
  });

  test("exchange response missing access_token → 502", async () => {
    const state = await signState(
      { returnTo: "/", ts: Date.now() },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?code=ok&state=${encodeURIComponent(state)}`;
    const stub = stubFetch(200, { user: { id: "u1" } });
    const out = await handleCallback(url, CFG, stub);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      expect(out.reason).toBe("missing-access-token");
    }
  });

  test("network error on exchange → 502 network-error", async () => {
    const state = await signState(
      { returnTo: "/", ts: Date.now() },
      CFG.stateSigningKey,
    );
    const url = `https://login.cjipro.com/callback?code=ok&state=${encodeURIComponent(state)}`;
    const stub: typeof fetch = (async () => {
      throw new Error("connection reset");
    }) as typeof fetch;
    const out = await handleCallback(url, CFG, stub);
    expect(out.kind).toBe("error");
    if (out.kind === "error") {
      expect(out.reason).toBe("network-error");
      expect(out.detail).toContain("connection reset");
    }
  });
});
