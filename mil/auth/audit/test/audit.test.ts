import { describe, expect, test } from "vitest";
import { extractJwtSub, logAuthEvent } from "../src/audit";
import { verifyChain } from "../src/verify";
import { FakeD1, asD1 } from "./fake_d1";

const FIXED_SALT = "a".repeat(64);
const fixedSaltStore = {
  async getOrCreate(_: string): Promise<string> {
    return FIXED_SALT;
  },
};

function fixedNow(): Date {
  return new Date("2026-04-24T12:34:56.000Z");
}

describe("logAuthEvent", () => {
  test("writes one row with prev_hash=genesis", async () => {
    const db = new FakeD1();
    await logAuthEvent(
      asD1(db),
      {
        worker: "edge-bouncer",
        event_type: "bouncer.pass.public",
        method: "GET",
        host: "cjipro.com",
        path: "/",
      },
      { saltStore: fixedSaltStore, now: fixedNow() },
    );
    expect(db.events).toHaveLength(1);
    expect(db.events[0].prev_hash).toBe("genesis");
    expect(db.events[0].row_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(db.events[0].ts).toBe("2026-04-24T12:34:56.000Z");
    expect(db.events[0].enforce).toBe(null); // not provided
  });

  test("hashes sensitive fields, never stores raw values", async () => {
    const db = new FakeD1();
    await logAuthEvent(
      asD1(db),
      {
        worker: "magic-link",
        event_type: "magic_link.callback.success",
        session_sub: "user_01ABCXYZ",
        ip: "203.0.113.7",
        user_agent: "Mozilla/5.0 (TestRunner)",
      },
      { saltStore: fixedSaltStore, now: fixedNow() },
    );
    const row = db.events[0];
    expect(row.user_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(row.ip_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(row.ua_hash).toMatch(/^[0-9a-f]{64}$/);
    // Raw values never surface:
    expect(JSON.stringify(row)).not.toContain("user_01ABCXYZ");
    expect(JSON.stringify(row)).not.toContain("203.0.113.7");
    expect(JSON.stringify(row)).not.toContain("Mozilla");
  });

  test("same session_sub → same user_hash within a day", async () => {
    const db = new FakeD1();
    const opts = { saltStore: fixedSaltStore, now: fixedNow() };
    await logAuthEvent(
      asD1(db),
      { worker: "magic-link", event_type: "magic_link.authorize", session_sub: "u1" },
      opts,
    );
    await logAuthEvent(
      asD1(db),
      {
        worker: "magic-link",
        event_type: "magic_link.callback.success",
        session_sub: "u1",
      },
      opts,
    );
    expect(db.events[0].user_hash).toBe(db.events[1].user_hash);
    expect(db.events[0].user_hash).not.toBeNull();
  });

  test("enforce=true → 1, enforce=false → 0, absent → null", async () => {
    const db = new FakeD1();
    const opts = { saltStore: fixedSaltStore, now: fixedNow() };
    await logAuthEvent(
      asD1(db),
      { worker: "edge-bouncer", event_type: "bouncer.pass.public", enforce: true },
      opts,
    );
    await logAuthEvent(
      asD1(db),
      { worker: "edge-bouncer", event_type: "bouncer.pass.public", enforce: false },
      opts,
    );
    await logAuthEvent(
      asD1(db),
      { worker: "edge-bouncer", event_type: "bouncer.pass.public" },
      opts,
    );
    expect(db.events.map((e) => e.enforce)).toEqual([1, 0, null]);
  });

  test("chain is well-formed across N writes", async () => {
    const db = new FakeD1();
    const opts = { saltStore: fixedSaltStore, now: fixedNow() };
    for (let i = 0; i < 5; i++) {
      await logAuthEvent(
        asD1(db),
        {
          worker: "edge-bouncer",
          event_type: "bouncer.pass.public",
          path: `/p${i}`,
        },
        opts,
      );
    }
    expect(db.events).toHaveLength(5);
    expect(db.events[0].prev_hash).toBe("genesis");
    for (let i = 1; i < 5; i++) {
      expect(db.events[i].prev_hash).toBe(db.events[i - 1].row_hash);
    }
    const report = await verifyChain({ all: async () => db.events });
    expect(report.violations).toEqual([]);
    expect(report.total_rows).toBe(5);
  });
});

describe("extractJwtSub", () => {
  test("returns sub from a well-formed JWT", () => {
    // header.payload.sig — payload base64url-encodes {"sub":"u_42"}
    const payload = btoa(JSON.stringify({ sub: "u_42" }))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    const jwt = `h.${payload}.s`;
    expect(extractJwtSub(jwt)).toBe("u_42");
  });

  test("returns undefined on malformed input", () => {
    expect(extractJwtSub("not-a-jwt")).toBeUndefined();
    expect(extractJwtSub("a.b")).toBeUndefined();
    expect(extractJwtSub("a.!!!.c")).toBeUndefined();
  });

  test("returns undefined when sub is missing", () => {
    const payload = btoa(JSON.stringify({ iss: "x" }))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    expect(extractJwtSub(`h.${payload}.s`)).toBeUndefined();
  });
});
