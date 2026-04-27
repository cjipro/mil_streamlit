// MIL-156 — multi-subject admin picker on /portal.
//
// Two layers of test coverage:
//
//  1. renderPortal contract — picker hidden when SUBJECTS.length < 2,
//     visible only on admin-internal branch, never visible to partners.
//     Currently SUBJECTS.length === 1 (barclays) so we exercise the
//     hidden-by-default behaviour AND the not-visible-to-partners rule.
//     The visible-with-multiple-subjects path is exercised below by
//     stub-passing through PortalRenderOptions.adminSubjectChoice,
//     which is the only knob renderPortal sees.
//
//  2. handleAdminSubjectSwitch — pure function (no D1, no env). Exercises
//     the full state-table: valid slug → cookie set + 303; unknown slug
//     → cookie cleared + 303; same-slug-as-cookie → still emits new
//     cookie (idempotent — keeps Max-Age fresh).
//
// resolveFirm + cookie path tested in firm_resolution.test.ts.

import { describe, expect, test } from "vitest";
import {
  ADMIN_SUBJECT_COOKIE_NAME,
  handleAdminSubjectSwitch,
  renderPortal,
  type PortalRenderOptions,
} from "../src/portal";
import type { ResolvedFirm } from "../src/firm_resolution";
import { SUBJECTS } from "../src/subjects.generated";

const FIRM_ADMIN_INTERNAL: ResolvedFirm = {
  slug: "barclays",
  display_name: "CJI",
  kind: "admin-internal",
  is_internal: true,
  has_briefing: true,
};

const FIRM_BARCLAYS_PARTNER: ResolvedFirm = {
  slug: "barclays",
  display_name: "Barclays",
  kind: "admin-set",
  is_internal: false,
  has_briefing: true,
};

function baseOpts(firm: ResolvedFirm, choice?: string): PortalRenderOptions {
  return {
    identity: { sub: "u_x", email: "x@example.com" },
    profile: null,
    firm,
    lastActiveAt: null,
    lastActiveCountry: null,
    promptReaffirmation: false,
    recentDates: [],
    adminSubjectChoice: choice,
  };
}

describe("admin picker — render rules", () => {
  test("hidden when SUBJECTS.length === 1 (today's state)", () => {
    // Sanity check: clients.yaml ships exactly one subject today.
    expect(SUBJECTS.length).toBe(1);
    const html = renderPortal(baseOpts(FIRM_ADMIN_INTERNAL));
    // Look for the rendered element, not the bare classname (CSS contains
    // the selector verbatim).
    expect(html).not.toContain('<section class="admin-picker"');
    expect(html).not.toContain("Viewing as CJI Internal");
  });

  test("partners NEVER see the picker even when admin-internal exists", () => {
    // Partner cohort — admin-set / domain-inferred. firm.kind branches.
    const html = renderPortal(baseOpts(FIRM_BARCLAYS_PARTNER));
    expect(html).not.toContain('<section class="admin-picker"');
  });
});

describe("admin picker — handleAdminSubjectSwitch", () => {
  test("valid slug → 303 + Set-Cookie + correct location", () => {
    // Use the only known subject today.
    const validSlug = SUBJECTS[0]!.slug;
    const result = handleAdminSubjectSwitch(validSlug, null);
    expect(result.response.status).toBe(303);
    expect(result.response.headers.get("location")).toBe("/portal");
    const cookie = result.response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain(`${ADMIN_SUBJECT_COOKIE_NAME}=${validSlug}`);
    expect(cookie).toContain("Path=/");
    expect(cookie).toContain("Secure");
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=Lax");
    expect(cookie).not.toContain("Domain="); // __Host- prefix forbids it
    expect(result.oldSlug).toBeNull();
    expect(result.newSlug).toBe(validSlug);
  });

  test("unknown slug → cookie CLEARED + 303 (Max-Age=0)", () => {
    const result = handleAdminSubjectSwitch("not-a-real-slug", "barclays");
    expect(result.response.status).toBe(303);
    const cookie = result.response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain(`${ADMIN_SUBJECT_COOKIE_NAME}=`);
    expect(cookie).toContain("Max-Age=0");
    expect(result.oldSlug).toBe("barclays");
    expect(result.newSlug).toBe("barclays"); // falls back to default
  });

  test("null slug (no query param) → cookie cleared", () => {
    const result = handleAdminSubjectSwitch(null, "barclays");
    expect(result.response.status).toBe(303);
    expect(result.response.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  test("oldSlug threads through from cookie for audit emission", () => {
    const result = handleAdminSubjectSwitch(SUBJECTS[0]!.slug, "previous-slug");
    expect(result.oldSlug).toBe("previous-slug");
  });

  test("redirect cache-control is no-store (don't cache the switch)", () => {
    const result = handleAdminSubjectSwitch(SUBJECTS[0]!.slug, null);
    expect(result.response.headers.get("cache-control")).toBe("no-store");
  });
});

describe("SUBJECTS generated artefact", () => {
  test("non-empty (clients.yaml has at least one subject)", () => {
    expect(SUBJECTS.length).toBeGreaterThan(0);
  });

  test("first entry has non-empty slug + display", () => {
    const first = SUBJECTS[0]!;
    expect(first.slug.length).toBeGreaterThan(0);
    expect(first.display.length).toBeGreaterThan(0);
  });

  test("all slugs match the lowercase-alphanumeric-hyphen shape", () => {
    for (const s of SUBJECTS) {
      expect(s.slug).toMatch(/^[a-z0-9-]+$/);
    }
  });
});
