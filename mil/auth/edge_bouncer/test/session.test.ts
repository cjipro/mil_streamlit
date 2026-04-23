import { describe, expect, test } from "vitest";
import { extractCookie } from "../src/session";

describe("extractCookie", () => {
  test("returns null on no header", () => {
    expect(extractCookie(null, "x")).toBeNull();
  });

  test("finds a single cookie", () => {
    expect(extractCookie("foo=bar", "foo")).toBe("bar");
  });

  test("finds the right cookie among many", () => {
    const h = "a=1; b=2; __Secure-cjipro-session=abc.def.ghi; c=3";
    expect(extractCookie(h, "__Secure-cjipro-session")).toBe("abc.def.ghi");
  });

  test("does not match substring of a different cookie name", () => {
    const h = "__Secure-cjipro-session-legacy=xxx";
    expect(extractCookie(h, "__Secure-cjipro-session")).toBeNull();
  });

  test("handles values containing '='", () => {
    const h = "token=a=b=c";
    expect(extractCookie(h, "token")).toBe("a=b=c");
  });

  test("ignores malformed segments without '='", () => {
    const h = "malformed; real=value";
    expect(extractCookie(h, "real")).toBe("value");
  });

  test("is case-sensitive on cookie name (matches RFC 6265)", () => {
    const h = "Foo=bar";
    expect(extractCookie(h, "foo")).toBeNull();
  });
});
