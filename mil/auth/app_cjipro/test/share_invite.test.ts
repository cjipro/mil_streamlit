// MIL-145 — share-invite handler + share-affordance render contract.
//
// handleShareInvite is the POST endpoint that backs the "Add colleague
// by email" form on Sonar briefings. Pure-D1 dependency; we run it
// against a FakeD1 that mirrors the schema submitRequest + checkAndIncrement
// expect.
//
// renderShareAffordance is a pure HTML function — visual contract tests
// pin the load-bearing pieces (form action, mailto target, link box).

import { describe, expect, test, beforeEach } from "vitest";
import { handleShareInvite } from "../src/share_invite";
import {
  renderShareAffordance,
  renderInviteSentBanner,
} from "../src/share_affordance";

interface PendingRow {
  id: number;
  email: string;
  status: string;
  note: string | null;
}

interface ApprovedRow {
  email: string;
}

interface RateLimitRow {
  ip_hash: string;
  window_start: string;
  count: number;
}

class FakeD1 {
  public pending: PendingRow[] = [];
  public approved: ApprovedRow[] = [];
  public rateLimit: RateLimitRow[] = [];
  public salts: { utc_date: string; salt: string }[] = [];
  public _nextPendingId = 1;
  prepare(sql: string) {
    return new FakeStmt(this, sql, []);
  }
  // submitRequest writes via .run() with multiple .prepare/.bind calls
  // tracked above; rate_limit and salt store call equivalent paths.
  batch(_stmts: unknown[]): Promise<unknown[]> {
    return Promise.resolve([]);
  }
  nextId(): number {
    return this._nextPendingId++;
  }
}

class FakeStmt {
  constructor(
    private db: FakeD1,
    private sql: string,
    private args: unknown[],
  ) {}
  bind(...a: unknown[]): FakeStmt {
    return new FakeStmt(this.db, this.sql, a);
  }
  async first<T>(): Promise<T | null> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("SELECT 1 AS present FROM approved_users")) {
      const [email] = this.args as [string];
      const hit = this.db.approved.find((r) => r.email === email);
      return (hit ? { present: 1 } : null) as T | null;
    }
    if (s.startsWith("SELECT id FROM pending_signups")) {
      const [email] = this.args as [string];
      const hit = this.db.pending.find((r) => r.email === email && r.status === "pending");
      return (hit ? { id: hit.id } : null) as T | null;
    }
    // Rate-limit + salt store reads — empty defaults are fine for these tests.
    if (s.startsWith("SELECT count FROM signup_rate_limit") || s.includes("rate_limit")) {
      return null;
    }
    if (s.includes("audit_salts")) {
      return null;
    }
    return null;
  }
  async run(): Promise<{ meta: { last_row_id?: number; changes?: number } }> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("INSERT INTO pending_signups")) {
      const [email, _ts, _ipHash, _uaHash, note] = this.args as [
        string, string, string | null, string | null, string | null,
      ];
      const id = this.db.nextId();
      this.db.pending.push({ id, email, status: "pending", note });
      return { meta: { last_row_id: id, changes: 1 } };
    }
    return { meta: { changes: 0 } };
  }
  async all<T>(): Promise<{ results: T[] }> {
    return { results: [] };
  }
}

const ENV = (db: FakeD1) => ({ AUDIT_DB: db as unknown as D1Database });
const IDENTITY = { sub: "u_inviter", email: "inviter@barclays.com" };

function makeRequest(body: Record<string, string>): Request {
  const form = new URLSearchParams();
  for (const [k, v] of Object.entries(body)) form.append(k, v);
  return new Request("https://app.cjipro.com/api/share-invite", {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "cf-connecting-ip": "203.0.113.42",
      "user-agent": "Mozilla/5.0 (Test)",
    },
    body: form.toString(),
  });
}

