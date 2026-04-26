// MIL-151 — /portal handler tests.
//
// Pure handler-level tests against a local FakeD1. The end-to-end
// auth-gate-then-portal flow is exercised in auth_gate.test.ts; this
// file pins the rendering rules and the confirm POST behaviour.

import { describe, expect, test, beforeEach } from "vitest";
import {
  handleGetPortal,
  handlePostConfirm,
  renderPortal,
  type PortalEnv,
  type PortalIdentity,
} from "../src/portal";

interface PartnerProfileRow {
  sub: string;
  display_name: string | null;
  role: string | null;
  firm_slug: string | null;
  firm_name: string | null;
  contact_email: string | null;
  contact_pref: string;
  last_confirmed_at: string | null;
  last_confirmed_hash: string | null;
  created_at: string;
  updated_at: string;
}

class FakeD1 {
  public profiles: PartnerProfileRow[] = [];
  prepare(sql: string) {
    return new FakeStmt(this, sql, []);
  }
}

class FakeStmt {
  constructor(
    private db: FakeD1,
    private sql: string,
    private args: unknown[],
  ) {}
  bind(...args: unknown[]) {
    return new FakeStmt(this.db, this.sql, args);
  }
  async first<T = unknown>(): Promise<T | null> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("SELECT * FROM partner_profiles WHERE sub")) {
      const sub = this.args[0] as string;
      const hit = this.db.profiles.find((r) => r.sub === sub);
      return (hit as T | undefined) ?? null;
    }
    throw new Error(`FakeD1.first unhandled: ${this.sql}`);
  }
  async run() {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (
      s.startsWith(
        "UPDATE partner_profiles SET display_name = ?, role = ?, contact_email = ?, contact_pref = ?, last_confirmed_at = ?, last_confirmed_hash = ?, updated_at = ? WHERE sub = ?",
      )
    ) {
      const [display_name, role, contact_email, contact_pref, last_confirmed_at, last_confirmed_hash, updated_at, sub] =
        this.args as [string | null, string | null, string | null, string, string, string, string, string];
      const hit = this.db.profiles.find((r) => r.sub === sub);
      if (!hit) return { meta: { changes: 0 } };
      hit.display_name = display_name;
      hit.role = role;
      hit.contact_email = contact_email;
      hit.contact_pref = contact_pref;
      hit.last_confirmed_at = last_confirmed_at;
      hit.last_confirmed_hash = last_confirmed_hash;
      hit.updated_at = updated_at;
      return { meta: { changes: 1 } };
    }
    throw new Error(`FakeD1.run unhandled: ${this.sql}`);
  }
}

const NOW = new Date("2026-04-27T12:00:00.000Z");

const IDENTITY: PortalIdentity = {
  sub: "u_alpha",
  email: "alpha@example.com",
};

function envFor(db: FakeD1): PortalEnv {
  return { AUDIT_DB: db as unknown as D1Database };
}

function seedProfile(db: FakeD1, overrides: Partial<PartnerProfileRow> = {}) {
  db.profiles.push({
    sub: "u_alpha",
    display_name: null,
    role: null,
    firm_slug: null,
    firm_name: null,
    contact_email: "alpha@example.com",
    contact_pref: "email-only",
    last_confirmed_at: null,
    last_confirmed_hash: null,
    created_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
    ...overrides,
  });
}

describe("renderPortal — visual rules", () => {
  test("shows email + signed-in state", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
    });
    expect(html).toContain("alpha@example.com");
    expect(html).toContain("Signed in as");
    expect(html).toContain("Sign out");
  });

  test("no firm → 'Setting up your account' fallback + disabled briefing CTA", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: {
        sub: "u_alpha",
        display_name: null,
        role: null,
        firm_slug: null,
        firm_name: null,
        contact_email: "alpha@example.com",
        contact_pref: "email-only",
        last_confirmed_at: null,
        last_confirmed_hash: null,
        created_at: NOW.toISOString(),
        updated_at: NOW.toISOString(),
      },
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
    });
    expect(html).toContain("Setting up your account");
    expect(html).toContain("disabled");
    expect(html).not.toContain('href="/sonar/');
  });

  test("firm set → primary briefing CTA links to /sonar/{slug}/", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: {
        sub: "u_alpha",
        display_name: "Alpha User",
        role: "Head of CX",
        firm_slug: "barclays",
        firm_name: "Barclays",
        contact_email: "alpha@example.com",
        contact_pref: "email-only",
        last_confirmed_at: NOW.toISOString(),
        last_confirmed_hash: "abc",
        created_at: NOW.toISOString(),
        updated_at: NOW.toISOString(),
      },
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
    });
    expect(html).toContain('href="/sonar/barclays/"');
    expect(html).toContain("Barclays");
    // Reckoner CTA always present
    expect(html).toContain('href="/reckoner"');
  });

  test("promptReaffirmation=true → confirm form rendered", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
    });
    expect(html).toContain('action="/portal/confirm"');
    expect(html).toContain('name="display_name"');
    expect(html).toContain('name="role"');
  });

  test("promptReaffirmation=false → confirm form NOT rendered, last-confirmed line shown", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: {
        sub: "u_alpha",
        display_name: null,
        role: null,
        firm_slug: "barclays",
        firm_name: "Barclays",
        contact_email: "alpha@example.com",
        contact_pref: "email-only",
        last_confirmed_at: "2026-04-25T12:00:00.000Z",
        last_confirmed_hash: "abc",
        created_at: NOW.toISOString(),
        updated_at: NOW.toISOString(),
      },
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
    });
    expect(html).not.toContain('action="/portal/confirm"');
    expect(html).toContain("Details last confirmed");
  });

  test("XSS — email + firm_name escaped", () => {
    const html = renderPortal({
      identity: { sub: "u_alpha", email: "<script>alert(1)</script>@example.com" },
      profile: {
        sub: "u_alpha",
        display_name: null,
        role: null,
        firm_slug: "x",
        firm_name: '<img onerror="x">',
        contact_email: null,
        contact_pref: "email-only",
        last_confirmed_at: NOW.toISOString(),
        last_confirmed_hash: "abc",
        created_at: NOW.toISOString(),
        updated_at: NOW.toISOString(),
      },
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
    });
    expect(html).not.toContain("<script>");
    expect(html).not.toContain('<img onerror=');
    expect(html).toContain("&lt;script&gt;");
  });

  test("noindex meta — utility surface", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
    });
    expect(html).toContain('name="robots" content="noindex,nofollow"');
  });
});

