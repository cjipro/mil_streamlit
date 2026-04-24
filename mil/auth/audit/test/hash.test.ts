import { describe, expect, test } from "vitest";
import { canonicalJson, hashRow, recomputeRowHash, sha256Hex } from "../src/hash";
import type { AuthEventRow } from "../src/types";

describe("sha256Hex", () => {
  test("empty string has known digest", async () => {
    const h = await sha256Hex("");
    expect(h).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  test("abc has known digest", async () => {
    const h = await sha256Hex("abc");
    expect(h).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  test("lowercase hex, 64 chars", async () => {
    const h = await sha256Hex("arbitrary input");
    expect(h).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("canonicalJson", () => {
  test("sorts keys lexicographically", () => {
    expect(canonicalJson({ b: 1, a: 2 })).toBe('{"a":2,"b":1}');
  });

  test("is stable across object literal order", () => {
    const a = canonicalJson({ b: 1, a: 2, c: 3 });
    const b = canonicalJson({ c: 3, a: 2, b: 1 });
    expect(a).toBe(b);
  });

  test("nulls pass through", () => {
    expect(canonicalJson({ x: null })).toBe('{"x":null}');
  });

  test("strings are JSON-escaped", () => {
    expect(canonicalJson({ s: 'a"b' })).toBe('{"s":"a\\"b"}');
  });

  test("rejects arrays", () => {
    expect(() => canonicalJson({ xs: [1, 2] })).toThrow();
  });

  test("rejects non-finite numbers", () => {
    expect(() => canonicalJson({ n: Infinity })).toThrow();
    expect(() => canonicalJson({ n: NaN })).toThrow();
  });
});

describe("hashRow", () => {
  test("same content + same prev → same hash", async () => {
    const content = { ts: "2026-04-24T00:00:00Z", worker: "edge-bouncer" };
    const a = await hashRow(content, "genesis");
    const b = await hashRow(content, "genesis");
    expect(a).toBe(b);
  });

  test("different prev → different hash", async () => {
    const content = { ts: "2026-04-24T00:00:00Z", worker: "edge-bouncer" };
    const a = await hashRow(content, "genesis");
    const b = await hashRow(content, "abc");
    expect(a).not.toBe(b);
  });

  test("missing columns get filled with null (not undefined)", async () => {
    const a = await hashRow({ ts: "t" }, "genesis");
    const b = await hashRow({ ts: "t", worker: null }, "genesis");
    expect(a).toBe(b);
  });
});

describe("recomputeRowHash", () => {
  test("matches hashRow for an equivalent content record", async () => {
    const row: AuthEventRow = {
      id: 1,
      ts: "2026-04-24T00:00:00.000Z",
      worker: "edge-bouncer",
      event_type: "bouncer.pass.public",
      method: "GET",
      host: "cjipro.com",
      path: "/",
      enforce: 0,
      user_hash: null,
      ip_hash: null,
      ua_hash: null,
      country: null,
      reason: null,
      detail: null,
      prev_hash: "genesis",
      row_hash: "ignored",
    };
    const viaRecompute = await recomputeRowHash(row);
    const viaHash = await hashRow(
      {
        ts: row.ts,
        worker: row.worker,
        event_type: row.event_type,
        method: row.method,
        host: row.host,
        path: row.path,
        enforce: row.enforce,
        user_hash: row.user_hash,
        ip_hash: row.ip_hash,
        ua_hash: row.ua_hash,
        country: row.country,
        reason: row.reason,
        detail: row.detail,
      },
      row.prev_hash,
    );
    expect(viaRecompute).toBe(viaHash);
  });
});
