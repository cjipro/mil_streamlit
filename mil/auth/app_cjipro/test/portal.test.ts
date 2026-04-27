// MIL-151 + MIL-144 — /portal handler tests.
//
// Pure handler-level tests against a local FakeD1. The end-to-end
// auth-gate-then-portal flow is exercised in auth_gate.test.ts; this
// file pins the rendering rules and the confirm POST behaviour, plus
// the MIL-144 additions: welcome line, briefing hero (Share/Forward),
// recent dates strip, and product family with entitlement CTAs.

import { describe, expect, test } from "vitest";
import {
  buildRecentDates,
  firstName,
  handleGetPortal,
  handlePostConfirm,
  renderPortal,
  type PortalEnv,
  type PortalIdentity,
} from "../src/portal";
import { resolveFirm, type ResolvedFirm } from "../src/firm_resolution";

const FIRM_BARCLAYS_ADMIN_SET: ResolvedFirm = {
  slug: "barclays",
  display_name: "Barclays",
  kind: "admin-set",
  is_internal: false,
  has_briefing: true,
};

const FIRM_UNPROVISIONED: ResolvedFirm = {
  slug: null,
  display_name: "Setting up your account",
  kind: "unprovisioned",
  is_internal: false,
  has_briefing: false,
};

const FIRM_ADMIN_INTERNAL: ResolvedFirm = {
  slug: "barclays",
  display_name: "CJI",
  kind: "admin-internal",
  is_internal: true,
  has_briefing: true,
};

