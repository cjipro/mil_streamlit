import { describe, expect, test } from "vitest";
import { logAuthEvent } from "../src/audit";
import { verifyChain } from "../src/verify";
import { FakeD1, asD1 } from "./fake_d1";

const FIXED_SALT = "b".repeat(64);
const fixedSaltStore = {
  async getOrCreate(_: string): Promise<string> {
    return FIXED_SALT;
  },
};
const fixedNow = new Date("2026-04-24T00:00:00.000Z");

async function buildChain(db: FakeD1, n: number): Promise<void> {
  for (let i = 0; i < n; i++) {
    await logAuthEvent(
      asD1(db),
      {
        worker: "edge-bouncer",
        event_type: "bouncer.pass.public",
        path: `/p${i}`,
      },
      { saltStore: fixedSaltStore, now: fixedNow },
    );
  }
}

describe("verifyChain", () => {
  test("clean chain yields zero violations", async () => {
    const db = new FakeD1();
    await buildChain(db, 4);
    const report = await verifyChain({ all: async () => db.events });
    expect(report.violations).toHaveLength(0);
    expect(report.total_rows).toBe(4);
    expect(report.last_id).toBe(4);
  });

  test("empty chain is trivially clean", async () => {
    const report = await verifyChain({ all: async () => [] });
    expect(report.violations).toHaveLength(0);
    expect(report.total_rows).toBe(0);
    expect(report.last_id).toBeNull();
  });

  test("row mutation triggers row-hash-mismatch", async () => {
    const db = new FakeD1();
    await buildChain(db, 3);
    // Tamper with the middle row's path — row_hash no longer matches.
    db.events[1] = { ...db.events[1], path: "/tampered" };
    const report = await verifyChain({ all: async () => db.events });
    const kinds = report.violations.map((v) => v.kind);
    expect(kinds).toContain("row-hash-mismatch");
  });

  test("row deletion triggers chain-break", async () => {
    const db = new FakeD1();
    await buildChain(db, 4);
    const trimmed = [db.events[0], db.events[2], db.events[3]];
    const report = await verifyChain({ all: async () => trimmed });
    const kinds = report.violations.map((v) => v.kind);
    expect(kinds).toContain("chain-break");
  });

  test("reorder triggers chain-break + row-hash-mismatch", async () => {
    const db = new FakeD1();
    await buildChain(db, 4);
    const swapped = [db.events[0], db.events[2], db.events[1], db.events[3]];
    const report = await verifyChain({ all: async () => swapped });
    expect(report.violations.length).toBeGreaterThan(0);
    expect(report.violations.map((v) => v.kind)).toContain("chain-break");
  });

  test("genesis missing is surfaced distinctly", async () => {
    const db = new FakeD1();
    await buildChain(db, 2);
    // Drop the genesis row; now the first surviving row's prev_hash
    // points to a row that isn't in the stream.
    const trimmed = [db.events[1]];
    const report = await verifyChain({ all: async () => trimmed });
    expect(report.violations.some((v) => v.kind === "genesis-missing")).toBe(true);
  });
});
