import { describe, expect, test } from "vitest";
import { lookupSessionEmail, writeSession } from "../src/sessions";
import { FakeD1, asD1 } from "./fake_d1";

const NOW = new Date("2026-04-24T12:00:00.000Z");

describe("writeSession + lookupSessionEmail", () => {
  test("write then lookup returns the email", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "alpha@example.com", NOW);
    const email = await lookupSessionEmail(asD1(db), "u_alpha");
    expect(email).toBe("alpha@example.com");
  });

  test("emails are canonicalised on write", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "  Alpha@Example.COM  ", NOW);
    const email = await lookupSessionEmail(asD1(db), "u_alpha");
    expect(email).toBe("alpha@example.com");
  });

  test("INSERT OR REPLACE updates existing row", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "old@example.com", NOW);
    await writeSession(asD1(db), "u_alpha", "new@example.com", NOW);
    expect(db.sessions).toHaveLength(1);
    expect(await lookupSessionEmail(asD1(db), "u_alpha")).toBe("new@example.com");
  });

  test("missing sub returns undefined", async () => {
    const db = new FakeD1();
    expect(await lookupSessionEmail(asD1(db), "u_unknown")).toBeUndefined();
    expect(await lookupSessionEmail(asD1(db), undefined)).toBeUndefined();
    expect(await lookupSessionEmail(asD1(db), null)).toBeUndefined();
  });
});
