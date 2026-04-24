// MIL-66a — unit tests for the approval gate inside decide().
//
// decide() is not exported; we exercise it via the default fetch
// handler and assert response status. We stub verifySession so we
// don't need a real WorkOS JWT — the gate logic downstream is what
// we care about here.

import { beforeEach, describe, expect, test, vi } from "vitest";

// Must mock BEFORE importing the worker module so the stub wins.
vi.mock("../src/session", async () => {
  const actual = await vi.importActual<typeof import("../src/session")>(
    "../src/session",
  );
  return {
    ...actual,
    verifySession: vi.fn(),
  };
});

import worker, { type Env } from "../src/index";
import { verifySession } from "../src/session";

interface FakeUserRow {
  email: string;
}

class FakeApprovalsDb {
  public approved: FakeUserRow[] = [];
  prepare(sql: string) {
    return new FakeStmt(this, sql, []);
  }
}

class FakeStmt {
  constructor(
    private db: FakeApprovalsDb,
    private sql: string,
    private args: unknown[],
  ) {}
  bind(...args: unknown[]) {
    return new FakeStmt(this.db, this.sql, args);
  }
  async first<T = unknown>() {
    const s = this.sql.trim();
    if (s.startsWith("SELECT 1 AS present FROM approved_users")) {
      const email = this.args[0] as string;
      return this.db.approved.find((u) => u.email === email)
        ? ({ present: 1 } as T)
        : null;
    }
    // Any SELECT / INSERT on auth_events is an audit-path call —
    // return the shape logAuthEvent expects so it doesn't blow up.
    if (s.startsWith("SELECT row_hash FROM auth_events")) return null;
    if (s.startsWith("INSERT OR IGNORE INTO audit_salts")) return null;
    if (s.startsWith("SELECT salt FROM audit_salts")) {
      return { salt: "x".repeat(64) } as T;
    }
    return null;
  }
  async all<T = unknown>() {
    return { results: [] as T[] };
  }
  async run() {
    return { results: [] };
  }
  async batch<T>(_: unknown[]) {
    return [{ results: [] as T[] }, { results: [{ salt: "x".repeat(64) }] as T[] }];
  }
}

// ThreadingHTTPServer... er, ExecutionContext stub.
function testCtx(): ExecutionContext {
  return {
    waitUntil(_: Promise<unknown>) {},
    passThroughOnException() {},
    props: {},
  } as unknown as ExecutionContext;
}

function envWith(db: FakeApprovalsDb, enforce: boolean): Env {
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
    AUDIT_DB: db as unknown as D1Database,
  };
}

function req(path: string, cookie = ""): Request {
  const headers: Record<string, string> = {};
  if (cookie) headers["cookie"] = cookie;
  return new Request(`https://cjipro.com${path}`, { headers });
}

const COOKIE_WITH_TOKEN = "__Secure-cjipro-session=dummy.jwt.token";

beforeEach(() => {
  vi.mocked(verifySession).mockReset();
  // Default: behave like the real module when no cookie present.
  vi.mocked(verifySession).mockImplementation(async (token) => {
    if (!token) return { kind: "missing" };
    throw new Error("test must set explicit mock for token-present case");
  });
});

describe("approval gate — enforce=true", () => {
  test("approved email → pass through to origin", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha", email: "alpha@example.com" },
    });
    // Stub global fetch so the "pass" path doesn't hit real origin.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/briefing-v4/", COOKIE_WITH_TOKEN),
        envWith(db, true),
        testCtx(),
      );
      expect(res.status).toBe(200);
      expect(await res.text()).toBe("origin");
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("non-approved email → 403 deny page", async () => {
    const db = new FakeApprovalsDb();
    // allowlist is empty — nobody is approved
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo", email: "bravo@example.com" },
    });
    const res = await worker.fetch(
      req("/briefing-v4/", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(403);
    const body = await res.text();
    expect(body).toContain("Access pending");
    expect(body).toContain("hello@cjipro.com");
  });

  test("case-insensitive email match", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha", email: "Alpha@Example.COM" },
    });
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/briefing-v4/", COOKIE_WITH_TOKEN),
        envWith(db, true),
        testCtx(),
      );
      expect(res.status).toBe(200);
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("missing email claim → deny (fail closed)", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" }, // no email claim
    });
    const res = await worker.fetch(
      req("/briefing-v4/", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(403);
  });

  test("public path bypasses approval check", async () => {
    const db = new FakeApprovalsDb();
    // Doesn't matter — approval check never runs on public paths.
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_nobody", email: "nobody@example.com" },
    });
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/"),
        envWith(db, true),
        testCtx(),
      );
      expect(res.status).toBe(200);
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("missing cookie → redirect to login (unchanged)", async () => {
    const db = new FakeApprovalsDb();
    // verifySession returns `missing` when cookie is absent
    const res = await worker.fetch(
      req("/briefing-v4/"),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("login.cjipro.com");
  });

  test("AUDIT_DB absent → deny (fail closed)", async () => {
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha", email: "alpha@example.com" },
    });
    const env: Env = { ...envWith(new FakeApprovalsDb(), true) };
    delete env.AUDIT_DB;
    const res = await worker.fetch(
      req("/briefing-v4/", COOKIE_WITH_TOKEN),
      env,
      testCtx(),
    );
    expect(res.status).toBe(403);
  });
});

describe("approval gate — enforce=false (shadow mode)", () => {
  test("non-approved email still passes through in shadow", async () => {
    const db = new FakeApprovalsDb(); // empty allowlist
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo", email: "bravo@example.com" },
    });
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/briefing-v4/", COOKIE_WITH_TOKEN),
        envWith(db, false),
        testCtx(),
      );
      // Shadow mode: decision was "deny" but we pass through to
      // origin so real traffic isn't blocked during rollout.
      expect(res.status).toBe(200);
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
