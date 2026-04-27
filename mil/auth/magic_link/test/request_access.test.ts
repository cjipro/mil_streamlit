// MIL-147 — /request-access pre-fill + form copy tests.
//
// renderRequestForm is a pure function over an opts object; readEmailParam
// is a pure function over URL. Both are tested end-to-end at the HTTP
// layer in index.test.ts; this file pins the unit-level behaviour.

import { describe, expect, test } from "vitest";
import { readEmailParam, renderRequestForm } from "../src/request_access";

describe("readEmailParam — URL ?email= sanitisation", () => {
  test("returns valid email", () => {
    const url = new URL("https://login.cjipro.com/request-access?email=alice%40barclays.com");
    expect(readEmailParam(url)).toBe("alice@barclays.com");
  });
  test("trims whitespace", () => {
    const url = new URL("https://login.cjipro.com/request-access?email=%20alice%40x.com%20");
    expect(readEmailParam(url)).toBe("alice@x.com");
  });
  test("returns undefined when missing", () => {
    const url = new URL("https://login.cjipro.com/request-access");
    expect(readEmailParam(url)).toBeUndefined();
  });
  test("returns undefined when empty", () => {
    const url = new URL("https://login.cjipro.com/request-access?email=");
    expect(readEmailParam(url)).toBeUndefined();
  });
  test("returns undefined on implausible email (no @)", () => {
    const url = new URL("https://login.cjipro.com/request-access?email=notanemail");
    expect(readEmailParam(url)).toBeUndefined();
  });
  test("returns undefined on >254-char value (RFC 5321 cap)", () => {
    const long = "a".repeat(250) + "@x.com";
    const url = new URL(`https://login.cjipro.com/request-access?email=${encodeURIComponent(long)}`);
    expect(readEmailParam(url)).toBeUndefined();
  });
  test("rejects XSS payload (no @)", () => {
    const url = new URL(
      `https://login.cjipro.com/request-access?email=${encodeURIComponent("<script>alert(1)</script>")}`,
    );
    expect(readEmailParam(url)).toBeUndefined();
  });
});

describe("renderRequestForm — email pre-fill", () => {
  test("renders email value when provided", async () => {
    const res = renderRequestForm({ email: "alice@barclays.com" });
    const html = await res.text();
    expect(html).toContain('value="alice@barclays.com"');
    expect(res.status).toBe(200);
  });
  test("renders empty value when no email provided", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    expect(html).toContain('value=""');
  });
  test("escapes HTML in pre-filled value (defence-in-depth)", async () => {
    // readEmailParam should reject this upstream, but the render layer
    // must not assume that. XSS-safe by escapeHtml.
    const res = renderRequestForm({ email: '"><script>alert(1)</script>' });
    const html = await res.text();
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
  test("does NOT include any firm-name field (Hua Li enumeration guard)", async () => {
    const res = renderRequestForm({ email: "alice@barclays.com" });
    const html = await res.text();
    expect(html).not.toMatch(/name="firm/i);
    expect(html).not.toMatch(/name="company/i);
    expect(html).not.toMatch(/name="organisation/i);
    expect(html).not.toMatch(/name="organization/i);
    // The pre-filled email is the ONLY firm-related signal.
    expect(html).not.toContain("Barclays"); // domain in value="alice@barclays.com" is the ONLY ref
  });
  test("renders the personal-review copy line", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    expect(html).toContain("We review every request personally");
    expect(html).toContain("Corporate email preferred but not required");
  });
  test("renders error when supplied", async () => {
    const res = renderRequestForm({ error: "That doesn't look right.", email: "bad" });
    const html = await res.text();
    expect(html).toContain("That doesn&#39;t look right.");
    expect(res.status).toBe(400);
  });
  test("noindex meta — utility surface, not for search engines", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    expect(html).toContain('name="robots" content="noindex,nofollow"');
  });
});

describe("renderRequestForm — MIL-139 a11y contract", () => {
  test("email input is programmatically labelled and described", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    // <label for="email"> + <input id="email"> association
    expect(html).toMatch(/<label for="email">/);
    expect(html).toMatch(/<input id="email"/);
    // Email field describes its purpose via aria-describedby → #email-help
    expect(html).toContain('aria-describedby="email-help"');
    expect(html).toContain('id="email-help"');
  });

  test("error renders inside role=alert live region with id linked from input", async () => {
    const res = renderRequestForm({ error: "Bad email", email: "x" });
    const html = await res.text();
    // Error gets its own id and lives in a role=alert region for SR announcement
    expect(html).toContain('id="email-err"');
    expect(html).toContain('role="alert"');
    // Input now describes BOTH help text AND error
    expect(html).toContain('aria-describedby="email-help email-err"');
    // Visible error styling cue is also wired via aria-invalid
    expect(html).toContain('aria-invalid="true"');
  });

  test("aria-invalid omitted from <input> when no error — clean state on first paint", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    // The CSS contains `input[aria-invalid="true"]` as a selector; we
    // care that the input ELEMENT doesn't carry the attribute on first
    // paint, not that the substring is absent globally.
    const inputTag = html.match(/<input id="email"[\s\S]*?>/);
    expect(inputTag).not.toBeNull();
    expect(inputTag![0]).not.toContain("aria-invalid");
  });

  test("focus-visible CSS rules present (no outline:none reset anywhere)", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    expect(html).toContain(":focus-visible");
    expect(html).not.toMatch(/outline\s*:\s*none/);
  });

  test("inputmode=email + spellcheck=false on email input (mobile keyboard hint)", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    expect(html).toContain('inputmode="email"');
    expect(html).toContain('spellcheck="false"');
  });

  test("form has novalidate so we own the error UX (matches role=alert path)", async () => {
    const res = renderRequestForm();
    const html = await res.text();
    // Browser-default tooltip would steal SR focus from our role=alert.
    expect(html).toContain('novalidate');
  });
});