const FIRM_DOMAIN_INFERRED: ResolvedFirm = {
  slug: "barclays",
  display_name: "Barclays",
  kind: "domain-inferred",
  is_internal: false,
  has_briefing: true,
};

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
  public admins: string[] = []; // canonicalised emails
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
    if (s.startsWith("SELECT 1 AS present FROM admin_users WHERE email")) {
      const email = (this.args[0] as string).toLowerCase();
      return this.db.admins.includes(email)
        ? ({ present: 1 } as unknown as T)
        : null;
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

const FULL_PROFILE: PartnerProfileRow = {
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
};

describe("renderPortal — visual rules", () => {
  test("shows email + signed-in state", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      firm: FIRM_UNPROVISIONED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
      recentDates: [],
    });
    expect(html).toContain("alpha@example.com");
    expect(html).toContain("Signed in as");
    expect(html).toContain("Sign out");
  });

  test("welcome line uses display_name first token when set", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: FULL_PROFILE,
      firm: FIRM_BARCLAYS_ADMIN_SET,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [],
    });
    expect(html).toContain("Welcome back, Alpha.");
    expect(html).toContain("Barclays");
    expect(html).toContain("workspace");
  });

  test("welcome line falls back to email-prefix when display_name unset", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      firm: FIRM_UNPROVISIONED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
      recentDates: [],
    });
    expect(html).toContain("Welcome back, Alpha.");
  });

  test("admin-internal welcome → 'CJI' + Internal badge, no 'workspace' suffix", () => {
    const html = renderPortal({
      identity: { sub: "u_admin", email: "hussain.marketing@gmail.com" },
      profile: null,
      firm: FIRM_ADMIN_INTERNAL,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [],
    });
    expect(html).toContain("Welcome back, Hussain.");
    expect(html).toContain("CJI");
    expect(html).toContain("Internal");
    expect(html).not.toContain("CJI workspace");
    // Briefing hero is still functional — admin gets default subject (Barclays)
    expect(html).toContain('href="/sonar/barclays/"');
    expect(html).toContain("Today's Sonar briefing — Barclays");
  });

  test("domain-inferred firm renders as full workspace (no Internal badge)", () => {
    const html = renderPortal({
      identity: { sub: "u_p", email: "real.partner@barclays.com" },
      profile: null,
      firm: FIRM_DOMAIN_INFERRED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [{ iso: "2026-04-27", label: "Today" }],
    });
    expect(html).toContain("Welcome back, Real.");
    expect(html).toMatch(/Barclays<\/span>\s*workspace/);
    expect(html).not.toContain("Internal");
    expect(html).toContain('href="/sonar/barclays/2026-04-27/"');
    expect(html).toContain("Today's Sonar briefing for Barclays");
  });

  test("unprovisioned → 'Welcome back, X.' (no firm clause), disabled briefing hero", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: { ...FULL_PROFILE, firm_slug: null, firm_name: null },
      firm: FIRM_UNPROVISIONED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
      recentDates: [],
    });
    expect(html).toContain("Welcome back, Alpha.");
    expect(html).not.toContain("workspace");
    expect(html).not.toContain("Internal");
    expect(html).toContain("Setting up your account");
    expect(html).toContain("once your firm is provisioned");
    expect(html).not.toContain('href="/sonar/');
    expect(html).toContain("CJI Sonar");
  });

  test("admin-set firm → briefing hero links + share/forward mailto present", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: FULL_PROFILE,
      firm: FIRM_BARCLAYS_ADMIN_SET,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [],
    });
    expect(html).toContain('href="/sonar/barclays/"');
    expect(html).toContain("Today's Sonar briefing for Barclays");
    expect(html).toContain('href="mailto:?subject=');
    expect(html).toContain("Share with team");
    expect(html).toContain("Forward by email");
  });

  test("recent strip renders when firm has briefing + dates supplied", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: FULL_PROFILE,
      firm: FIRM_BARCLAYS_ADMIN_SET,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [
        { iso: "2026-04-27", label: "Today" },
        { iso: "2026-04-26", label: "Yesterday" },
        { iso: "2026-04-25", label: "Apr 25" },
      ],
    });
    expect(html).toContain('href="/sonar/barclays/2026-04-27/"');
    expect(html).toContain('href="/sonar/barclays/2026-04-26/"');
    expect(html).toContain('href="/sonar/barclays/2026-04-25/"');
    expect(html).toContain("All briefings →");
  });

  test("recent strip suppressed when firm.has_briefing=false even if dates supplied", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: { ...FULL_PROFILE, firm_slug: null },
      firm: FIRM_UNPROVISIONED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [{ iso: "2026-04-27", label: "Today" }],
    });
    expect(html).not.toContain('href="/sonar/');
  });

  test("product family — all four products visible with correct CTAs", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: FULL_PROFILE,
      firm: FIRM_BARCLAYS_ADMIN_SET,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [],
    });
    expect(html).toContain("CJI Reckoner");
    expect(html).toContain("CJI Sonar");
    expect(html).toContain("CJI Pulse");
    expect(html).toContain("CJI Lever");
    expect(html).toContain('href="/reckoner"');
    expect(html).toContain("You're here");
    expect(html).toContain("mailto:hello@cjipro.com?subject=CJI%20Pulse%20design%20partner");
    expect(html).toContain("mailto:hello@cjipro.com?subject=CJI%20Lever%20enquiry");
  });

  test("promptReaffirmation=true → confirm form rendered", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      firm: FIRM_UNPROVISIONED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
      recentDates: [],
    });
    expect(html).toContain('action="/portal/confirm"');
    expect(html).toContain('name="display_name"');
    expect(html).toContain('name="role"');
  });

  test("promptReaffirmation=false → confirm form NOT rendered, last-confirmed line shown", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: { ...FULL_PROFILE, last_confirmed_at: "2026-04-25T12:00:00.000Z" },
      firm: FIRM_BARCLAYS_ADMIN_SET,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [],
    });
    expect(html).not.toContain('action="/portal/confirm"');
    expect(html).toContain("Details last confirmed");
  });

  test("XSS — email, firm.display_name, display_name escaped", () => {
    const html = renderPortal({
      identity: { sub: "u_alpha", email: "<script>alert(1)</script>@example.com" },
      profile: {
        ...FULL_PROFILE,
        display_name: '<img onerror="x">',
        firm_slug: "x",
        firm_name: '<img onerror="x">',
      },
      firm: { ...FIRM_BARCLAYS_ADMIN_SET, display_name: '<img onerror="x">' },
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: false,
      recentDates: [],
    });
    expect(html).not.toContain("<script>");
    expect(html).not.toContain('<img onerror=');
    expect(html).toContain("&lt;script&gt;");
  });

  test("noindex meta — utility surface", () => {
    const html = renderPortal({
      identity: IDENTITY,
      profile: null,
      firm: FIRM_UNPROVISIONED,
      lastActiveAt: null,
      lastActiveCountry: null,
      promptReaffirmation: true,
      recentDates: [],
    });
    expect(html).toContain('name="robots" content="noindex,nofollow"');
  });
});

describe("resolveFirm", () => {
  test("admin-set wins over everything else", () => {
    const profile = { ...FULL_PROFILE };
    const r = resolveFirm(profile, "anything@barclays.com", true);
    expect(r.kind).toBe("admin-set");
    expect(r.slug).toBe("barclays");
    expect(r.is_internal).toBe(false);
  });
  test("admin flag → admin-internal with default subject", () => {
    const r = resolveFirm(null, "hussain.marketing@gmail.com", true);
    expect(r.kind).toBe("admin-internal");
    expect(r.is_internal).toBe(true);
    expect(r.display_name).toBe("CJI");
    expect(r.slug).toBe("barclays"); // default subject
    expect(r.has_briefing).toBe(true);
  });
  test("known partner email domain → domain-inferred", () => {
    const r = resolveFirm(null, "real.partner@barclays.com", false);
    expect(r.kind).toBe("domain-inferred");
    expect(r.slug).toBe("barclays");
    expect(r.display_name).toBe("Barclays");
    expect(r.has_briefing).toBe(true);
  });
  test("co.uk variant of barclays domain also inferred", () => {
    const r = resolveFirm(null, "x@barclays.co.uk", false);
    expect(r.kind).toBe("domain-inferred");
    expect(r.slug).toBe("barclays");
  });
  test("unknown email domain + non-admin → unprovisioned", () => {
    const r = resolveFirm(null, "stranger@randomdomain.com", false);
    expect(r.kind).toBe("unprovisioned");
    expect(r.slug).toBeNull();
    expect(r.has_briefing).toBe(false);
  });
  test("profile with empty firm_slug falls through to next signal", () => {
    const profile = { ...FULL_PROFILE, firm_slug: null, firm_name: null };
    const r = resolveFirm(profile, "real.partner@barclays.com", false);
    expect(r.kind).toBe("domain-inferred");
  });
  test("malformed email (no @) → unprovisioned for non-admin", () => {
    const r = resolveFirm(null, "notanemail", false);
    expect(r.kind).toBe("unprovisioned");
  });
});

