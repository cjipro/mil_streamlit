import { describe, expect, test } from "vitest";
import {
  forceSignout,
  listApprovedWithSessions,
  lookupSessionEmail,
  recordActivity,
  writeSession,
} from "../src/sessions";
import { FakeD1, asD1 } from "./fake_d1";

const NOW = new Date("2026-04-24T12:00:00.000Z");

describe("writeSession + lookupSessionEmail", () => {
  test("write then lookup returns the email", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "alpha@example.com", null, NOW);
    const email = await lookupSessionEmail(asD1(db), "u_alpha");
    expect(email).toBe("alpha@example.com");
  });

  test("emails are canonicalised on write", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "  Alpha@Example.COM  ", null, NOW);
    const email = await lookupSessionEmail(asD1(db), "u_alpha");
    expect(email).toBe("alpha@example.com");
  });

  test("INSERT OR REPLACE updates existing row", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "old@example.com", null, NOW);
    await writeSession(asD1(db), "u_alpha", "new@example.com", null, NOW);
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

describe("recordActivity", () => {
  test("updates last_active_at on existing session", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "alpha@example.com", null, NOW);
    expect(db.sessions[0].last_active_at).toBeNull();
    const later = new Date("2026-04-25T01:00:00.000Z");
    await recordActivity(asD1(db), "u_alpha", later);
    expect(db.sessions[0].last_active_at).toBe("2026-04-25T01:00:00.000Z");
  });

  test("no-op when sub has no session row", async () => {
    const db = new FakeD1();
    await recordActivity(asD1(db), "u_ghost", NOW);
    expect(db.sessions).toHaveLength(0);
  });
});

describe("listApprovedWithSessions", () => {
  test("LEFT JOIN: approved without session yields null last_active_at", async () => {
    const db = new FakeD1();
    db.users.push({
      email: "alpha@example.com",
      approved_at: "2026-04-24T10:00Z",
      approved_by: "x",
      note: null,
    });
    const rows = await listApprovedWithSessions(asD1(db));
    expect(rows).toHaveLength(1);
    expect(rows[0].email).toBe("alpha@example.com");
    expect(rows[0].last_active_at).toBeNull();
  });

  test("approved + session: last_active_at returned", async () => {
    const db = new FakeD1();
    db.users.push({
      email: "alpha@example.com",
      approved_at: "2026-04-24T10:00Z",
      approved_by: "x",
      note: null,
    });
    await writeSession(asD1(db), "u_alpha", "alpha@example.com", null, NOW);
    await recordActivity(
      asD1(db),
      "u_alpha",
      new Date("2026-04-25T00:30:00.000Z"),
    );
    const rows = await listApprovedWithSessions(asD1(db));
    expect(rows[0].last_active_at).toBe("2026-04-25T00:30:00.000Z");
  });
});

describe("forceSignout", () => {
  test("removes the session row, denies next gate hit", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "alpha@example.com", null, NOW);
    expect(db.sessions).toHaveLength(1);
    const out = await forceSignout(asD1(db), "alpha@example.com");
    expect(out.kind).toBe("ok");
    expect(db.sessions).toHaveLength(0);
    expect(await lookupSessionEmail(asD1(db), "u_alpha")).toBeUndefined();
  });

  test("not-found when no session matches", async () => {
    const db = new FakeD1();
    const out = await forceSignout(asD1(db), "ghost@example.com");
    expect(out.kind).toBe("not-found");
  });

  test("case-insensitive match on email", async () => {
    const db = new FakeD1();
    await writeSession(asD1(db), "u_alpha", "alpha@example.com", null, NOW);
    const out = await forceSignout(asD1(db), "Alpha@EXAMPLE.COM");
    expect(out.kind).toBe("ok");
    expect(db.sessions).toHaveLength(0);
  });
});
