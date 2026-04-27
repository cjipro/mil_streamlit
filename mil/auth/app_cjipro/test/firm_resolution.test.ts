// MIL-155 — pure-logic tests for resolveFirm + the YAML-backed
// PARTNER_DOMAIN_TO_SLUG map. Split out from portal.test.ts so domain
// behaviour is exercisable without spinning up the portal renderer +
// FakeD1 fixtures.
//
// PARTNER_DOMAIN_TO_SLUG is generated at pretest time from
// mil/config/clients.yaml. If a partner is added there, these tests
// pick up the new domains automatically — no manual sync.

import { describe, expect, test } from "vitest";
import { resolveFirm } from "../src/firm_resolution";
import { PARTNER_DOMAIN_TO_SLUG } from "../src/partner_domains.generated";

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

const NOW_ISO = "2026-04-27T12:00:00.000Z";

const FULL_PROFILE: PartnerProfileRow = {
  sub: "u_alpha",
  display_name: "Alpha User",
  role: "Head of CX",
  firm_slug: "barclays",
  firm_name: "Barclays",
  contact_email: "alpha@example.com",
  contact_pref: "email-only",
  last_confirmed_at: NOW_ISO,
  last_confirmed_hash: "abc",
  created_at: NOW_ISO,
  updated_at: NOW_ISO,
};

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
    expect(r.slug).toBe("barclays");
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

  test("profile with null firm_slug falls through to next signal", () => {
    const profile = { ...FULL_PROFILE, firm_slug: null, firm_name: null };
    const r = resolveFirm(profile, "real.partner@barclays.com", false);
    expect(r.kind).toBe("domain-inferred");
  });

  test("malformed email (no @) → unprovisioned for non-admin", () => {
    const r = resolveFirm(null, "notanemail", false);
    expect(r.kind).toBe("unprovisioned");
  });

  test("uppercase email domain matches lowercase YAML entry", () => {
    const r = resolveFirm(null, "PARTNER@BARCLAYS.COM", false);
    expect(r.kind).toBe("domain-inferred");
    expect(r.slug).toBe("barclays");
  });
});

describe("PARTNER_DOMAIN_TO_SLUG (generated artefact)", () => {
  test("barclays seed domains present (load-bearing assertion — alpha cohort)", () => {
    expect(PARTNER_DOMAIN_TO_SLUG["barclays.com"]).toEqual({
      slug: "barclays",
      display: "Barclays",
    });
    expect(PARTNER_DOMAIN_TO_SLUG["barclays.co.uk"]).toEqual({
      slug: "barclays",
      display: "Barclays",
    });
  });

  test("all keys are lowercase + non-empty", () => {
    for (const domain of Object.keys(PARTNER_DOMAIN_TO_SLUG)) {
      expect(domain.length).toBeGreaterThan(0);
      expect(domain).toBe(domain.toLowerCase());
      expect(domain.startsWith("@")).toBe(false);
    }
  });

  test("all entries have non-empty slug + display", () => {
    for (const entry of Object.values(PARTNER_DOMAIN_TO_SLUG)) {
      expect(entry.slug.length).toBeGreaterThan(0);
      expect(entry.display.length).toBeGreaterThan(0);
    }
  });
});
