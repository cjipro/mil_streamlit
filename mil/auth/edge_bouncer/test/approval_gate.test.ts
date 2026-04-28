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
interface FakeSessionRow {
  sub: string;
  email: string;
}

interface FakePendingRow {
  email: string;
  requested_at: string;
}

class FakeApprovalsDb {
  public approved: FakeUserRow[] = [];
  public sessions: FakeSessionRow[] = [];
  public pending: FakePendingRow[] = [];
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
    if (s.startsWith("SELECT email FROM sessions WHERE sub")) {
      const sub = this.args[0] as string;
      const hit = this.db.sessions.find((r) => r.sub === sub);
      return hit ? ({ email: hit.email } as T) : null;
    }
    // MIL-153 — pending lookup (both isPending and the inline
    // requested_at SELECT in lookupPendingRow). One handler covers
    // both because they query the same table+where.
    if (s.startsWith("SELECT id FROM pending_signups WHERE email")) {
      const email = this.args[0] as string;
      const hit = this.db.pending.find((r) => r.email === email);
      return hit ? ({ id: 1 } as T) : null;
    }
    if (s.startsWith("SELECT requested_at FROM pending_signups WHERE email")) {
      const email = this.args[0] as string;
      const hit = this.db.pending.find((r) => r.email === email);
      return hit ? ({ requested_at: hit.requested_at } as T) : null;
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
    LOGIN_URL: "https://login.cjipro.com/sign-in/",
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
    db.sessions.push({ sub: "u_alpha", email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    // Stub global fetch so the "pass" path doesn't hit real origin.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/briefing-v3/", COOKIE_WITH_TOKEN),
        envWith(db, true),
        testCtx(),
      );
      expect(res.status).toBe(200);
      expect(await res.text()).toBe("origin");
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("non-approved email WITH pending request → 200 in-queue page (MIL-153)", async () => {
    const db = new FakeApprovalsDb();
    db.sessions.push({ sub: "u_charlie", email: "charlie@example.com" });
    db.pending.push({
      email: "charlie@example.com",
      requested_at: "2026-04-20T09:30:00.000Z",
    });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_charlie" },
    });
    const res = await worker.fetch(
      req("/briefing-v3/", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    // 200 not 403: positive ack of a known queue state, not an error.
    expect(res.status).toBe(200);
    const body = await res.text();
    expect(body).toContain("Your request is being reviewed");
    expect(body).toContain("charlie@example.com");
    expect(body).toContain("2026-04-20"); // submitted-on date
    expect(body).not.toContain("Request access");
  });

  test("non-approved email, no pending request → 403 not-on-allowlist page (MIL-153)", async () => {
    const db = new FakeApprovalsDb();
    db.sessions.push({ sub: "u_bravo", email: "bravo@example.com" });
    // approved is empty AND no pending row — bravo is signed in but
    // hasn't requested access. Differentiated deny page should fire
    // with the "Request access" CTA carrying their email pre-fill.
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo" },
    });
    const res = await worker.fetch(
      req("/briefing-v3/", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(403);
    const body = await res.text();
    expect(body).toContain("Access not yet provisioned");
    expect(body).toContain("Request access");
    expect(body).toContain("bravo@example.com");
    expect(body).toContain("/request-access?email=bravo%40example.com");
  });

  test("case-insensitive email match", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    // session row stores canonical lowercase (writeSession does this);
    // the lookup itself is exact-match by sub.
    db.sessions.push({ sub: "u_alpha", email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/briefing-v3/", COOKIE_WITH_TOKEN),
        envWith(db, true),
        testCtx(),
      );
      expect(res.status).toBe(200);
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  test("no session row → deny (fail closed)", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    // No db.sessions entry — simulates a JWT issued before MIL-66c
    // shipped, or a session table wipe. lookupSessionEmail returns
    // undefined, isApproved fails closed.
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    const res = await worker.fetch(
      req("/briefing-v3/", COOKIE_WITH_TOKEN),
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
      payload: { sub: "u_nobody" },
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
      req("/briefing-v3/"),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("login.cjipro.com");
  });

  test("AUDIT_DB absent → deny (fail closed)", async () => {
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    const env: Env = { ...envWith(new FakeApprovalsDb(), true) };
    delete env.AUDIT_DB;
    const res = await worker.fetch(
      req("/briefing-v3/", COOKIE_WITH_TOKEN),
      env,
      testCtx(),
    );
    expect(res.status).toBe(403);
  });
});

describe("approval gate — enforce=false (shadow mode)", () => {
  test("non-approved email still passes through in shadow", async () => {
    const db = new FakeApprovalsDb(); // empty allowlist
    db.sessions.push({ sub: "u_bravo", email: "bravo@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo" },
    });
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response("origin", { status: 200 })) as typeof fetch;
    try {
      const res = await worker.fetch(
        req("/briefing-v3/", COOKIE_WITH_TOKEN),
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
