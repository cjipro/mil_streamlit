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

  return { ok: true, accessToken, refreshToken, userId, rawBody: body };
}
