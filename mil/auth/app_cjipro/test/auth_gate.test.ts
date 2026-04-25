// MIL-84 — auth gate tests. Mirrors edge-bouncer's approval_gate
// suite but adapted for the app_cjipro Worker which renders content
// instead of passing through to origin.

import { beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("../../edge_bouncer/src/session", async () => {
  const actual = await vi.importActual<
    typeof import("../../edge_bouncer/src/session")
  >("../../edge_bouncer/src/session");
  return {
    ...actual,
    verifySession: vi.fn(),
  };
});

import worker, { type Env } from "../src/index";
import { verifySession } from "../../edge_bouncer/src/session";

interface FakeUserRow {
  email: string;
}
interface FakeSessionRow {
  sub: string;
  email: string;
}

class FakeApprovalsDb {
  public approved: FakeUserRow[] = [];
  public sessions: FakeSessionRow[] = [];
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
    return [
      { results: [] as T[] },
      { results: [{ salt: "x".repeat(64) }] as T[] },
    ];
  }
}

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
    EXPECTED_ISS: "https://api.workos.com/user_management/client_x",
    LOGIN_URL: "https://login.cjipro.com/",
    RETURN_TO_PARAM: "return_to",
    JWKS_CACHE_TTL_SECONDS: "3600",
    PUBLIC_PATHS: "=/healthz,=/favicon.ico,=/robots.txt,=/.nojekyll",
    AUDIT_DB: db as unknown as D1Database,
  };
}

function req(path: string, cookie = ""): Request {
  const headers: Record<string, string> = {};
  if (cookie) headers["cookie"] = cookie;
  return new Request(`https://app.cjipro.com${path}`, { headers });
}

const COOKIE_WITH_TOKEN = "__Secure-cjipro-session=dummy.jwt.token";

beforeEach(() => {
  vi.mocked(verifySession).mockReset();
  vi.mocked(verifySession).mockImplementation(async (token) => {
    if (!token) return { kind: "missing" };
    throw new Error("test must set explicit mock for token-present case");
  });
});

describe("app_cjipro auth gate — enforce=true", () => {
  test("approved user → renders /reckoner page", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    db.sessions.push({ sub: "u_alpha", email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    const res = await worker.fetch(
      req("/reckoner", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(200);
    const body = await res.text();
    expect(body).toContain("Industry Pulse");
  });

  test("non-approved user → 403 access-pending page", async () => {
    const db = new FakeApprovalsDb();
    db.sessions.push({ sub: "u_bravo", email: "bravo@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo" },
    });
    const res = await worker.fetch(
      req("/reckoner", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(403);
    const body = await res.text();
    expect(body).toContain("Access pending");
  });

  test("missing cookie → 302 to login.cjipro.com", async () => {
    const db = new FakeApprovalsDb();
    const res = await worker.fetch(
      req("/reckoner"),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("login.cjipro.com");
    expect(res.headers.get("location")).toContain("return_to");
  });

  test("public /healthz bypasses auth", async () => {
    const db = new FakeApprovalsDb();
    const res = await worker.fetch(req("/healthz"), envWith(db, true), testCtx());
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
  });

  test("public /favicon.ico bypasses auth", async () => {
    const db = new FakeApprovalsDb();
    const res = await worker.fetch(
      req("/favicon.ico"),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(204);
  });

  test("AUDIT_DB absent → fail closed (deny)", async () => {
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    const env: Env = { ...envWith(new FakeApprovalsDb(), true) };
    delete env.AUDIT_DB;
    const res = await worker.fetch(
      req("/reckoner", COOKIE_WITH_TOKEN),
      env,
      testCtx(),
    );
    expect(res.status).toBe(403);
  });

  test("/ → 302 redirect to /reckoner (after auth pass)", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    db.sessions.push({ sub: "u_alpha", email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });
    const res = await worker.fetch(
      req("/", COOKIE_WITH_TOKEN),
      envWith(db, true),
      testCtx(),
    );
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("/reckoner");
  });
});

describe("app_cjipro auth gate — enforce=false (shadow mode)", () => {
  test("non-approved user still gets the page in shadow", async () => {
    const db = new FakeApprovalsDb();
    db.sessions.push({ sub: "u_bravo", email: "bravo@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo" },
    });
    const res = await worker.fetch(
      req("/reckoner", COOKIE_WITH_TOKEN),
      envWith(db, false),
      testCtx(),
    );
    // Shadow mode renders the surface even on a deny decision.
    expect(res.status).toBe(200);
    const body = await res.text();
    expect(body).toContain("Industry Pulse");
  });

  test("missing cookie still passes through to render in shadow", async () => {
    const db = new FakeApprovalsDb();
    const res = await worker.fetch(
      req("/reckoner"),
      envWith(db, false),
      testCtx(),
    );
    // Shadow mode does not redirect to login — we want to see real
    // traffic shape on the surfaces themselves before flipping enforce.
    expect(res.status).toBe(200);
  });
});
