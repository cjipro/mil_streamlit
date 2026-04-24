// MIL-61 — session JWT validation against WorkOS JWKS
//
// MIL-63 sets the session cookie as a side effect of the magic-link
// callback. MIL-64 will formalise the cookie spec. This module only
// cares about the JWT payload that lands inside it.

import {
  createRemoteJWKSet,
  jwtVerify,
  type JWTPayload,
  type JWTVerifyGetKey,
} from "jose";

export type SessionConfig = {
  jwksUrl: string;
  expectedIss: string;
  expectedAud: string;
  jwksCacheTtlSeconds: number;
};

export type SessionCheck =
  | { kind: "valid"; payload: JWTPayload }
  | { kind: "missing" }
  | { kind: "invalid"; reason: string };

// One JWKS fetcher per (jwksUrl, ttl) pair, cached in module scope
// so the isolate reuses it across requests. jose handles the
// stale-while-revalidate pattern internally.
const jwksCache = new Map<string, JWTVerifyGetKey>();

function getJwks(cfg: SessionConfig): JWTVerifyGetKey {
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

export function extractCookie(
  cookieHeader: string | null,
  name: string,
): string | null {
  if (!cookieHeader) return null;
  const parts = cookieHeader.split(";");
  for (const raw of parts) {
    const trimmed = raw.trim();
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    if (trimmed.slice(0, eq) === name) {
      return trimmed.slice(eq + 1);
    }
  }
  return null;
}

export async function verifySession(
  token: string | null,
  cfg: SessionConfig,
): Promise<SessionCheck> {
  if (!token) return { kind: "missing" };
  try {
    const jwks = getJwks(cfg);
    // MIL-66b: WorkOS User Management access tokens do not carry an
    // `aud` claim, so we verify issuer + signature only. The expected
    // aud is kept in config for symmetry + future swap to id_token.
    const { payload } = await jwtVerify(token, jwks, {
      issuer: cfg.expectedIss,
    });
    void cfg.expectedAud;
    return { kind: "valid", payload };
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    return { kind: "invalid", reason };
  }
}
