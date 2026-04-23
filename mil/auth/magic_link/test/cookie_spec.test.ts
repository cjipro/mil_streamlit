import { describe, expect, test } from "vitest";
import { assertSpecCompliant } from "../src/cookie_spec";
import { buildClearCookie, buildSessionCookie } from "../src/cookie";

const CFG = {
  name: "__Secure-cjipro-session",
  domain: ".cjipro.com",
  maxAgeSeconds: 3600,
};

describe("cookie spec — issuance compliance", () => {
  test("buildSessionCookie emits spec-compliant header", () => {
    const r = assertSpecCompliant(buildSessionCookie("eyJ.tok.sig", CFG));
    expect(r.ok).toBe(true);
  });

  test("buildClearCookie emits spec-compliant header (Max-Age=0)", () => {
    const r = assertSpecCompliant(buildClearCookie(CFG));
    expect(r.ok).toBe(true);
  });

  test("custom Max-Age (24h) is still spec-compliant", () => {
    const r = assertSpecCompliant(
      buildSessionCookie("tok", { ...CFG, maxAgeSeconds: 86400 }),
    );
    expect(r.ok).toBe(true);
  });
});

describe("cookie spec — catches violations", () => {
  test("wrong cookie name fails", () => {
    const bad = "wrong-name=tok; Max-Age=60; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("cookie-name");
  });

  test("missing HttpOnly fails", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=.cjipro.com; Path=/; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("required-flag");
  });

  test("missing Secure fails", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=.cjipro.com; Path=/; HttpOnly; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("required-flag");
  });

  test("SameSite=Strict is rejected (would break return flow)", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=Strict";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("samesite");
  });

  test("SameSite=None is rejected (CSRF surface)", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=None";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("samesite");
  });

  test("Domain without leading dot is rejected", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=cjipro.com; Path=/; HttpOnly; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("domain");
  });

  test("missing Max-Age fails", () => {
    const bad = "__Secure-cjipro-session=tok; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("max-age-missing");
  });

  test("Expires attribute rejected (spec requires Max-Age only)", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Expires=Mon, 01 Jan 2030 00:00:00 GMT; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("forbidden-attr");
  });

  test("Partitioned attribute rejected (first-party session only)", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=Lax; Partitioned";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("forbidden-attr");
  });

  test("wrong Path fails", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=60; Domain=.cjipro.com; Path=/app; HttpOnly; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("path");
  });

  test("non-numeric Max-Age fails", () => {
    const bad = "__Secure-cjipro-session=tok; Max-Age=forever; Domain=.cjipro.com; Path=/; HttpOnly; Secure; SameSite=Lax";
    const r = assertSpecCompliant(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("max-age-invalid");
  });
});
