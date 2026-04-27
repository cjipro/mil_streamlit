// MIL-161 — sign-out lifecycle tests.
//
// Covers:
//   - JWT sid extraction
//   - CSRF token build + verify (constant-time, version pinned)
//   - WorkOS revoke success / 404 / http-error / network-error paths
//   - performLogout orchestration (each step independently failable)
//   - Audit detail JSON shape

import { describe, expect, test } from "vitest";
import {
  buildAuthkitLogoutUrl,
  buildCsrfToken,
  extractJwtSid,
  outcomeToAuditDetail,
  performLogout,
  revokeWorkosSession,
  verifyCsrfToken,
  type LogoutOutcome,
} from "../src/logout";

// ── Helper: forge a JWT with a chosen payload ──────────────────────

function b64url(s: string): string {
  return btoa(s).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function makeJwt(claims: Record<string, unknown>): string {
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = b64url(JSON.stringify(claims));
  // Signature is opaque for our purposes — extractJwt* never verifies.
  return `${header}.${payload}.fake-signature`;
}

// ── extractJwtSid ──────────────────────────────────────────────────

describe("extractJwtSid", () => {
  test("returns sid claim when present", () => {
    const jwt = makeJwt({ sub: "user_01", sid: "session_xyz" });
    expect(extractJwtSid(jwt)).toBe("session_xyz");
  });

  test("returns undefined when sid claim is absent", () => {
    const jwt = makeJwt({ sub: "user_01" });
    expect(extractJwtSid(jwt)).toBeUndefined();
  });

  test("returns undefined when sid claim is non-string", () => {
    const jwt = makeJwt({ sub: "user_01", sid: 12345 });
    expect(extractJwtSid(jwt)).toBeUndefined();
  });

  test("returns undefined on malformed JWT (no dots)", () => {
    expect(extractJwtSid("not-a-jwt")).toBeUndefined();
  });

  test("returns undefined on bad base64 in payload", () => {
    expect(extractJwtSid("aaa.!!!.bbb")).toBeUndefined();
  });
});

// ── CSRF tokens ────────────────────────────────────────────────────

describe("CSRF tokens", () => {
  const KEY = "secret-signing-key-for-tests";
  const JWT = makeJwt({ sub: "user_01", sid: "s1" });

  test("buildCsrfToken returns a versioned, opaque string", async () => {
    const token = await buildCsrfToken(JWT, KEY);
    expect(token.startsWith("v1.")).toBe(true);
    expect(token.length).toBeGreaterThan(10);
  });

  test("verifyCsrfToken accepts the matching token", async () => {
    const token = await buildCsrfToken(JWT, KEY);
    expect(await verifyCsrfToken(token, JWT, KEY)).toBe(true);
  });

  test("verifyCsrfToken rejects a token built for a different JWT", async () => {
    const t1 = await buildCsrfToken(JWT, KEY);
    const otherJwt = makeJwt({ sub: "attacker", sid: "s9" });
    expect(await verifyCsrfToken(t1, otherJwt, KEY)).toBe(false);
  });

  test("verifyCsrfToken rejects when signing key differs", async () => {
    const token = await buildCsrfToken(JWT, KEY);
    expect(await verifyCsrfToken(token, JWT, "different-key")).toBe(false);
  });

  test("verifyCsrfToken rejects null/empty token", async () => {
    expect(await verifyCsrfToken(null, JWT, KEY)).toBe(false);
    expect(await verifyCsrfToken("", JWT, KEY)).toBe(false);
    expect(await verifyCsrfToken(undefined, JWT, KEY)).toBe(false);
  });

  test("verifyCsrfToken rejects token without version prefix", async () => {
    expect(await verifyCsrfToken("nope", JWT, KEY)).toBe(false);
    expect(await verifyCsrfToken("v9.somesig", JWT, KEY)).toBe(false);
  });
});

// ── WorkOS revoke ──────────────────────────────────────────────────

describe("revokeWorkosSession", () => {
  test("200 OK → ok", async () => {
    const fetcher = (async () =>
      new Response("", { status: 200 })) as unknown as typeof fetch;
    const result = await revokeWorkosSession("sid_01", "sk_test", fetcher);
    expect(result.kind).toBe("ok");
  });

  test("204 No Content → ok", async () => {
    const fetcher = (async () =>
      new Response(null, { status: 204 })) as unknown as typeof fetch;
    const result = await revokeWorkosSession("sid_01", "sk_test", fetcher);
    expect(result.kind).toBe("ok");
  });

  test("404 (already gone) → ok", async () => {
    const fetcher = (async () =>
      new Response("not found", { status: 404 })) as unknown as typeof fetch;
    const result = await revokeWorkosSession("sid_01", "sk_test", fetcher);
    expect(result.kind).toBe("ok");
  });

  test("500 → error with body in detail", async () => {
    const fetcher = (async () =>
      new Response("server err", { status: 500 })) as unknown as typeof fetch;
    const result = await revokeWorkosSession("sid_01", "sk_test", fetcher);
    expect(result.kind).toBe("error");
    if (result.kind === "error") {
      expect(result.detail).toContain("http_500");
      expect(result.detail).toContain("server err");
    }
  });

  test("network throw → error with network: prefix", async () => {
    const fetcher = (async () => {
      throw new Error("connect ETIMEDOUT");
    }) as unknown as typeof fetch;
    const result = await revokeWorkosSession("sid_01", "sk_test", fetcher);
    expect(result.kind).toBe("error");
    if (result.kind === "error") {
      expect(result.detail).toContain("network:");
      expect(result.detail).toContain("ETIMEDOUT");
    }
  });

  test("URL-encodes the sid (hardens against path traversal)", async () => {
    let calledUrl = "";
    const fetcher = (async (url: string) => {
      calledUrl = url;
      return new Response("", { status: 200 });
    }) as unknown as typeof fetch;
    await revokeWorkosSession("../../etc/passwd", "sk_test", fetcher);
    // encodeURIComponent leaves `..` and `.` alone but escapes `/` to
    // %2F. That alone defangs path traversal — every separator becomes
    // an opaque path-segment character, so the whole sid lands as a
    // single path component between /sessions/ and /revoke.
    expect(calledUrl).toContain("..%2F..%2F");
    expect(calledUrl).not.toContain("/etc/passwd/");
    expect(calledUrl).toContain("/sessions/");
    expect(calledUrl.endsWith("/revoke")).toBe(true);
  });

  test("Bearer header carries the API key", async () => {
    let calledInit: RequestInit | undefined;
    const fetcher = (async (_url: string, init?: RequestInit) => {
      calledInit = init;
      return new Response("", { status: 200 });
    }) as unknown as typeof fetch;
    await revokeWorkosSession("sid_01", "sk_secret_value", fetcher);
    expect(calledInit?.method).toBe("POST");
    const headers = calledInit?.headers as Record<string, string>;
    expect(headers.authorization).toBe("Bearer sk_secret_value");
  });
});

// ── performLogout orchestration ────────────────────────────────────

function fakeDb(opts: {
  changes?: number;
  throws?: boolean;
} = {}): D1Database {
  return {
    prepare: () => ({
      bind: () => ({
        run: async () => {
          if (opts.throws) throw new Error("db down");
          return { meta: { changes: opts.changes ?? 1 } };
        },
      }),
    }),
  } as unknown as D1Database;
}

describe("performLogout", () => {
  test("no JWT → all-skipped outcome, cookie_cleared still true", async () => {
    const outcome = await performLogout(undefined, {
      db: fakeDb(),
      workosApiKey: "sk_test",
    });
    expect(outcome.cookie_cleared).toBe(true);
    expect(outcome.sessions_row_deleted).toBe("skipped");
    expect(outcome.workos_session_revoked).toBe("skipped");
  });

  test("happy path: row deleted + WorkOS revoked", async () => {
    const fetcher = (async () =>
      new Response(null, { status: 204 })) as unknown as typeof fetch;
    const jwt = makeJwt({ sub: "user_01", sid: "s_99" });
    const outcome = await performLogout(jwt, {
      db: fakeDb({ changes: 1 }),
      workosApiKey: "sk_test",
      fetcher,
    });
    expect(outcome.sessions_row_deleted).toBe("deleted");
    expect(outcome.workos_session_revoked).toBe("revoked");
    expect(outcome.cookie_cleared).toBe(true);
    expect(outcome.sessions_row_error).toBeNull();
    expect(outcome.workos_revoke_error).toBeNull();
  });

  test("D1 row already gone → not-found, NOT error", async () => {
    const fetcher = (async () =>
      new Response(null, { status: 204 })) as unknown as typeof fetch;
    const jwt = makeJwt({ sub: "user_01", sid: "s_99" });
    const outcome = await performLogout(jwt, {
      db: fakeDb({ changes: 0 }),
      workosApiKey: "sk_test",
      fetcher,
    });
    expect(outcome.sessions_row_deleted).toBe("not-found");
    expect(outcome.workos_session_revoked).toBe("revoked");
  });

  test("D1 throw → error captured, lifecycle continues to WorkOS", async () => {
    const fetcher = (async () =>
      new Response(null, { status: 204 })) as unknown as typeof fetch;
    const jwt = makeJwt({ sub: "user_01", sid: "s_99" });
    const outcome = await performLogout(jwt, {
      db: fakeDb({ throws: true }),
      workosApiKey: "sk_test",
      fetcher,
    });
    expect(outcome.sessions_row_deleted).toBe("error");
    expect(outcome.sessions_row_error).toContain("db down");
    // WorkOS revoke STILL runs even though D1 failed — defense in depth.
    expect(outcome.workos_session_revoked).toBe("revoked");
  });

  test("WorkOS down → error captured, cookie_cleared still true", async () => {
    const fetcher = (async () =>
      new Response("oops", { status: 503 })) as unknown as typeof fetch;
    const jwt = makeJwt({ sub: "user_01", sid: "s_99" });
    const outcome = await performLogout(jwt, {
      db: fakeDb({ changes: 1 }),
      workosApiKey: "sk_test",
      fetcher,
    });
    expect(outcome.sessions_row_deleted).toBe("deleted");
    expect(outcome.workos_session_revoked).toBe("error");
    expect(outcome.workos_revoke_error).toContain("http_503");
    expect(outcome.cookie_cleared).toBe(true);
  });

  test("missing sid claim → WorkOS revoke skipped (not an error)", async () => {
    const jwt = makeJwt({ sub: "user_01" }); // no sid
    const outcome = await performLogout(jwt, {
      db: fakeDb({ changes: 1 }),
      workosApiKey: "sk_test",
    });
    expect(outcome.sessions_row_deleted).toBe("deleted");
    expect(outcome.workos_session_revoked).toBe("skipped");
  });

  test("missing AUDIT_DB binding → sessions delete skipped", async () => {
    const fetcher = (async () =>
      new Response(null, { status: 204 })) as unknown as typeof fetch;
    const jwt = makeJwt({ sub: "user_01", sid: "s_99" });
    const outcome = await performLogout(jwt, {
      db: undefined,
      workosApiKey: "sk_test",
      fetcher,
    });
    expect(outcome.sessions_row_deleted).toBe("skipped");
    expect(outcome.workos_session_revoked).toBe("revoked");
  });

  test("missing WORKOS_CLIENT_SECRET → revoke skipped", async () => {
    const jwt = makeJwt({ sub: "user_01", sid: "s_99" });
    const outcome = await performLogout(jwt, {
      db: fakeDb({ changes: 1 }),
      workosApiKey: undefined,
    });
    expect(outcome.sessions_row_deleted).toBe("deleted");
    expect(outcome.workos_session_revoked).toBe("skipped");
  });
});

// ── AuthKit front-channel logout URL ───────────────────────────────

describe("buildAuthkitLogoutUrl", () => {
  test("builds full URL with sid + return_to on the AuthKit domain", () => {
    const url = buildAuthkitLogoutUrl(
      "ideal-log-65-staging.authkit.app",
      "session_01ABC",
      "https://login.cjipro.com/logout/done",
    );
    expect(url).not.toBeNull();
    expect(url).toContain("https://ideal-log-65-staging.authkit.app/");
    expect(url).toContain("/user_management/sessions/logout");
    expect(url).toContain("session_id=session_01ABC");
    expect(url).toContain(
      "return_to=https%3A%2F%2Flogin.cjipro.com%2Flogout%2Fdone",
    );
  });

  test("strips https:// prefix if env value carries one (defensive)", () => {
    const url = buildAuthkitLogoutUrl(
      "https://ideal-log-65-staging.authkit.app",
      "session_01ABC",
      "https://login.cjipro.com/logout/done",
    );
    expect(url).not.toContain("https://https://");
    expect(url?.startsWith("https://ideal-log-65-staging.authkit.app/")).toBe(true);
  });

  test("strips trailing slash if env value carries one (defensive)", () => {
    const url = buildAuthkitLogoutUrl(
      "ideal-log-65-staging.authkit.app/",
      "session_01ABC",
      "https://login.cjipro.com/logout/done",
    );
    expect(url).not.toContain(".app//");
  });

  test("omits session_id when sid is undefined (still useful — clears any cookie AuthKit finds)", () => {
    const url = buildAuthkitLogoutUrl(
      "ideal-log-65-staging.authkit.app",
      undefined,
      "https://login.cjipro.com/logout/done",
    );
    expect(url).not.toBeNull();
    expect(url).not.toContain("session_id");
    expect(url).toContain("return_to=");
  });

  test("returns null when authKitHost is missing (caller falls back to direct render)", () => {
    expect(
      buildAuthkitLogoutUrl(undefined, "sid_01", "https://x/done"),
    ).toBeNull();
    expect(
      buildAuthkitLogoutUrl("", "sid_01", "https://x/done"),
    ).toBeNull();
  });
});

// ── Audit detail JSON ──────────────────────────────────────────────

describe("outcomeToAuditDetail", () => {
  test("compact JSON with stable key order", () => {
    const o: LogoutOutcome = {
      sessions_row_deleted: "deleted",
      sessions_row_error: null,
      workos_session_revoked: "revoked",
      workos_revoke_error: null,
      cookie_cleared: true,
    };
    const detail = outcomeToAuditDetail(o);
    expect(detail).toBe(
      '{"s":"deleted","s_err":null,"w":"revoked","w_err":null,"c":true}',
    );
  });

  test("error detail captured verbatim", () => {
    const o: LogoutOutcome = {
      sessions_row_deleted: "error",
      sessions_row_error: "db down",
      workos_session_revoked: "error",
      workos_revoke_error: "http_503: oops",
      cookie_cleared: true,
    };
    const detail = outcomeToAuditDetail(o);
    expect(detail).toContain('"s":"error"');
    expect(detail).toContain('"s_err":"db down"');
    expect(detail).toContain('"w_err":"http_503: oops"');
  });
});