describe("handleShareInvite — happy path", () => {
  let db: FakeD1;
  beforeEach(() => { db = new FakeD1(); });

  test("creates pending_signups row with inviter context in note", async () => {
    const req = makeRequest({
      recipient_email: "colleague@barclays.com",
      source_firm_slug: "barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.outcomeKind).toBe("created");
    expect(db.pending.length).toBe(1);
    expect(db.pending[0]!.email).toBe("colleague@barclays.com");
    // Note carries inviter email + firm display name — load-bearing for
    // the admin reviewing the queue.
    expect(db.pending[0]!.note).toContain("inviter@barclays.com");
    expect(db.pending[0]!.note).toContain("Barclays");
  });

  test("redirects (303) back to source briefing with invite_sent param", async () => {
    const req = makeRequest({
      recipient_email: "x@example.com",
      source_firm_slug: "barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.response.status).toBe(303);
    const loc = r.response.headers.get("location") ?? "";
    expect(loc).toContain("/sonar/barclays/");
    expect(loc).toContain("invite_sent=x%40example.com");
  });

  test("cache-control: no-store on the redirect response", async () => {
    const req = makeRequest({
      recipient_email: "x@y.com",
      source_firm_slug: "barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.response.headers.get("cache-control")).toBe("no-store");
  });
});

describe("handleShareInvite — validation + safety", () => {
  let db: FakeD1;
  beforeEach(() => { db = new FakeD1(); });

  test("missing recipient → 400", async () => {
    const req = makeRequest({ source_firm_slug: "barclays" });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.response.status).toBe(400);
    expect(r.outcomeKind).toBe("missing-fields");
    expect(db.pending.length).toBe(0);
  });

  test("invalid email → 400 with no DB write", async () => {
    const req = makeRequest({
      recipient_email: "not-an-email",
      source_firm_slug: "barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.response.status).toBe(400);
    expect(r.outcomeKind).toBe("invalid-email");
    expect(db.pending.length).toBe(0);
  });

  test("unknown source slug falls back to /portal redirect (no open-redirect risk)", async () => {
    const req = makeRequest({
      recipient_email: "x@y.com",
      source_firm_slug: "spoofed-slug",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.response.status).toBe(303);
    const loc = r.response.headers.get("location") ?? "";
    expect(loc).toBe("/portal");
    // sourceFirmSlug is null on the result because it didn't pass the regex.
    expect(r.sourceFirmSlug).toBeNull();
  });

  test("malformed source slug shape (uppercase) → null + /portal redirect", async () => {
    const req = makeRequest({
      recipient_email: "x@y.com",
      source_firm_slug: "Barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.sourceFirmSlug).toBeNull();
  });

  test("already-pending recipient → still 303 with same banner (no enumeration leak)", async () => {
    db.pending.push({ id: 1, email: "alice@example.com", status: "pending", note: null });
    const req = makeRequest({
      recipient_email: "alice@example.com",
      source_firm_slug: "barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.outcomeKind).toBe("already-pending");
    expect(r.response.status).toBe(303);
  });

  test("already-approved recipient → still 303 with same banner", async () => {
    db.approved.push({ email: "alice@example.com" });
    const req = makeRequest({
      recipient_email: "alice@example.com",
      source_firm_slug: "barclays",
    });
    const r = await handleShareInvite(req, ENV(db), IDENTITY, "test-salt");
    expect(r.outcomeKind).toBe("already-approved");
    expect(r.response.status).toBe(303);
  });
});

describe("renderShareAffordance — HTML contract", () => {
  const opts = {
    firmSlug: "barclays",
    firmDisplay: "Barclays",
    briefingUrl: "https://app.cjipro.com/sonar/barclays/2026-04-27/",
    briefingDateLabel: "2026-04-27",
  };

  test("share form posts to /api/share-invite", () => {
    const html = renderShareAffordance(opts);
    expect(html).toContain('action="/api/share-invite"');
    expect(html).toContain('method="post"');
  });

  test("mailto link encodes briefing URL + request-access link", () => {
    const html = renderShareAffordance(opts);
    expect(html).toContain('href="mailto:?');
    expect(html).toContain(encodeURIComponent("Barclays"));
    // Briefing URL appears in the encoded mailto body.
    expect(html).toContain(encodeURIComponent(opts.briefingUrl));
    // Request-access fallback link is present so a forwarded recipient
    // who's not on the allowlist has a clear next step.
    expect(html).toContain(encodeURIComponent("https://login.cjipro.com/request-access"));
  });

  test("share-link box is readonly + selects on focus (CSP-friendly)", () => {
    const html = renderShareAffordance(opts);
    expect(html).toContain('class="cji-share-link" readonly');
    // No inline <script> — selection happens via onfocus="this.select()"
    // attribute which doesn't need script-src.
    expect(html).toContain('onfocus="this.select()"');
    expect(html).not.toContain("<script");
  });

  test("XSS-escapes firm display name", () => {
    const html = renderShareAffordance({
      ...opts,
      firmDisplay: '<img src=x onerror="alert(1)">',
    });
    expect(html).not.toContain('<img src=x');
    expect(html).toContain("&lt;img");
  });

  test("hidden source_firm_slug field carries firm context for the POST", () => {
    const html = renderShareAffordance(opts);
    expect(html).toContain('name="source_firm_slug" value="barclays"');
  });
});

describe("renderInviteSentBanner", () => {
  test("renders recipient email inside a banner div", () => {
    const html = renderInviteSentBanner("alice@example.com");
    expect(html).toContain("cji-share-confirm");
    expect(html).toContain("alice@example.com");
  });

  test("escapes XSS payload in recipient param", () => {
    const html = renderInviteSentBanner('"><script>alert(1)</script>');
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
