// MIL-146 — forwarded magic-link heuristic: pure-logic tests.
//
// Acceptance contract from the ticket:
//   same context           -> not forwarded
//   different IP, same UA  -> forwarded
//   same IP, different UA  -> forwarded
//   different both         -> forwarded
//
// Plus tests for the underlying helpers (ipClass + uaFamily) so future
// edits to either don't silently break the heuristic.

import { describe, expect, test } from "vitest";
import {
  ipClass,
  uaFamily,
  looksForwarded,
} from "../src/forward_detect";

const CHROME_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const FIREFOX_UA =
  "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0";
const SAFARI_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const EDGE_UA =
  "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0";

describe("ipClass — IPv4", () => {
  test("zeroes the last octet (/24)", () => {
    expect(ipClass("203.0.113.42")).toBe("203.0.113.0");
  });
  test("two distinct hosts in same /24 collapse to same class", () => {
    expect(ipClass("203.0.113.42")).toBe(ipClass("203.0.113.99"));
  });
  test("hosts in different /24 produce different classes", () => {
    expect(ipClass("203.0.113.42")).not.toBe(ipClass("203.0.114.42"));
  });
  test("malformed IP returned as-is rather than crashing", () => {
    expect(ipClass("not.an.ip")).toBe("not.an.ip");
    expect(ipClass("1.2.3")).toBe("1.2.3");
  });
});

describe("ipClass — IPv6", () => {
  test("collapses to /64 prefix", () => {
    expect(ipClass("2001:db8:abcd:1234:5678:9abc:def0:1234")).toBe(
      "2001:db8:abcd:1234::",
    );
  });
  test("two hosts in same /64 collapse equal", () => {
    const a = ipClass("2001:db8:abcd:1234::1");
    const b = ipClass("2001:db8:abcd:1234::99");
    expect(a).toBe(b);
  });
});

describe("ipClass — empty/null", () => {
  test("returns empty string", () => {
    expect(ipClass(null)).toBe("");
    expect(ipClass(undefined)).toBe("");
    expect(ipClass("")).toBe("");
  });
});

describe("uaFamily", () => {
  test("Chrome", () => expect(uaFamily(CHROME_UA)).toBe("chrome"));
  test("Firefox", () => expect(uaFamily(FIREFOX_UA)).toBe("firefox"));
  test("Safari (mobile)", () => expect(uaFamily(SAFARI_UA)).toBe("safari"));
  test("Edge wins over chrome — must check Edg/ first", () => {
    // The Edge UA contains "Chrome/120" too — order matters in the impl.
    expect(uaFamily(EDGE_UA)).toBe("edge");
  });
  test("unknown UA → other", () => {
    expect(uaFamily("curl/8.4.0")).toBe("other");
  });
  test("empty UA → other", () => {
    expect(uaFamily("")).toBe("other");
    expect(uaFamily(null)).toBe("other");
  });
});

describe("looksForwarded — acceptance contract", () => {
  test("same context → not forwarded", () => {
    const r = looksForwarded("203.0.113.42", CHROME_UA, "203.0.113.42", CHROME_UA);
    expect(r.forwarded).toBe(false);
    expect(r.ip_changed).toBe(false);
    expect(r.ua_changed).toBe(false);
  });

  test("different IP /24, same UA family → forwarded", () => {
    // 203.0.113.x vs 198.51.100.y — different /24
    const r = looksForwarded(
      "203.0.113.42",
      CHROME_UA,
      "198.51.100.99",
      CHROME_UA,
    );
    expect(r.forwarded).toBe(true);
    expect(r.ip_changed).toBe(true);
    expect(r.ua_changed).toBe(false);
  });

  test("same IP /24, different UA family → forwarded", () => {
    const r = looksForwarded(
      "203.0.113.42",
      CHROME_UA,
      "203.0.113.99",
      FIREFOX_UA,
    );
    expect(r.forwarded).toBe(true);
    expect(r.ip_changed).toBe(false);
    expect(r.ua_changed).toBe(true);
  });

  test("different IP and different UA → forwarded", () => {
    const r = looksForwarded(
      "203.0.113.42",
      CHROME_UA,
      "198.51.100.7",
      SAFARI_UA,
    );
    expect(r.forwarded).toBe(true);
    expect(r.ip_changed).toBe(true);
    expect(r.ua_changed).toBe(true);
  });
});

describe("looksForwarded — robustness", () => {
  test("two hosts in same /24 are NOT flagged (corp NAT)", () => {
    // Two Barclays employees behind the same office NAT click the same
    // forwarded link. /24 collapse means the heuristic doesn't false-
    // positive on intra-corp forwards.
    const r = looksForwarded("10.0.5.42", CHROME_UA, "10.0.5.99", CHROME_UA);
    expect(r.forwarded).toBe(false);
  });

  test("missing original context → never fires (older state, no false alarm)", () => {
    const r = looksForwarded(undefined, undefined, "203.0.113.99", CHROME_UA);
    expect(r.forwarded).toBe(false);
    expect(r.ip_changed).toBe(false);
    expect(r.ua_changed).toBe(false);
  });

  test("two Chrome versions on different OSes still match (UA family stable)", () => {
    const macChrome = CHROME_UA;
    const winChrome =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36";
    const r = looksForwarded("203.0.113.42", macChrome, "203.0.113.42", winChrome);
    expect(r.forwarded).toBe(false);
  });
});
