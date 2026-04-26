// MIL-93 Phase B — /api/ask reverse-proxy tests
//
// Two layers exercised here:
//   1. apiAskHandler (unit) — body forwarding, header rewriting, method
//      check, upstream error surfacing.
//   2. Worker fetch() integration — page ENFORCE / API_ENFORCE separation,
//      JSON 401 (not 302) on auth fail for /api/* paths.

import { beforeEach, describe, expect, test, vi } from "vitest";

import { apiAskHandler, type ApiAskEnv } from "../src/api_ask";

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

// ── apiAskHandler unit tests ─────────────────────────────────────────────

function postReq(
  body: object | string,
  headers: Record<string, string> = {},
): Request {
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  return new Request("https://app.cjipro.com/api/ask", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...headers,
    },
    body: payload,
  });
}

const ENV_OK: ApiAskEnv = {
  ASK_BACKEND_URL: "https://chat-backend.example/api/ask",
  ASK_BACKEND_SCOPE: "reckoner",
};

describe("apiAskHandler — unit", () => {
  test("POST happy path forwards body + injects X-CJI-Scope", async () => {
    let upstreamUrl = "";
    let upstreamHeaders: Headers | null = null;
    let upstreamBody = "";
    const fetcher = (async (url: string, init: RequestInit) => {
      upstreamUrl = url;
      upstreamHeaders = init.headers as Headers;
      upstreamBody = await new Response(init.body).text();
      return new Response(JSON.stringify({ answer: "test answer" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;

    const res = await apiAskHandler(
      postReq({ query: "what's happening with login failures across the cohort" }),
      ENV_OK,
      { email: "alpha@example.com" },
      fetcher,
    );

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toEqual({ answer: "test answer" });
    expect(upstreamUrl).toBe("https://chat-backend.example/api/ask");
    expect(upstreamHeaders!.get("X-CJI-Scope")).toBe("reckoner");
    expect(upstreamHeaders!.get("Cf-Access-Authenticated-User-Email")).toBe(
      "alpha@example.com",
    );
    expect(upstreamBody).toContain("login failures");
  });

  test("strips Cookie + Host before forwarding", async () => {
    let upstreamHeaders: Headers | null = null;
    const fetcher = (async (_url: string, init: RequestInit) => {
      upstreamHeaders = init.headers as Headers;
      return new Response("{}", { status: 200 });
    }) as typeof fetch;

    const req = postReq(
      { query: "x" },
      { cookie: "__Secure-cjipro-session=abc.def.ghi", host: "app.cjipro.com" },
    );
    await apiAskHandler(req, ENV_OK, {}, fetcher);
    expect(upstreamHeaders!.get("cookie")).toBeNull();
    expect(upstreamHeaders!.get("host")).toBeNull();
  });

  test("any non-POST method returns 405", async () => {
    const req = new Request("https://app.cjipro.com/api/ask", { method: "GET" });
    const fetcher = vi.fn() as unknown as typeof fetch;
    const res = await apiAskHandler(req, ENV_OK, {}, fetcher);
    expect(res.status).toBe(405);
    expect(res.headers.get("allow")).toBe("POST");
    expect(fetcher).not.toHaveBeenCalled();
  });

  test("missing ASK_BACKEND_URL returns 500 backend_unconfigured", async () => {
    const env: ApiAskEnv = { ASK_BACKEND_URL: "", ASK_BACKEND_SCOPE: "reckoner" };
    const fetcher = vi.fn() as unknown as typeof fetch;
    const res = await apiAskHandler(postReq({ query: "x" }), env, {}, fetcher);
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body).toMatchObject({ error: "backend_unconfigured" });
  });

  test("upstream throw surfaces as 502 backend_unreachable", async () => {
    const fetcher = (async () => {
      throw new Error("ECONNREFUSED");
    }) as typeof fetch;
    const res = await apiAskHandler(postReq({ query: "x" }), ENV_OK, {}, fetcher);
    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string; detail: string };
    expect(body.error).toBe("backend_unreachable");
    expect(body.detail).toContain("ECONNREFUSED");
  });

  test("upstream 5xx body passes through unchanged", async () => {
    const fetcher = (async () => {
      return new Response(JSON.stringify({ error: "synthesis_failed" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;
    const res = await apiAskHandler(postReq({ query: "x" }), ENV_OK, {}, fetcher);
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body).toEqual({ error: "synthesis_failed" });
  });

  test("client-supplied X-CJI-Scope is overridden by env", async () => {
    let upstreamHeaders: Headers | null = null;
    const fetcher = (async (_url: string, init: RequestInit) => {
      upstreamHeaders = init.headers as Headers;
      return new Response("{}", { status: 200 });
    }) as typeof fetch;
    const req = postReq({ query: "x" }, { "x-cji-scope": "sonar" });
    await apiAskHandler(req, ENV_OK, {}, fetcher);
    // env wins — caller can't elevate scope by spoofing header.
    expect(upstreamHeaders!.get("X-CJI-Scope")).toBe("reckoner");
  });
});

// ── Worker integration: API_ENFORCE separation ───────────────────────────

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

function envWith(
  db: FakeApprovalsDb,
  pageEnforce: boolean,
  apiEnforce: boolean,
): Env {
  return {
    ENFORCE: pageEnforce ? "true" : "false",
    API_ENFORCE: apiEnforce ? "true" : "false",
    ASK_BACKEND_URL: "https://chat-backend.example/api/ask",
    ASK_BACKEND_SCOPE: "reckoner",
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

function apiPostReq(cookie = ""): Request {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (cookie) headers["cookie"] = cookie;
  return new Request("https://app.cjipro.com/api/ask", {
    method: "POST",
    headers,
    body: JSON.stringify({ query: "cohort-wide login regression?" }),
  });
}

const COOKIE_WITH_TOKEN = "__Secure-cjipro-session=dummy.jwt.token";

beforeEach(() => {
  vi.mocked(verifySession).mockReset();
  vi.mocked(verifySession).mockImplementation(async (token) => {
    if (!token) return { kind: "missing" };
    throw new Error("test must set explicit mock for token-present case");
  });
  // Default global fetch — most tests intercept their own.
  vi.stubGlobal("fetch", async () =>
    new Response(JSON.stringify({ answer: "ok" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
});

describe("Worker /api/ask — API_ENFORCE separation", () => {
  test("approved + API_ENFORCE=true → forwards (200)", async () => {
    const db = new FakeApprovalsDb();
    db.approved.push({ email: "alpha@example.com" });
    db.sessions.push({ sub: "u_alpha", email: "alpha@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_alpha" },
    });

    const res = await worker.fetch(
      apiPostReq(COOKIE_WITH_TOKEN),
      envWith(db, true, true),
      testCtx(),
    );
    expect(res.status).toBe(200);
  });

  test("not-approved + API_ENFORCE=true → 401 JSON (not 302)", async () => {
    const db = new FakeApprovalsDb();
    db.sessions.push({ sub: "u_bravo", email: "bravo@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo" },
    });

    const res = await worker.fetch(
      apiPostReq(COOKIE_WITH_TOKEN),
      envWith(db, true, true),
      testCtx(),
    );
    expect(res.status).toBe(401);
    expect(res.headers.get("content-type")).toContain("application/json");
    const body = await res.json();
    expect(body).toMatchObject({ error: "unauthorized", reason: "not_approved" });
    // Critical: must NOT be a 302 to login.cjipro.com — fetch() can't follow it.
    expect(res.headers.get("location")).toBeNull();
  });

  test("missing cookie + API_ENFORCE=true → 401 JSON", async () => {
    const db = new FakeApprovalsDb();
    const res = await worker.fetch(
      apiPostReq(),
      envWith(db, true, true),
      testCtx(),
    );
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body).toMatchObject({ error: "unauthorized", reason: "missing_session" });
  });

  test("API_ENFORCE=false + not-approved → forwards (shadow)", async () => {
    const db = new FakeApprovalsDb();
    db.sessions.push({ sub: "u_bravo", email: "bravo@example.com" });
    vi.mocked(verifySession).mockResolvedValue({
      kind: "valid",
      payload: { sub: "u_bravo" },
    });

    const res = await worker.fetch(
      apiPostReq(COOKIE_WITH_TOKEN),
      envWith(db, true, false), // page enforce on, API enforce off
      testCtx(),
    );
    // Shadow on the API path — request is logged + passed through.
    expect(res.status).toBe(200);
  });

  test("page ENFORCE=false but API_ENFORCE=true gates only the API", async () => {
    // Same env, request /reckoner → should render in shadow. Request
    // /api/ask without auth → should still 401.
    const db = new FakeApprovalsDb();

    const pageRes = await worker.fetch(
      new Request("https://app.cjipro.com/reckoner"),
      envWith(db, false, true),
      testCtx(),
    );
    expect(pageRes.status).toBe(200); // shadow renders the page

    const apiRes = await worker.fetch(
      apiPostReq(),
      envWith(db, false, true),
      testCtx(),
    );
    expect(apiRes.status).toBe(401);
  });
});

// ── Router routing test ──────────────────────────────────────────────────

describe("dispatch — /api/ask routing", () => {
  test("dispatch routes /api/ask through to apiAskHandler", async () => {
    const { dispatch } = await import("../src/router");
    const req = new Request("https://app.cjipro.com/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "x" }),
    });
    const env: ApiAskEnv = {
      ASK_BACKEND_URL: "https://chat-backend.example/api/ask",
      ASK_BACKEND_SCOPE: "reckoner",
    };
    let called = false;
    vi.stubGlobal("fetch", async () => {
      called = true;
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const res = await dispatch(req, env);
    expect(res!.status).toBe(200);
    expect(called).toBe(true);
  });

  test("dispatch /api/ask without apiEnv arg returns 500 (defensive)", async () => {
    const { dispatch } = await import("../src/router");
    const req = new Request("https://app.cjipro.com/api/ask", {
      method: "POST",
      body: "{}",
    });
    const res = await dispatch(req);
    expect(res!.status).toBe(500);
    const body = await res!.json();
    expect(body).toMatchObject({ error: "api_unconfigured" });
  });
});
