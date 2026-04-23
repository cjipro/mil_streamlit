import { describe, expect, test } from "vitest";
import { buildClearCookie, buildSessionCookie } from "../src/cookie";

const CFG = {
  name: "__Secure-cjipro-session",
  domain: ".cjipro.com",
  maxAgeSeconds: 3600,
};

describe("buildSessionCookie", () => {
  test("contains the token", () => {
    const c = buildSessionCookie("eyJhbGc.XXX.YYY", CFG);
    expect(c).toMatch(/^__Secure-cjipro-session=eyJhbGc\.XXX\.YYY/);
  });

  test("has all security flags", () => {
    const c = buildSessionCookie("tok", CFG);
    expect(c).toContain("HttpOnly");
    expect(c).toContain("Secure");
    expect(c).toContain("SameSite=Lax");
  });

  test("sets Domain and Path", () => {
    const c = buildSessionCookie("tok", CFG);
    expect(c).toContain("Domain=.cjipro.com");
    expect(c).toContain("Path=/");
  });

  test("sets Max-Age from config", () => {
    const c = buildSessionCookie("tok", { ...CFG, maxAgeSeconds: 60 });
    expect(c).toContain("Max-Age=60");
  });
});

describe("buildClearCookie", () => {
  test("Max-Age=0 clears the cookie", () => {
    const c = buildClearCookie(CFG);
    expect(c).toContain("Max-Age=0");
  });

  test("preserves Domain and Path so browser matches the live cookie", () => {
    const c = buildClearCookie(CFG);
    expect(c).toContain("Domain=.cjipro.com");
    expect(c).toContain("Path=/");
  });

  test("keeps security flags", () => {
    const c = buildClearCookie(CFG);
    expect(c).toContain("HttpOnly");
    expect(c).toContain("Secure");
    expect(c).toContain("SameSite=Lax");
  });
});
