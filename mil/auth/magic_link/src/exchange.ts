// MIL-63 — exchange AuthKit authorization code for a session
//
// WorkOS User Management authenticate endpoint:
//   POST https://api.workos.com/user_management/authenticate
//   Content-Type: application/json
//   {
//     "grant_type": "authorization_code",
//     "code": "<from callback>",
//     "client_id": "<client_id>",
//     "client_secret": "<API secret>"
//   }
//
// Response body is the authenticated session. For MIL-63 v1 we only
// care about the access_token (a JWT signed by WorkOS) which becomes
// the contents of the __Secure-cjipro-session cookie. The Edge
// Bouncer (MIL-61) verifies it against WorkOS JWKS.

const AUTHENTICATE_URL =
  "https://api.workos.com/user_management/authenticate";

export type ExchangeConfig = {
  clientId: string;
  clientSecret: string;
};

export type ExchangeSuccess = {
  ok: true;
  accessToken: string;
  refreshToken?: string;
  userId?: string;
  // MIL-66c — email from the WorkOS response body. Access tokens
  // don't carry an email claim, so this is our only chance to capture
  // it. Stored by the Worker into the sessions table for sub→email
  // lookups at the gate.
  userEmail?: string;
  // MIL-72 — organization_id, used to scope per-tenant audit log
  // exports. Absent for individual sign-ups not tied to a WorkOS Org.
  organizationId?: string;
  rawBody: Record<string, unknown>;
};

export type ExchangeFailure = {
  ok: false;
  status: number;
  reason: "http-error" | "missing-access-token" | "network-error";
  detail?: string;
};

export type ExchangeResult = ExchangeSuccess | ExchangeFailure;

// fetchImpl parameter exists purely for test injection. Callers
// in the Worker pass global fetch; tests pass a stub.
export async function exchangeCode(
  code: string,
  cfg: ExchangeConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<ExchangeResult> {
  let res: Response;
  try {
    res = await fetchImpl(AUTHENTICATE_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        grant_type: "authorization_code",
        code,
        client_id: cfg.clientId,
        client_secret: cfg.clientSecret,
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
      reason: "http-error",
      detail: `non-JSON body: ${rawText.slice(0, 120)}`,
    };
  }

  if (!res.ok) {
    const detail =
      typeof body.error_description === "string"
        ? body.error_description
        : typeof body.error === "string"
          ? body.error
          : rawText.slice(0, 200);
    return { ok: false, status: res.status, reason: "http-error", detail };
  }

  const accessToken = body.access_token;
  if (typeof accessToken !== "string" || accessToken.length === 0) {
    return {
      ok: false,
      status: res.status,
      reason: "missing-access-token",
    };
  }

  const refreshToken =
    typeof body.refresh_token === "string" ? body.refresh_token : undefined;
  const userId =
    body.user && typeof body.user === "object" && "id" in body.user
      ? String((body.user as { id: unknown }).id)
      : undefined;
  const userEmail =
    body.user &&
    typeof body.user === "object" &&
    "email" in body.user &&
    typeof (body.user as { email: unknown }).email === "string"
      ? ((body.user as { email: string }).email)
      : undefined;
  // organization_id may live at body.organization_id (top-level on
  // the authenticate response) or at body.user.organization_id
  // depending on the WorkOS response shape. Try both.
  let organizationId: string | undefined;
  if (typeof body.organization_id === "string") {
    organizationId = body.organization_id;
  } else if (
    body.user &&
    typeof body.user === "object" &&
    typeof (body.user as { organization_id?: unknown }).organization_id ===
      "string"
  ) {
    organizationId = (body.user as { organization_id: string }).organization_id;
  }

  return {
    ok: true,
    accessToken,
    refreshToken,
    userId,
    userEmail,
    organizationId,
    rawBody: body,
  };
}
