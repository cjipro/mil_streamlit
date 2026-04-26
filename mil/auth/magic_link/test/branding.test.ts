// MIL-138 — user-facing branding regression guards.
//
// The login.cjipro.com Worker emits HTML on a few surfaces (error page,
// request-access form). These tests lock in two invariants:
//
//   1. No third-party brand name ("WorkOS" / "AuthKit") leaks into
//      user-visible HTML. Internal code comments are exempt.
//   2. The brand string is "CJI" (locked 2026-04-25), never the
//      historical "CJI Pro" that has now been retired.
//
// renderErrorPage also gets a friendly-message-mapping check: known
// reason codes must produce a human sentence, unknown codes must fall
// back to a generic one — the raw enum must never appear in HTML.

import { describe, expect, test } from "vitest";
import { REASON_MESSAGES, renderErrorPage } from "../src/index";
import { renderRequestForm } from "../src/request_access";

async function bodyOf(res: Response): Promise<string> {
  return await res.text();
}

describe("renderErrorPage — MIL-138 branding + reason mapping", () => {
  test("contains no WorkOS or AuthKit string anywhere in HTML", async () => {
    for (const reason of Object.keys(REASON_MESSAGES)) {
      const html = await bodyOf(renderErrorPage(400, reason));
      expect(html).not.toMatch(/WorkOS/i);
      expect(html).not.toMatch(/AuthKit/i);
      expect(html).not.toMatch(/authkit\.app/i);
    }
    // Also exercise an unknown reason — the fallback path must be clean too.
    const fallback = await bodyOf(renderErrorPage(500, "totally-unknown"));
    expect(fallback).not.toMatch(/WorkOS/i);
    expect(fallback).not.toMatch(/AuthKit/i);
  });

  test("uses CJI (not CJI Pro) in title and copy", async () => {
    const html = await bodyOf(renderErrorPage(400, "auth-error"));
    expect(html).toContain("<title>Sign-in error · CJI</title>");
    expect(html).not.toMatch(/CJI Pro/);
  });

  test("renders a friendly human message for known reason codes", async () => {
    const html = await bodyOf(renderErrorPage(400, "auth-error"));
    expect(html).toContain("Your sign-in didn't complete.");
    // Internal code must not appear as raw text or in a <code> tag.
    expect(html).not.toMatch(/<code>auth-error<\/code>/);
    expect(html).not.toMatch(/Reason: auth-error/);
  });

  test("falls back to generic message for unknown reason codes", async () => {
    const html = await bodyOf(renderErrorPage(500, "totally-unknown"));
    expect(html).toContain("We couldn't complete your sign-in.");
    // The raw code is suppressed — it must not surface to the user.
    expect(html).not.toMatch(/totally-unknown/);
  });
});

describe("renderRequestForm — MIL-138 branding", () => {
  test("contains no WorkOS / AuthKit / CJI Pro strings", async () => {
    const html = await bodyOf(renderRequestForm());
    expect(html).not.toMatch(/WorkOS/i);
    expect(html).not.toMatch(/AuthKit/i);
    expect(html).not.toMatch(/authkit\.app/i);
    expect(html).not.toMatch(/CJI Pro/);
    // Positive: the brand is present in the locked form.
    expect(html).toContain("CJI");
  });
});
