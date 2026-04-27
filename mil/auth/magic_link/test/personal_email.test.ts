// MIL-147 — personal-email domain detection tests.

import { describe, expect, test } from "vitest";
import { isPersonalEmail, personalDomains } from "../src/personal_email";

describe("isPersonalEmail", () => {
  test("flags gmail.com", () => {
    expect(isPersonalEmail("alice@gmail.com")).toBe(true);
  });
  test("flags yahoo.co.uk", () => {
    expect(isPersonalEmail("bob@yahoo.co.uk")).toBe(true);
  });
  test("flags outlook.com / hotmail.com / icloud.com", () => {
    expect(isPersonalEmail("c@outlook.com")).toBe(true);
    expect(isPersonalEmail("d@hotmail.com")).toBe(true);
    expect(isPersonalEmail("e@icloud.com")).toBe(true);
  });
  test("flags proton.me + protonmail.com", () => {
    expect(isPersonalEmail("f@proton.me")).toBe(true);
    expect(isPersonalEmail("g@protonmail.com")).toBe(true);
  });
  test("flags live.com / live.co.uk (Hussain's actual login email)", () => {
    expect(isPersonalEmail("hussainahmed@live.com")).toBe(true);
    expect(isPersonalEmail("user@live.co.uk")).toBe(true);
  });
  test("does NOT flag corporate domains", () => {
    expect(isPersonalEmail("alice@barclays.com")).toBe(false);
    expect(isPersonalEmail("bob@hsbc.com")).toBe(false);
    expect(isPersonalEmail("c@cjipro.com")).toBe(false);
    expect(isPersonalEmail("d@randomcorp.co.uk")).toBe(false);
  });
  test("case-insensitive on domain", () => {
    expect(isPersonalEmail("alice@GMAIL.COM")).toBe(true);
    expect(isPersonalEmail("alice@Gmail.Com")).toBe(true);
  });
  test("trims whitespace", () => {
    expect(isPersonalEmail("alice@gmail.com  ")).toBe(true);
  });
  test("returns false on null / undefined / empty / malformed", () => {
    expect(isPersonalEmail(null)).toBe(false);
    expect(isPersonalEmail(undefined)).toBe(false);
    expect(isPersonalEmail("")).toBe(false);
    expect(isPersonalEmail("notanemail")).toBe(false);
    expect(isPersonalEmail("@gmail.com")).toBe(true); // domain only — flag it
    expect(isPersonalEmail("alice@")).toBe(false);
  });
});

describe("personalDomains", () => {
  test("returns a sorted snapshot of the domain list", () => {
    const list = personalDomains();
    expect(list.length).toBeGreaterThan(20);
    expect(list).toContain("gmail.com");
    expect(list).toContain("proton.me");
    // sorted
    expect(list).toEqual([...list].sort());
  });
});
