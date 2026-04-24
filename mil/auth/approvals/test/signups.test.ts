import { describe, expect, test } from "vitest";
import {
  approvePending,
  denyPending,
  isPlausibleEmail,
  listApproved,
  listByStatus,
  revokeApproval,
  submitRequest,
} from "../src/signups";
import { FakeD1, asD1 } from "./fake_d1";

const NOW = new Date("2026-04-24T12:00:00.000Z");
const LATER = new Date("2026-04-24T13:00:00.000Z");

describe("isPlausibleEmail", () => {
  test("accepts normal emails", () => {
    expect(isPlausibleEmail("user@example.com")).toBe(true);
    expect(isPlausibleEmail("a.b+c@sub.example.co.uk")).toBe(true);
  });
  test("rejects junk", () => {
    expect(isPlausibleEmail("no-at-sign")).toBe(false);
    expect(isPlausibleEmail("user@")).toBe(false);
    expect(isPlausibleEmail("@example.com")).toBe(false);
    expect(isPlausibleEmail("user@example")).toBe(false);
    expect(isPlausibleEmail("user with spaces@example.com")).toBe(false);
  });
});

describe("submitRequest", () => {
  test("creates a pending row on first submission", async () => {
    const db = new FakeD1();
    const out = await submitRequest(
      asD1(db),
      { email: "Alpha@Example.COM", note: "alpha cohort", ipHash: "iph", uaHash: "uah" },
      NOW,
    );
    expect(out.kind).toBe("created");
    expect(db.signups).toHaveLength(1);
    expect(db.signups[0].email).toBe("alpha@example.com"); // canonicalised
    expect(db.signups[0].status).toBe("pending");
    expect(db.signups[0].note).toBe("alpha cohort");
    expect(db.signups[0].ip_hash).toBe("iph");
  });

  test("already-pending on resubmission within the window", async () => {
    const db = new FakeD1();
    await submitRequest(asD1(db), { email: "alpha@example.com" }, NOW);
    const second = await submitRequest(
      asD1(db),
      { email: "alpha@example.com" },
      LATER,
    );
    expect(second.kind).toBe("already-pending");
    expect(db.signups).toHaveLength(1);
  });

  test("already-approved if email is in approved_users", async () => {
    const db = new FakeD1();
    db.users.push({
      email: "alpha@example.com",
      approved_at: "x",
      approved_by: "x",
      note: null,
    });
    const out = await submitRequest(
      asD1(db),
      { email: "alpha@example.com" },
      NOW,
    );
    expect(out.kind).toBe("already-approved");
    expect(db.signups).toHaveLength(0);
  });

  test("invalid-email rejected before any D1 write", async () => {
    const db = new FakeD1();
    const out = await submitRequest(asD1(db), { email: "garbage" }, NOW);
    expect(out.kind).toBe("invalid-email");
    expect(db.signups).toHaveLength(0);
  });
});

describe("approvePending", () => {
  test("moves email into approved_users and marks row approved", async () => {
    const db = new FakeD1();
    await submitRequest(asD1(db), { email: "alpha@example.com" }, NOW);
    const id = db.signups[0].id;
    const out = await approvePending(asD1(db), id, "admin@example.com", LATER);
    expect(out.kind).toBe("ok");
    expect(db.users.find((u) => u.email === "alpha@example.com")).toBeDefined();
    expect(db.signups[0].status).toBe("approved");
    expect(db.signups[0].reviewed_by).toBe("admin@example.com");
  });

  test("not-found on unknown id", async () => {
    const db = new FakeD1();
    const out = await approvePending(asD1(db), 999, "admin@example.com");
    expect(out.kind).toBe("not-found");
  });

  test("not-pending if already approved/denied", async () => {
    const db = new FakeD1();
    await submitRequest(asD1(db), { email: "alpha@example.com" }, NOW);
    const id = db.signups[0].id;
    await approvePending(asD1(db), id, "admin@example.com", LATER);
    const again = await approvePending(asD1(db), id, "admin@example.com", LATER);
    expect(again.kind).toBe("not-pending");
  });
});

describe("denyPending", () => {
  test("marks row denied without touching approved_users", async () => {
    const db = new FakeD1();
    await submitRequest(asD1(db), { email: "alpha@example.com" }, NOW);
    const id = db.signups[0].id;
    const out = await denyPending(asD1(db), id, "admin@example.com", LATER);
    expect(out.kind).toBe("ok");
    expect(db.users).toHaveLength(0);
    expect(db.signups[0].status).toBe("denied");
  });
});

describe("revokeApproval", () => {
  test("removes the row from approved_users", async () => {
    const db = new FakeD1();
    db.users.push({
      email: "alpha@example.com",
      approved_at: "x",
      approved_by: "x",
      note: null,
    });
    const out = await revokeApproval(asD1(db), "ALPHA@example.com");
    expect(out.kind).toBe("ok");
    expect(db.users).toHaveLength(0);
  });

  test("not-found if the email was never approved", async () => {
    const db = new FakeD1();
    const out = await revokeApproval(asD1(db), "ghost@example.com");
    expect(out.kind).toBe("not-found");
  });
});

describe("listByStatus / listApproved", () => {
  test("listByStatus returns most-recent first", async () => {
    const db = new FakeD1();
    await submitRequest(asD1(db), { email: "a@x.com" }, new Date("2026-04-24T10:00:00Z"));
    await submitRequest(asD1(db), { email: "b@x.com" }, new Date("2026-04-24T11:00:00Z"));
    await submitRequest(asD1(db), { email: "c@x.com" }, new Date("2026-04-24T12:00:00Z"));
    const rows = await listByStatus(asD1(db), "pending");
    expect(rows.map((r) => r.email)).toEqual(["c@x.com", "b@x.com", "a@x.com"]);
  });

  test("listApproved returns most-recent first", async () => {
    const db = new FakeD1();
    db.users.push({ email: "a@x.com", approved_at: "2026-04-24T10:00Z", approved_by: "x", note: null });
    db.users.push({ email: "b@x.com", approved_at: "2026-04-24T12:00Z", approved_by: "x", note: null });
    const rows = await listApproved(asD1(db));
    expect(rows.map((r) => r.email)).toEqual(["b@x.com", "a@x.com"]);
  });
});
