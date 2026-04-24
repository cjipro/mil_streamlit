import { describe, expect, test } from "vitest";
import { checkAndIncrement, windowKey } from "../src/rate_limit";
import { FakeD1, asD1 } from "./fake_d1";

describe("windowKey", () => {
  test("produces YYYY-MM-DDTHH in UTC", () => {
    const d = new Date("2026-04-24T14:37:12.000Z");
    expect(windowKey(d)).toBe("2026-04-24T14");
  });

  test("pads all components", () => {
    const d = new Date("2026-01-02T03:04:05.000Z");
    expect(windowKey(d)).toBe("2026-01-02T03");
  });

  test("crosses hour boundary cleanly", () => {
    const a = new Date("2026-04-24T14:59:59.000Z");
    const b = new Date("2026-04-24T15:00:00.000Z");
    expect(windowKey(a)).toBe("2026-04-24T14");
    expect(windowKey(b)).toBe("2026-04-24T15");
  });
});

describe("checkAndIncrement", () => {
  const NOW = new Date("2026-04-24T14:00:00.000Z");

  test("first N requests are allowed, N+1 is denied", async () => {
    const db = new FakeD1();
    for (let i = 0; i < 5; i++) {
      expect(
        await checkAndIncrement(asD1(db), "ip_alpha", NOW),
      ).toBe(true);
    }
    expect(
      await checkAndIncrement(asD1(db), "ip_alpha", NOW),
    ).toBe(false);
  });

  test("different IPs have independent budgets", async () => {
    const db = new FakeD1();
    for (let i = 0; i < 5; i++) {
      await checkAndIncrement(asD1(db), "ip_alpha", NOW);
    }
    // alpha is now blocked, bravo still fresh
    expect(await checkAndIncrement(asD1(db), "ip_alpha", NOW)).toBe(false);
    expect(await checkAndIncrement(asD1(db), "ip_bravo", NOW)).toBe(true);
  });

  test("window reset clears the limit", async () => {
    const db = new FakeD1();
    for (let i = 0; i < 5; i++) {
      await checkAndIncrement(asD1(db), "ip_alpha", NOW);
    }
    expect(await checkAndIncrement(asD1(db), "ip_alpha", NOW)).toBe(false);
    const nextHour = new Date("2026-04-24T15:00:00.000Z");
    expect(await checkAndIncrement(asD1(db), "ip_alpha", nextHour)).toBe(true);
  });

  test("absent ipHash → allow (don't deny on header quirks)", async () => {
    const db = new FakeD1();
    expect(await checkAndIncrement(asD1(db), undefined, NOW)).toBe(true);
    expect(await checkAndIncrement(asD1(db), null, NOW)).toBe(true);
    expect(await checkAndIncrement(asD1(db), "", NOW)).toBe(true);
  });

  test("custom maxPerWindow", async () => {
    const db = new FakeD1();
    const cfg = { maxPerWindow: 2, windowFormat: "hour" as const };
    expect(await checkAndIncrement(asD1(db), "ip_a", NOW, cfg)).toBe(true);
    expect(await checkAndIncrement(asD1(db), "ip_a", NOW, cfg)).toBe(true);
    expect(await checkAndIncrement(asD1(db), "ip_a", NOW, cfg)).toBe(false);
  });
});
