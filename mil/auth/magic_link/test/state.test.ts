import { describe, expect, test } from "vitest";
import { isValidReturnTo, signState, verifyState } from "../src/state";

const SECRET = "test-signing-key-0123456789abcdef";

describe("signState / verifyState roundtrip", () => {
  test("valid signed state verifies", async () => {
    const state = await signState(
      { returnTo: "/briefing-v4/", ts: Date.now() },
      SECRET,
    );
    const r = await verifyState(state, SECRET);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload.returnTo).toBe("/briefing-v4/");
    }
  });

  test("wrong secret rejects", async () => {
    const state = await signState(
      { returnTo: "/briefing-v4/", ts: Date.now() },
      SECRET,
    );
    const r = await verifyState(state, "different-secret");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("bad-signature");
  });

  test("tampered payload rejects", async () => {
    const state = await signState(
      { returnTo: "/briefing-v4/", ts: Date.now() },
      SECRET,
    );
    // Swap body portion with a different (unsigned) payload.
    const [, sig] = state.split(".");
    const evilBody = btoa(JSON.stringify({ returnTo: "/admin", ts: Date.now() }))
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
    const tampered = `${evilBody}.${sig}`;
    const r = await verifyState(tampered, SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("bad-signature");
  });

  test("expired state rejects", async () => {
    const oldTs = Date.now() - 11 * 60 * 1000;
    const state = await signState({ returnTo: "/", ts: oldTs }, SECRET);
    const r = await verifyState(state, SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("expired");
  });

  test("malformed state rejects — no dot", async () => {
    const r = await verifyState("no-dot-here", SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("malformed");
  });

  test("malformed state rejects — garbage base64", async () => {
    const r = await verifyState("@@@.@@@", SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok)
      expect(["malformed", "bad-signature"]).toContain(r.reason);
  });

  test("non-schema payload rejects", async () => {
    // Handcraft a validly-signed but schema-invalid payload.
    const { signState: s } = await import("../src/state");
    // Sign a payload that JSON-parses but lacks returnTo/ts types.
    const payloadBytes = new TextEncoder().encode(
      JSON.stringify({ returnTo: 42, ts: "nope" }),
    );
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const sig = await crypto.subtle.sign("HMAC", key, payloadBytes);
    const b64 = (bytes: Uint8Array) =>
      btoa(String.fromCharCode(...bytes))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replaceAll("=", "");
    const forged = `${b64(payloadBytes)}.${b64(new Uint8Array(sig))}`;
    const r = await verifyState(forged, SECRET);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("malformed");
    // Reference `s` to silence unused-import lint
    expect(typeof s).toBe("function");
  });

  test("custom maxAge honours caller", async () => {
    const ts = Date.now() - 5000;
    const state = await signState({ returnTo: "/", ts }, SECRET);
    const short = await verifyState(state, SECRET, Date.now(), 1000);
    expect(short.ok).toBe(false);
    const long = await verifyState(state, SECRET, Date.now(), 60_000);
    expect(long.ok).toBe(true);
  });
});

describe("isValidReturnTo", () => {
  test("accepts path-only URLs", () => {
    expect(isValidReturnTo("/")).toBe(true);
    expect(isValidReturnTo("/briefing-v4/")).toBe(true);
    expect(isValidReturnTo("/ask?q=hello")).toBe(true);
  });

  test("rejects protocol-relative URLs (open-redirect vector)", () => {
    expect(isValidReturnTo("//evil.example.com/steal")).toBe(false);
  });

  test("accepts absolute URLs on allowlisted cjipro hosts", () => {
    expect(isValidReturnTo("https://cjipro.com/briefing/")).toBe(true);
    expect(isValidReturnTo("https://app.cjipro.com/sonar/barclays/")).toBe(true);
    expect(isValidReturnTo("https://admin.cjipro.com/admin")).toBe(true);
    expect(isValidReturnTo("https://login.cjipro.com/admin")).toBe(true);
  });

  test("rejects absolute URLs on non-allowlisted hosts", () => {
    expect(isValidReturnTo("https://evil.example.com/")).toBe(false);
    expect(isValidReturnTo("https://malicious-cjipro.com/")).toBe(false);
    expect(isValidReturnTo("https://cjipro.com.evil.com/")).toBe(false);
  });

  test("rejects non-https schemes on otherwise allowlisted hosts", () => {
    expect(isValidReturnTo("http://cjipro.com/")).toBe(false);
    expect(isValidReturnTo("javascript:alert(1)")).toBe(false);
    expect(isValidReturnTo("data:text/html,evil")).toBe(false);
  });

  test("rejects path-traversal-looking paths", () => {
    expect(isValidReturnTo("/../admin")).toBe(false);
  });

  test("rejects empty / non-string", () => {
    expect(isValidReturnTo("")).toBe(false);
    // @ts-expect-error — runtime guard for non-string inputs
    expect(isValidReturnTo(undefined)).toBe(false);
    // @ts-expect-error
    expect(isValidReturnTo(null)).toBe(false);
  });
});
