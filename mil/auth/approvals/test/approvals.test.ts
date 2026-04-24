import { describe, expect, test } from "vitest";
import { canonicalEmail, isApproved } from "../src/approvals";
import { FakeD1, asD1 } from "./fake_d1";

function seed(db: FakeD1, ...emails: string[]): void {
  for (const e of emails) {
    db.users.push({
      email: e,
      approved_at: "2026-04-24T00:00:00.000Z",
      approved_by: "test",
      note: null,
    });
  }
}

describe("isApproved", () => {
  test("approved email returns true", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), "alpha@example.com")).toBe(true);
  });

  test("non-approved email returns false", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), "bravo@example.com")).toBe(false);
  });

  test("empty allowlist denies everyone", async () => {
    const db = new FakeD1();
    expect(await isApproved(asD1(db), "alpha@example.com")).toBe(false);
  });

  test("case-insensitive lookup", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), "Alpha@Example.COM")).toBe(true);
  });

  test("leading/trailing whitespace stripped", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), "  alpha@example.com  ")).toBe(true);
  });

  test("undefined input denies", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), undefined)).toBe(false);
  });

  test("null input denies", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), null)).toBe(false);
  });

  test("empty string denies", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), "")).toBe(false);
  });

  test("whitespace-only denies", async () => {
    const db = new FakeD1();
    seed(db, "alpha@example.com");
    expect(await isApproved(asD1(db), "   ")).toBe(false);
  });
});

describe("canonicalEmail", () => {
  test("lowercases + trims", () => {
    expect(canonicalEmail("  Alpha@Example.COM  ")).toBe("alpha@example.com");
  });

  test("already-canonical passes through", () => {
    expect(canonicalEmail("alpha@example.com")).toBe("alpha@example.com");
  });
});
