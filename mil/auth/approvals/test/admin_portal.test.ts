import { describe, expect, test } from "vitest";
import { generatePortalLink } from "../src/admin_portal";

const KEY = "sk_test_example";
const ORG = "org_01HXYZABC";

function stubFetch(
  status: number,
  body: unknown,
  capture?: { calls: { url: string; init?: RequestInit }[] },
): typeof fetch {
  return (async (url: string, init?: RequestInit) => {
    capture?.calls.push({ url, init });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
}

describe("generatePortalLink", () => {
  test("happy path returns link", async () => {
    const fetchStub = stubFetch(200, {
      link: "https://setup.workos.com/portal/abc123",
    });
    const r = await generatePortalLink(
      KEY,
      { organizationId: ORG, intent: "sso" },
      fetchStub,
    );
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.link).toBe("https://setup.workos.com/portal/abc123");
  });

  test("missing api key → 503", async () => {
    const r = await generatePortalLink("", {
      organizationId: ORG,
      intent: "sso",
    });
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.status).toBe(503);
      expect(r.reason).toBe("missing-api-key");
    }
  });

  test("missing organization → 400", async () => {
    const r = await generatePortalLink(
      KEY,
      { organizationId: "", intent: "sso" },
      stubFetch(200, {}),
    );
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.status).toBe(400);
      expect(r.reason).toBe("missing-organization-id");
    }
  });

  test("WorkOS HTTP error surfaced", async () => {
    const fetchStub = stubFetch(404, { message: "Organization not found" });
    const r = await generatePortalLink(
      KEY,
      { organizationId: ORG, intent: "sso" },
      fetchStub,
    );
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.status).toBe(404);
      expect(r.reason).toBe("http-error");
      expect(r.detail).toContain("not found");
    }
  });

  test("missing link field in 200 response → reason mismatch", async () => {
    const fetchStub = stubFetch(200, { other: "stuff" });
    const r = await generatePortalLink(
      KEY,
      { organizationId: ORG, intent: "sso" },
      fetchStub,
    );
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe("missing-link-field");
  });

  test("authorization header carries Bearer + key", async () => {
    const capture = { calls: [] as { url: string; init?: RequestInit }[] };
    const fetchStub = stubFetch(
      200,
      { link: "https://x" },
      capture,
    );
    await generatePortalLink(
      KEY,
      { organizationId: ORG, intent: "sso" },
      fetchStub,
    );
    expect(capture.calls).toHaveLength(1);
    const headers = capture.calls[0].init?.headers as Record<string, string>;
    expect(headers.authorization).toBe(`Bearer ${KEY}`);
  });

  test("body includes organization + intent + optional return_url", async () => {
    const capture = { calls: [] as { url: string; init?: RequestInit }[] };
    const fetchStub = stubFetch(200, { link: "https://x" }, capture);
    await generatePortalLink(
      KEY,
      {
        organizationId: ORG,
        intent: "dsync",
        returnUrl: "https://login.cjipro.com/admin",
      },
      fetchStub,
    );
    const body = JSON.parse(capture.calls[0].init?.body as string);
    expect(body.organization).toBe(ORG);
    expect(body.intent).toBe("dsync");
    expect(body.return_url).toBe("https://login.cjipro.com/admin");
  });

  test("network error surfaces gracefully", async () => {
    const fetchStub = (async () => {
      throw new Error("ECONNREFUSED");
    }) as typeof fetch;
    const r = await generatePortalLink(
      KEY,
      { organizationId: ORG, intent: "sso" },
      fetchStub,
    );
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe("network-error");
      expect(r.detail).toContain("ECONNREFUSED");
    }
  });
});