describe("firstName helper", () => {
  test("uses display_name first token", () => {
    expect(firstName(FULL_PROFILE, "x@y.com")).toBe("Alpha");
  });
  test("falls back to email-prefix capitalised", () => {
    expect(firstName(null, "hussain@example.com")).toBe("Hussain");
  });
  test("falls back to 'there' on empty everything", () => {
    expect(firstName(null, "")).toBe("there");
  });
  test("trims whitespace-only display_name and falls back", () => {
    expect(firstName({ ...FULL_PROFILE, display_name: "   " }, "alpha@x.com")).toBe("Alpha");
  });
});

describe("buildRecentDates helper", () => {
  test("returns 3 dates by default — Today / Yesterday / Apr 25", () => {
    const dates = buildRecentDates(NOW);
    expect(dates).toHaveLength(3);
    expect(dates[0]).toEqual({ iso: "2026-04-27", label: "Today" });
    expect(dates[1]).toEqual({ iso: "2026-04-26", label: "Yesterday" });
    expect(dates[2]).toEqual({ iso: "2026-04-25", label: "Apr 25" });
  });
  test("respects custom count", () => {
    const dates = buildRecentDates(NOW, 1);
    expect(dates).toHaveLength(1);
    expect(dates[0].iso).toBe("2026-04-27");
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

  test("includes recent dates when firm is provisioned", async () => {
    const db = new FakeD1();
    seedProfile(db, { firm_slug: "barclays", firm_name: "Barclays" });
    const res = await handleGetPortal(IDENTITY, envFor(db), null, NOW);
    const body = await res.text();
    expect(body).toContain('href="/sonar/barclays/2026-04-27/"');
    expect(body).toContain('href="/sonar/barclays/2026-04-26/"');
  });

  test("omits recent dates when firm is not provisioned", async () => {
    const db = new FakeD1();
    seedProfile(db);
    const res = await handleGetPortal(IDENTITY, envFor(db), null, NOW);
    const body = await res.text();
    expect(body).not.toContain('href="/sonar/');
  });

  test("admin email → CJI welcome + Internal badge + functional briefing hero", async () => {
    const db = new FakeD1();
    db.admins.push("hussain.marketing@gmail.com");
    // No partner_profiles row — admin auto-resolves to CJI without one.
    const res = await handleGetPortal(
      { sub: "u_admin", email: "hussain.marketing@gmail.com" },
      envFor(db),
      null,
      NOW,
    );
    const body = await res.text();
    expect(body).toContain("Welcome back, Hussain.");
    expect(body).toContain("CJI");
    expect(body).toContain("Internal");
    expect(body).toContain("Today's Sonar briefing — Barclays");
    expect(body).toContain('href="/sonar/barclays/"');
  });

  test("@barclays.com email (non-admin, no profile) → domain-inferred Barclays", async () => {
    const db = new FakeD1();
    const res = await handleGetPortal(
      { sub: "u_p", email: "real.partner@barclays.com" },
      envFor(db),
      null,
      NOW,
    );
    const body = await res.text();
    expect(body).toContain("Welcome back, Real.");
    expect(body).toMatch(/Barclays<\/span>\s*workspace/);
    expect(body).not.toContain("Internal");
    expect(body).toContain('href="/sonar/barclays/"');
  });

  test("admin-set firm overrides domain inference", async () => {
    const db = new FakeD1();
    seedProfile(db, { firm_slug: "barclays", firm_name: "Barclays" });
    // Email domain is unrelated, but admin-set firm wins.
    const res = await handleGetPortal(
      { sub: "u_alpha", email: "alpha@example.com" },
      envFor(db),
      null,
      NOW,
    );
    const body = await res.text();
    expect(body).toMatch(/Barclays<\/span>\s*workspace/);
    expect(body).toContain('href="/sonar/barclays/"');
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
