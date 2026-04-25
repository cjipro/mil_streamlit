import { describe, expect, test } from "vitest";
import { verifyWorkosWebhook } from "../src/webhooks";

const SECRET = "whsec_test_0123456789abcdef0123456789abcdef";
const FROZEN_TS = 1777068000; // 2026-04-25T01:20:00Z
const NOW = () => FROZEN_TS;

async function hmacHex(secret: string, payload: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  const view = new Uint8Array(sig);
  let out = "";
  for (let i = 0; i < view.length; i++)
    out += view[i].toString(16).padStart(2, "0");
  return out;
}

function eventBody(): string {
  return JSON.stringify({
    id: "evt_01HABCDEFG",
    event: "user.created",
    data: { user: { id: "u_01XYZ" } },
    created_at: "2026-04-25T01:20:00Z",
  });
}

async function signedHeader(ts: number, body: string): Promise<string> {
  const sig = await hmacHex(SECRET, `${ts}.${body}`);
  return `t=${ts},v1=${sig}`;
}

describe("verifyWorkosWebhook", () => {
  test("valid signature within window → ok", async () => {
    const body = eventBody();
    const header = await signedHeader(FROZEN_TS, body);
    const r = await verifyWorkosWebhook(body, header, { secret: SECRET, now: NOW });
    expect(r.kind).toBe("ok");
    if (r.kind === "ok") {
      expect(r.rawType).toBe("user.created");
      expect(r.rawId).toBe("evt_01HABCDEFG");
    }
  });

  test("missing secret → 503", async () => {
    const body = eventBody();
    const header = await signedHeader(FROZEN_TS, body);
    const r = await verifyWorkosWebhook(body, header, { secret: "", now: NOW });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") {
      expect(r.status).toBe(503);
      expect(r.reason).toBe("missing-secret");
    }
  });

  test("missing signature header → 401", async () => {
    const r = await verifyWorkosWebhook(eventBody(), null, { secret: SECRET });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.status).toBe(401);
  });

  test("malformed header → 401", async () => {
    const r = await verifyWorkosWebhook(eventBody(), "garbage", {
      secret: SECRET,
      now: NOW,
    });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toBe("malformed-signature-header");
  });

  test("non-numeric timestamp → 401", async () => {
    const r = await verifyWorkosWebhook(
      eventBody(),
      "t=notanumber,v1=deadbeef",
      { secret: SECRET, now: NOW },
    );
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toBe("non-numeric-timestamp");
  });

  test("timestamp older than 5min → replay rejected", async () => {
    const body = eventBody();
    const oldTs = FROZEN_TS - 600;
    const header = await signedHeader(oldTs, body);
    const r = await verifyWorkosWebhook(body, header, { secret: SECRET, now: NOW });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toMatch(/^replay-window-exceeded/);
  });

  test("timestamp newer than now+5min → also rejected", async () => {
    const body = eventBody();
    const futureTs = FROZEN_TS + 600;
    const header = await signedHeader(futureTs, body);
    const r = await verifyWorkosWebhook(body, header, { secret: SECRET, now: NOW });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toMatch(/^replay-window-exceeded/);
  });

  test("body tampered after signing → signature mismatch", async () => {
    const realBody = eventBody();
    const header = await signedHeader(FROZEN_TS, realBody);
    const tampered = realBody.replace("user.created", "user.deleted");
    const r = await verifyWorkosWebhook(tampered, header, {
      secret: SECRET,
      now: NOW,
    });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toBe("signature-mismatch");
  });

  test("wrong secret → signature mismatch", async () => {
    const body = eventBody();
    const header = await signedHeader(FROZEN_TS, body);
    const r = await verifyWorkosWebhook(body, header, {
      secret: "wrong",
      now: NOW,
    });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toBe("signature-mismatch");
  });

  test("non-JSON body → 400", async () => {
    const garbage = "not json {{{";
    const header = await signedHeader(FROZEN_TS, garbage);
    const r = await verifyWorkosWebhook(garbage, header, {
      secret: SECRET,
      now: NOW,
    });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toBe("non-json-body");
  });

  test("missing required event fields → 400", async () => {
    const body = JSON.stringify({ event: "user.created" }); // no id, no data
    const header = await signedHeader(FROZEN_TS, body);
    const r = await verifyWorkosWebhook(body, header, {
      secret: SECRET,
      now: NOW,
    });
    expect(r.kind).toBe("rejected");
    if (r.kind === "rejected") expect(r.reason).toBe("missing-event-fields");
  });
});
