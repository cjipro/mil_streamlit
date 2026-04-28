// MIL-149 — direct WorkOS Magic Auth sign-in flow tests
//
// Three concerns:
//  1. State token roundtrip (sign + verify, including failure modes)
//  2. WorkOS API integration (sendMagicAuthCode + verifyMagicAuthCode)
//     with fetchImpl injection — no real network calls
//  3. Email-validation passthrough (delegated to approvals/signups)
//
// The Worker fetch handler integration (POST /sign-in/email →
// renderSignInCodeForm) is exercised in index.test.ts.

import { describe, expect, test } from "vitest";
import {
  isPlausibleEmail,
  sendMagicAuthCode,
  signSignInState,
  verifyMagicAuthCode,
  verifySignInState,
  type SignInState,
} from "../src/sign_in";

const SECRET = "mil149-test-key-32bytes-padding-blah-blah";

// ---- state token ---------------------------------------------------

describe("signSignInState / verifySignInState roundtrip", () => {
  const goodPayload: SignInState = {
    kind: "signin",
    email: "ada@example.com",
    returnTo: "https://app.cjipro.com/portal",
    ts: Date.now(),
  };

  test("valid signed state verifies and returns payload", async () => {
    const s = await signSignInState(goodPayload, SECRET);
    const r = await verifySignInState(s, SECRET);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload.email).toBe("ada@example.com");
      expect(r.payload.returnTo).toBe("https://app.cjipro.com/portal");
      expect(r.payload.kind).toBe("signin");
    }
  });

  test("wrong secret rejects with bad-signature", async () => {
    const s = await signSignInState(goodPayload, SECRET);
    const r = await verifySignInState(s, "different-secret");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("bad-signature");
  });

  test("malformed string rejects", async () => {
    const r = await verifySignInState("not-a-state-token", SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("malformed");
  });

  test("expired state rejects", async () => {
    const old: SignInState = { ...goodPayload, ts: Date.now() - 11 * 60_000 };
    const s = await signSignInState(old, SECRET);
    const r = await verifySignInState(s, SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("expired");
  });

  test("payload with wrong kind rejects (defends against state-type confusion)", async () => {
    // Sign a payload whose `kind` isn't "signin" — should be rejected
    // even though signature is valid. Prevents an attacker from
    // forging an OAuth-style state and replaying it through /sign-in/.
    const wrongKind = {
      kind: "oauth",
      email: "ada@example.com",
      returnTo: "/",
      ts: Date.now(),
    } as unknown as SignInState;
    const s = await signSignInState(wrongKind, SECRET);
    const r = await verifySignInState(s, SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("malformed");
  });

  test("tampered body fails signature check", async () => {
    const s = await signSignInState(goodPayload, SECRET);
    const [, sig] = s.split(".");
    const evilBody = btoa(
      JSON.stringify({
        kind: "signin",
        email: "attacker@example.com",
        returnTo: "https://app.cjipro.com/portal",
        ts: Date.now(),
      }),
    )
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
    const tampered = `${evilBody}.${sig}`;
    const r = await verifySignInState(tampered, SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("bad-signature");
  });
});

// ---- email validation -----------------------------------------------

describe("isPlausibleEmail (re-exported from approvals/signups)", () => {
  test("accepts plausible email", () => {
    expect(isPlausibleEmail("ada@example.com")).toBe(true);
  });
  test("rejects empty string", () => {
    expect(isPlausibleEmail("")).toBe(false);
  });
  test("rejects no @", () => {
    expect(isPlausibleEmail("ada-at-example.com")).toBe(false);
  });
});

// ---- sendMagicAuthCode ---------------------------------------------

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("sendMagicAuthCode", () => {
  test("invalid email short-circuits before network call", async () => {
    let called = false;
    const fakeFetch: typeof fetch = async () => {
      called = true;
      return jsonResponse(200, { id: "magic_auth_x" });
    };
    const r = await sendMagicAuthCode("not-an-email", "key", fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("invalid-email");
    expect(called).toBe(false);
  });

  test("2xx returns ok and uses Bearer auth + JSON body", async () => {
    let capturedUrl = "";
    let capturedAuth = "";
    let capturedBody = "";
    const fakeFetch: typeof fetch = async (input, init) => {
      capturedUrl = typeof input === "string" ? input : (input as URL).toString();
      capturedAuth = (init?.headers as Record<string, string>)?.authorization ?? "";
      capturedBody = (init?.body as string) ?? "";
      return jsonResponse(200, { id: "magic_auth_xyz" });
    };
    const r = await sendMagicAuthCode(
      "ada@example.com",
      "sk_test_123",
      fakeFetch,
    );
    expect(r.ok).toBe(true);
    expect(capturedUrl).toContain("/user_management/magic_auth/send");
    expect(capturedAuth).toBe("Bearer sk_test_123");
    expect(JSON.parse(capturedBody)).toEqual({ email: "ada@example.com" });
  });

  test("4xx returns http-error with detail extracted from error_description", async () => {
    const fakeFetch: typeof fetch = async () =>
      jsonResponse(400, { error_description: "rate limit" });
    const r = await sendMagicAuthCode(
      "ada@example.com",
      "sk_test_x",
      fakeFetch,
    );
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe("http-error");
      expect(r.status).toBe(400);
      expect(r.detail).toBe("rate limit");
    }
  });

  test("network error returns network-error", async () => {
    const fakeFetch: typeof fetch = async () => {
      throw new Error("DNS failure");
    };
    const r = await sendMagicAuthCode(
      "ada@example.com",
      "sk_test_x",
      fakeFetch,
    );
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe("network-error");
      expect(r.detail).toContain("DNS failure");
    }
  });
});

// ---- verifyMagicAuthCode --------------------------------------------

describe("verifyMagicAuthCode", () => {
  const cfg = { clientId: "client_test", clientSecret: "sk_test" };

  test("2xx returns access token + user fields", async () => {
    let capturedUrl = "";
    let capturedBody = "";
    const fakeFetch: typeof fetch = async (input, init) => {
      capturedUrl = typeof input === "string" ? input : (input as URL).toString();
      capturedBody = (init?.body as string) ?? "";
      return jsonResponse(200, {
        access_token: "jwt.eyJ.signature",
        user: {
          id: "user_01ABC",
          email: "ada@example.com",
          organization_id: "org_01XYZ",
        },
      });
    };
    const r = await verifyMagicAuthCode(
      "ada@example.com",
      "123456",
      cfg,
      fakeFetch,
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.accessToken).toBe("jwt.eyJ.signature");
      expect(r.userId).toBe("user_01ABC");
      expect(r.userEmail).toBe("ada@example.com");
      expect(r.organizationId).toBe("org_01XYZ");
    }
    expect(capturedUrl).toContain("/user_management/authenticate");
    const parsed = JSON.parse(capturedBody);
    expect(parsed.grant_type).toBe(
      "urn:workos:oauth:grant-type:magic-auth:code",
    );
    expect(parsed.code).toBe("123456");
    expect(parsed.email).toBe("ada@example.com");
    expect(parsed.client_id).toBe("client_test");
    expect(parsed.client_secret).toBe("sk_test");
  });

  test("organization_id at top-level body is also captured", async () => {
    const fakeFetch: typeof fetch = async () =>
      jsonResponse(200, {
        access_token: "jwt",
        user: { id: "u", email: "a@b.c" },
        organization_id: "org_top_level",
      });
    const r = await verifyMagicAuthCode("a@b.c", "1", cfg, fakeFetch);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.organizationId).toBe("org_top_level");
  });

  test("401 maps to invalid-code (user-fixable)", async () => {
    const fakeFetch: typeof fetch = async () =>
      jsonResponse(401, {
        code: "invalid_credentials",
        error_description: "Code expired or already used",
      });
    const r = await verifyMagicAuthCode("a@b.c", "999999", cfg, fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe("invalid-code");
      expect(r.status).toBe(401);
    }
  });

  test("422 with authentication_failed code maps to invalid-code", async () => {
    const fakeFetch: typeof fetch = async () =>
      jsonResponse(422, {
        code: "authentication_failed",
        error_description: "Bad code",
      });
    const r = await verifyMagicAuthCode("a@b.c", "111111", cfg, fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("invalid-code");
  });

  test("500 stays as http-error (not user-fixable)", async () => {
    const fakeFetch: typeof fetch = async () =>
      jsonResponse(500, { error: "internal" });
    const r = await verifyMagicAuthCode("a@b.c", "111111", cfg, fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe("http-error");
      expect(r.status).toBe(500);
    }
  });

  test("missing access_token in 2xx body returns missing-access-token", async () => {
    const fakeFetch: typeof fetch = async () =>
      jsonResponse(200, { user: { id: "u" } });
    const r = await verifyMagicAuthCode("a@b.c", "1", cfg, fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("missing-access-token");
  });

  test("non-JSON body returns http-error", async () => {
    const fakeFetch: typeof fetch = async () =>
      new Response("<html>oops</html>", {
        status: 502,
        headers: { "content-type": "text/html" },
      });
    const r = await verifyMagicAuthCode("a@b.c", "1", cfg, fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe("http-error");
      expect(r.detail).toContain("non-JSON body");
    }
  });

  test("network error returns network-error", async () => {
    const fakeFetch: typeof fetch = async () => {
      throw new Error("connect ETIMEDOUT");
    };
    const r = await verifyMagicAuthCode("a@b.c", "1", cfg, fakeFetch);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("network-error");
  });
});
