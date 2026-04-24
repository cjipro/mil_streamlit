import { describe, expect, test } from "vitest";
import { isAdmin } from "../src/admin";
import { FakeD1, asD1 } from "./fake_d1";

function seed(db: FakeD1, ...emails: string[]): void {
  for (const e of emails) {
    db.admins.push({
      email: e,
      added_at: "2026-04-24T00:00:00.000Z",
      added_by: "bootstrap",
    });
  }
}

describe("isAdmin", () => {
  test("admin returns true", async () => {
    const db = new FakeD1();
    seed(db, "hussain@example.com");
    expect(await isAdmin(asD1(db), "hussain@example.com")).toBe(true);
  });

  test("non-admin returns false", async () => {
    const db = new FakeD1();
    seed(db, "hussain@example.com");
    expect(await isAdmin(asD1(db), "random@example.com")).toBe(false);
  });

  test("case-insensitive", async () => {
    const db = new FakeD1();
    seed(db, "hussain@example.com");
    expect(await isAdmin(asD1(db), "Hussain@EXAMPLE.com")).toBe(true);
  });

  test("empty input returns false", async () => {
    const db = new FakeD1();
    seed(db, "hussain@example.com");
    expect(await isAdmin(asD1(db), "")).toBe(false);
    expect(await isAdmin(asD1(db), undefined)).toBe(false);
    expect(await isAdmin(asD1(db), null)).toBe(false);
  });
});
