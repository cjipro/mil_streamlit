// MIL-70 — generate WorkOS Admin Portal setup links.
//
// WorkOS hosts the entire SSO/SAML/SCIM admin UI. We generate a
// short-lived (5min) link tied to a specific organization + intent,
// share it with the partner's IT team, they configure their IdP
// inside the WorkOS-hosted page. No SAML XML in our codebase.
//
// API: POST https://api.workos.com/portal/generate_link
//   body: { organization, intent, return_url? }
//   auth: Bearer WORKOS_API_KEY
//   response: { link: "https://..." }  // valid for 5 minutes
//
// The link's host is `setup.workos.com` (or the partner's custom
// admin-portal domain if they've configured one). The partner clicks
// → completes setup → WorkOS fires webhook events that our existing
// /webhooks/workos endpoint captures.

export type PortalIntent =
  | "sso"
  | "domain_verification"
  | "dsync"
  | "audit_logs"
  | "log_streams";

export interface GenerateLinkInput {
  organizationId: string;
  intent: PortalIntent;
  returnUrl?: string;
}

export type GenerateLinkResult =
  | { ok: true; link: string }
  | { ok: false; status: number; reason: string; detail?: string };

export async function generatePortalLink(
  apiKey: string,
  input: GenerateLinkInput,
  fetchImpl: typeof fetch = fetch,
): Promise<GenerateLinkResult> {
  if (!apiKey) {
    return { ok: false, status: 503, reason: "missing-api-key" };
  }
  if (!input.organizationId) {
    return { ok: false, status: 400, reason: "missing-organization-id" };
  }

  let res: Response;
  try {
    res = await fetchImpl("https://api.workos.com/portal/generate_link", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        organization: input.organizationId,
        intent: input.intent,
        ...(input.returnUrl ? { return_url: input.returnUrl } : {}),
      }),
    });
  } catch (e) {
    return {
      ok: false,
      status: 0,
      reason: "network-error",
      detail: e instanceof Error ? e.message : String(e),
    };
  }

  const rawText = await res.text();
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawText) as Record<string, unknown>;
  } catch {
    return {
      ok: false,
      status: res.status,
      reason: "non-json-body",
      detail: rawText.slice(0, 200),
    };
  }

  if (!res.ok) {
    const detail =
      typeof body.message === "string"
        ? body.message
        : typeof body.error === "string"
          ? body.error
          : rawText.slice(0, 200);
    return { ok: false, status: res.status, reason: "http-error", detail };
  }

  const link = body.link;
  if (typeof link !== "string" || link.length === 0) {
    return { ok: false, status: res.status, reason: "missing-link-field" };
  }
  return { ok: true, link };
}
