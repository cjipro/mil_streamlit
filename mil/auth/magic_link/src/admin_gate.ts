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

  let email: string | undefined;
  try {
    const { payload } = await jwtVerify(token, getJwks(cfg), {
      issuer: cfg.expectedIss,
      audience: cfg.expectedAud,
    });
    if (typeof payload.email === "string") email = payload.email;
  } catch (e) {
    return {
      kind: "invalid-session",
      reason: e instanceof Error ? e.message : String(e),
    };
  }

  if (!email) return { kind: "invalid-session", reason: "no-email-claim" };
  const ok = await isAdmin(db, email);
  return ok ? { kind: "ok", email } : { kind: "not-admin", email };
}
