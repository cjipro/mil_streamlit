// MIL-152 — partner_profiles helpers.

import { describe, expect, test } from "vitest";
import {
  AFFIRMABLE_FIELDS,
  canonicalHash,
  confirmDetails,
  ensureProfile,
  getProfile,
  needsReaffirmation,
  setFirm,
  type PartnerProfile,
} from "../src/partner_profiles";
import { FakeD1, asD1 } from "./fake_d1";

const NOW = new Date("2026-04-27T10:00:00.000Z");

describe("ensureProfile — first-touch idempotency", () => {
  test("creates a minimal row for a new sub", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    expect(db.partnerProfiles).toHaveLength(1);
    const row = db.partnerProfiles[0];
    expect(row.sub).toBe("u_alpha");
    expect(row.contact_email).toBe("alpha@example.com");
    expect(row.display_name).toBeNull();
    expect(row.firm_slug).toBeNull();
    expect(row.contact_pref).toBe("email-only");
    expect(row.created_at).toBe(NOW.toISOString());
  });

  test("emails canonicalised on write", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "  Alpha@Example.COM  ", NOW);
    expect(db.partnerProfiles[0].contact_email).toBe("alpha@example.com");
  });

  test("repeat call never overwrites existing fields", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    // Simulate user self-affirms + admin sets firm
    db.partnerProfiles[0].display_name = "Alpha User";
    db.partnerProfiles[0].firm_slug = "barclays";
    db.partnerProfiles[0].firm_name = "Barclays";
    // Sign back in — ensureProfile fires again.
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    expect(db.partnerProfiles).toHaveLength(1);
    expect(db.partnerProfiles[0].display_name).toBe("Alpha User");
    expect(db.partnerProfiles[0].firm_slug).toBe("barclays");
  });
});

describe("getProfile", () => {
  test("returns null for missing sub", async () => {
    const db = new FakeD1();
    expect(await getProfile(asD1(db), "u_unknown")).toBeNull();
    expect(await getProfile(asD1(db), undefined)).toBeNull();
    expect(await getProfile(asD1(db), null)).toBeNull();
  });

  test("returns the row when present", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    const row = await getProfile(asD1(db), "u_alpha");
    expect(row?.sub).toBe("u_alpha");
  });
});

describe("setFirm — admin-only firm assignment", () => {
  test("attaches firm_slug + firm_name to existing profile", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    const out = await setFirm(asD1(db), "u_alpha", "barclays", "Barclays", NOW);
    expect(out.kind).toBe("ok");
    expect(db.partnerProfiles[0].firm_slug).toBe("barclays");
    expect(db.partnerProfiles[0].firm_name).toBe("Barclays");
  });

  test("returns not-found for unknown sub (admin asked for someone who never signed in)", async () => {
    const db = new FakeD1();
    const out = await setFirm(asD1(db), "u_ghost", "barclays", "Barclays", NOW);
    expect(out.kind).toBe("not-found");
  });

  test("rejects invalid firm_slug shape — uppercase fails", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    await expect(
      setFirm(asD1(db), "u_alpha", "Barclays", "Barclays", NOW),
    ).rejects.toThrow(/invalid firm_slug/);
  });

  test("rejects invalid firm_slug shape — special chars fail", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    await expect(
      setFirm(asD1(db), "u_alpha", "barclays/uk", "Barclays", NOW),
    ).rejects.toThrow();
  });
});

describe("canonicalHash — change-detection", () => {
  test("identical payloads produce identical hashes", async () => {
    const a = await canonicalHash({ display_name: "Alpha", role: "PM" });
    const b = await canonicalHash({ display_name: "Alpha", role: "PM" });
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
  });

  test("key-order does not affect hash", async () => {
    const a = await canonicalHash({ display_name: "Alpha", role: "PM" });
    const b = await canonicalHash({ role: "PM", display_name: "Alpha" });
    expect(a).toBe(b);
  });

  test("whitespace + case differences canonicalised away", async () => {
    const a = await canonicalHash({ display_name: "Alpha", role: "PM" });
    const b = await canonicalHash({
      display_name: "  alpha  ",
      role: "pm",
    });
    expect(a).toBe(b);
  });

  test("different content produces different hash", async () => {
    const a = await canonicalHash({ display_name: "Alpha", role: "PM" });
    const b = await canonicalHash({ display_name: "Alpha", role: "Designer" });
    expect(a).not.toBe(b);
  });

  test("undefined and null treated identically (both → null)", async () => {
    const a = await canonicalHash({ display_name: "Alpha", role: undefined });
    const b = await canonicalHash({ display_name: "Alpha", role: null });
    expect(a).toBe(b);
  });
});