describe("handleGetPortal", () => {
  test("renders 200 with no profile (profile not yet ensured)", async () => {
    const db = new FakeD1();
    const res = await handleGetPortal(IDENTITY, envFor(db), null, NOW);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    const body = await res.text();
    expect(body).toContain("alpha@example.com");
    expect(body).toContain("Setting up your account");
  });

  test("renders confirm form when last_confirmed_at is null", async () => {
    const db = new FakeD1();
    seedProfile(db);
    const res = await handleGetPortal(IDENTITY, envFor(db), null, NOW);
    const body = await res.text();
    expect(body).toContain('action="/portal/confirm"');
  });

  test("does NOT render confirm form when recently confirmed", async () => {
    const db = new FakeD1();
    seedProfile(db, {
      last_confirmed_at: new Date(NOW.getTime() - 60 * 24 * 60 * 60 * 1000).toISOString(),
      last_confirmed_hash: "abc",
    });
    const res = await handleGetPortal(IDENTITY, envFor(db), null, NOW);
    const body = await res.text();
    expect(body).not.toContain('action="/portal/confirm"');
    expect(body).toContain("Details last confirmed");
  });

  test("re-prompts at 91 days", async () => {
    const db = new FakeD1();
    seedProfile(db, {
      last_confirmed_at: new Date(NOW.getTime() - 91 * 24 * 60 * 60 * 1000).toISOString(),
      last_confirmed_hash: "abc",
    });
    const res = await handleGetPortal(IDENTITY, envFor(db), null, NOW);
    const body = await res.text();
    expect(body).toContain('action="/portal/confirm"');
  });
});

describe("handlePostConfirm", () => {
  test("writes display_name + role, returns 302 to /portal", async () => {
    const db = new FakeD1();
    seedProfile(db);
    const fd = new FormData();
    fd.set("display_name", "Alpha User");
    fd.set("role", "Head of CX");
    const { response, outcome } = await handlePostConfirm(IDENTITY, envFor(db), fd, NOW);
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("/portal");
    expect(outcome.fields_changed).toContain("display_name");
    expect(outcome.fields_changed).toContain("role");
    expect(outcome.new_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(db.profiles[0].display_name).toBe("Alpha User");
    expect(db.profiles[0].last_confirmed_at).toBe(NOW.toISOString());
  });

  test("empty form fields written as null", async () => {
    const db = new FakeD1();
    seedProfile(db, { display_name: "Old", role: "Old" });
    const fd = new FormData();
    fd.set("display_name", "");
    fd.set("role", "");
    await handlePostConfirm(IDENTITY, envFor(db), fd, NOW);
    expect(db.profiles[0].display_name).toBeNull();
    expect(db.profiles[0].role).toBeNull();
  });

  test("missing profile row returns redirect (defensive)", async () => {
    const db = new FakeD1();
    const fd = new FormData();
    fd.set("display_name", "Alpha");
    const { response, outcome } = await handlePostConfirm(IDENTITY, envFor(db), fd, NOW);
    expect(response.status).toBe(302);
    expect(outcome.new_hash).toBeNull();
  });

  test("re-confirm with same values: same hash, no fields_changed", async () => {
    const db = new FakeD1();
    seedProfile(db);
    const fd = new FormData();
    fd.set("display_name", "Alpha User");
    fd.set("role", "Head of CX");
    const first = await handlePostConfirm(IDENTITY, envFor(db), fd, NOW);
    // Identical second submission
    const fd2 = new FormData();
    fd2.set("display_name", "Alpha User");
    fd2.set("role", "Head of CX");
    const second = await handlePostConfirm(
      IDENTITY,
      envFor(db),
      fd2,
      new Date(NOW.getTime() + 60_000),
    );
    expect(second.outcome.new_hash).toBe(first.outcome.new_hash);
    expect(second.outcome.fields_changed).toEqual([]);
  });
});
