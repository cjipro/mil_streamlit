import { describe, expect, test } from "vitest";
import { isPublic, parsePatterns } from "../src/whitelist";

// Mirrors wrangler.toml default. If this string drifts, tests fail
// and the drift is obvious.
const DEFAULT =
  "=/,=/privacy,=/privacy/,^/.well-known/,=/robots.txt,=/sitemap.xml,=/.nojekyll";

describe("parsePatterns", () => {
  test("parses exact, prefix, and bare tokens", () => {
    expect(parsePatterns("=/a,^/b/,/c")).toEqual([
      { kind: "exact", value: "/a" },
      { kind: "prefix", value: "/b/" },
      { kind: "prefix", value: "/c" },
    ]);
  });

  test("ignores empty segments and whitespace", () => {
    expect(parsePatterns(" ,=/a, ,^/b/ ")).toEqual([
      { kind: "exact", value: "/a" },
      { kind: "prefix", value: "/b/" },
    ]);
  });
});

describe("isPublic — default public paths", () => {
  const matchers = parsePatterns(DEFAULT);

  test("/ root matches exactly", () => {
    expect(isPublic("/", matchers)).toBe(true);
  });

  test("exact /privacy and /privacy/ match", () => {
    expect(isPublic("/privacy", matchers)).toBe(true);
    expect(isPublic("/privacy/", matchers)).toBe(true);
  });

  test("/.well-known/security.txt matches via prefix", () => {
    expect(isPublic("/.well-known/security.txt", matchers)).toBe(true);
    expect(isPublic("/.well-known/", matchers)).toBe(true);
  });

  test("robots.txt + sitemap.xml + .nojekyll match exactly", () => {
    expect(isPublic("/robots.txt", matchers)).toBe(true);
    expect(isPublic("/sitemap.xml", matchers)).toBe(true);
    expect(isPublic("/.nojekyll", matchers)).toBe(true);
  });

  test("gated briefing paths do NOT match", () => {
    expect(isPublic("/briefing", matchers)).toBe(false);
    expect(isPublic("/briefing-v4/", matchers)).toBe(false);
    expect(isPublic("/briefing-v4/index.html", matchers)).toBe(false);
  });

  test("privacy suffix variants do NOT match unexpectedly", () => {
    expect(isPublic("/privacy-leak", matchers)).toBe(false);
    expect(isPublic("/privacyx", matchers)).toBe(false);
  });

  test("root-adjacent paths do NOT match", () => {
    expect(isPublic("/dashboard", matchers)).toBe(false);
    expect(isPublic("/ask", matchers)).toBe(false);
  });
});

describe("isPublic — empty pattern list denies everything", () => {
  const matchers = parsePatterns("");
  test("nothing matches", () => {
    expect(isPublic("/", matchers)).toBe(false);
    expect(isPublic("/privacy", matchers)).toBe(false);
  });
});
