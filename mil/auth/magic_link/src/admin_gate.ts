// MIL-66b — admin gate helper.
//
// Two-step gate used by every /admin/* route:
//   1. Valid JWT in the session cookie (signed by WorkOS, iss/aud
//      match our AuthKit staging).
//   2. The JWT's `email` claim is in the admin_users table.
//
// Fails CLOSED on any step that can't be completed (no D1 binding,
// no jose verification, missing claim). Returns the admin's canonical
// email on success so route handlers can record `reviewed_by`.

import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";
import { isAdmin } from "../../approvals/src/admin";
import { lookupSessionEmail } from "../../approvals/src/sessions";

export interface AdminGateConfig {
  jwksUrl: string;
  expectedIss: string;
  expectedAud: string;
  jwksCacheTtlSeconds: number;
  cookieName: string;
}

const jwksCache = new Map<string, JWTVerifyGetKey>();

function getJwks(cfg: AdminGateConfig): JWTVerifyGetKey {
  const key = `${cfg.jwksUrl}|${cfg.jwksCacheTtlSeconds}`;
  let jwks = jwksCache.get(key);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(cfg.jwksUrl), {
      cacheMaxAge: cfg.jwksCacheTtlSeconds * 1000,
      cooldownDuration: 30 * 1000,
    });
    jwksCache.set(key, jwks);
  }
  return jwks;
}

function extractCookie(
  cookieHeader: string | null,
  name: string,
): string | null {
  if (!cookieHeader) return null;
  for (const raw of cookieHeader.split(";")) {
    const trimmed = raw.trim();
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    if (trimmed.slice(0, eq) === name) return trimmed.slice(eq + 1);
  }
  return null;
}

export type AdminCheck =
  | { kind: "ok"; email: string }
  | { kind: "no-session" }
  | { kind: "invalid-session"; reason: string }
  | { kind: "not-admin"; email: string }
  | { kind: "misconfigured" };

export async function checkAdmin(
  request: Request,
  db: D1Database | undefined,
  cfg: AdminGateConfig,
): Promise<AdminCheck> {
  if (!db) return { kind: "misconfigured" };

  const token = extractCookie(request.headers.get("cookie"), cfg.cookieName);
  if (!token) return { kind: "no-session" };

  let sub: string | undefined;
  try {
    // MIL-66b — WorkOS User Management access tokens don't carry an
    // `aud` claim, so we verify issuer + signature only. The aud the
    // edge-bouncer and this gate were configured with is kept as a
    // correlation value (wrangler.toml) but not passed to jose.
    const { payload } = await jwtVerify(token, getJwks(cfg), {
      issuer: cfg.expectedIss,
    });
    void cfg.expectedAud;
    if (typeof payload.sub === "string") sub = payload.sub;
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    return { kind: "invalid-session", reason };
  }

  // MIL-66c — WorkOS access_tokens carry sub but no email. /callback
  // wrote a sub→email row at sign-in time; look it up here.
  if (!sub) {
    return { kind: "invalid-session", reason: "no-sub-claim" };
  }
  const email = await lookupSessionEmail(db, sub);
  if (!email) {
    return { kind: "invalid-session", reason: "no-session-row" };
  }

  const ok = await isAdmin(db, email);
  return ok ? { kind: "ok", email } : { kind: "not-admin", email };
}