describe("confirmDetails", () => {
  test("first confirm — writes hash + ts, reports all populated fields changed", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    const out = await confirmDetails(
      asD1(db),
      "u_alpha",
      { display_name: "Alpha User", role: "Head of CX" },
      NOW,
    );
    expect("kind" in out && out.kind === "not-found").toBe(false);
    if ("kind" in out) throw new Error("unexpected not-found");
    expect(out.prev_hash).toBeNull();
    expect(out.new_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(out.fields_changed).toContain("display_name");
    expect(out.fields_changed).toContain("role");
    const row = db.partnerProfiles[0];
    expect(row.display_name).toBe("Alpha User");
    expect(row.role).toBe("Head of CX");
    expect(row.last_confirmed_at).toBe(NOW.toISOString());
    expect(row.last_confirmed_hash).toBe(out.new_hash);
  });

  test("re-confirm with identical values — bumps ts, hash unchanged, no fields_changed", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    const first = await confirmDetails(
      asD1(db),
      "u_alpha",
      { display_name: "Alpha User", role: "PM" },
      NOW,
    );
    if ("kind" in first) throw new Error("unexpected not-found");
    const later = new Date("2026-07-27T10:00:00.000Z");
    const second = await confirmDetails(
      asD1(db),
      "u_alpha",
      { display_name: "Alpha User", role: "PM" },
      later,
    );
    if ("kind" in second) throw new Error("unexpected not-found");
    expect(second.new_hash).toBe(first.new_hash);
    expect(second.fields_changed).toEqual([]);
    expect(db.partnerProfiles[0].last_confirmed_at).toBe(later.toISOString());
  });

  test("partial PATCH — undefined keys preserve existing", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    await confirmDetails(
      asD1(db),
      "u_alpha",
      { display_name: "Alpha", role: "PM" },
      NOW,
    );
    // Update role only
    await confirmDetails(asD1(db), "u_alpha", { role: "Designer" }, NOW);
    expect(db.partnerProfiles[0].display_name).toBe("Alpha");
    expect(db.partnerProfiles[0].role).toBe("Designer");
  });

  test("explicit null clears a field", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    await confirmDetails(
      asD1(db),
      "u_alpha",
      { display_name: "Alpha", role: "PM" },
      NOW,
    );
    await confirmDetails(asD1(db), "u_alpha", { role: null }, NOW);
    expect(db.partnerProfiles[0].role).toBeNull();
  });

  test("rejects non-affirmable keys (firm_slug must use setFirm)", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    // Cast through to bypass the type-checker — runtime guard must catch.
    await expect(
      confirmDetails(asD1(db), "u_alpha", { firm_slug: "barclays" } as never, NOW),
    ).rejects.toThrow(/not user-affirmable/);
  });

  test("not-found when profile row absent", async () => {
    const db = new FakeD1();
    const out = await confirmDetails(
      asD1(db),
      "u_ghost",
      { display_name: "Alpha" },
      NOW,
    );
    expect("kind" in out && out.kind === "not-found").toBe(true);
  });

  test("contact_email is canonicalised on write", async () => {
    const db = new FakeD1();
    await ensureProfile(asD1(db), "u_alpha", "alpha@example.com", NOW);
    await confirmDetails(
      asD1(db),
      "u_alpha",
      { contact_email: "  Alpha+News@Example.COM  " },
      NOW,
    );
    expect(db.partnerProfiles[0].contact_email).toBe("alpha+news@example.com");
  });
});

describe("needsReaffirmation", () => {
  test("true when profile is null", () => {
    expect(needsReaffirmation(null, NOW)).toBe(true);
  });

  test("true when last_confirmed_at is null", () => {
    const profile = stubProfile({ last_confirmed_at: null });
    expect(needsReaffirmation(profile, NOW)).toBe(true);
  });

  test("false at 89 days", () => {
    const ts = new Date(NOW.getTime() - 89 * 24 * 60 * 60 * 1000).toISOString();
    const profile = stubProfile({ last_confirmed_at: ts });
    expect(needsReaffirmation(profile, NOW)).toBe(false);
  });

  test("true at 91 days", () => {
    const ts = new Date(NOW.getTime() - 91 * 24 * 60 * 60 * 1000).toISOString();
    const profile = stubProfile({ last_confirmed_at: ts });
    expect(needsReaffirmation(profile, NOW)).toBe(true);
  });

  test("true when last_confirmed_at unparseable", () => {
    const profile = stubProfile({ last_confirmed_at: "not-a-date" });
    expect(needsReaffirmation(profile, NOW)).toBe(true);
  });
});

describe("AFFIRMABLE_FIELDS contract", () => {
  test("does NOT include firm fields", () => {
    expect(AFFIRMABLE_FIELDS).not.toContain("firm_slug");
    expect(AFFIRMABLE_FIELDS).not.toContain("firm_name");
  });
});

function stubProfile(overrides: Partial<PartnerProfile> = {}): PartnerProfile {
  return {
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
  };
}
