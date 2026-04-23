// MIL-64 — machine-enforced cookie invariants.
//
// This file is the executable form of `mil/auth/COOKIE_SPEC.md`.
// Any drift between the two is a bug.
//
// Usage: call `assertSpecCompliant(headerValue)` after
// `buildSessionCookie()` in tests to catch accidental changes.

export type SpecViolation = {
  ok: false;
  rule: string;
  detail: string;
};

export type SpecOk = { ok: true };

export type SpecResult = SpecOk | SpecViolation;

export const REQUIRED_COOKIE_NAME = "__Secure-cjipro-session";
export const REQUIRED_DOMAIN = ".cjipro.com";
export const REQUIRED_PATH = "/";
export const REQUIRED_SAMESITE = "Lax";
export const REQUIRED_FLAGS = ["HttpOnly", "Secure"] as const;
export const FORBIDDEN_ATTRS = ["Expires", "Partitioned"] as const;
export const FORBIDDEN_SAMESITE = ["None", "Strict"] as const;

// Parse a Set-Cookie header value into case-folded attribute names
// + values. RFC 6265 flags (e.g. "HttpOnly", "Secure") appear as
// value=true.
function parseSetCookie(header: string): Record<string, string | true> {
  const out: Record<string, string | true> = {};
  const parts = header.split(";").map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return out;

  // First part is name=value — we don't put it in the attr map.
  const first = parts.shift()!;
  const eq = first.indexOf("=");
  if (eq > 0) {
    out.__name__ = first.slice(0, eq);
    out.__value__ = first.slice(eq + 1);
  }

  for (const p of parts) {
    const peq = p.indexOf("=");
    if (peq < 0) {
      out[p.toLowerCase()] = true;
    } else {
      const k = p.slice(0, peq).toLowerCase();
      const v = p.slice(peq + 1);
      out[k] = v;
    }
  }
  return out;
}

export function assertSpecCompliant(setCookie: string): SpecResult {
  const attrs = parseSetCookie(setCookie);

  if (attrs.__name__ !== REQUIRED_COOKIE_NAME) {
    return {
      ok: false,
      rule: "cookie-name",
      detail: `expected ${REQUIRED_COOKIE_NAME}, got ${attrs.__name__}`,
    };
  }

  if (attrs.domain !== REQUIRED_DOMAIN) {
    return {
      ok: false,
      rule: "domain",
      detail: `expected ${REQUIRED_DOMAIN}, got ${attrs.domain ?? "(missing)"}`,
    };
  }

  if (attrs.path !== REQUIRED_PATH) {
    return {
      ok: false,
      rule: "path",
      detail: `expected ${REQUIRED_PATH}, got ${attrs.path ?? "(missing)"}`,
    };
  }

  for (const flag of REQUIRED_FLAGS) {
    if (attrs[flag.toLowerCase()] !== true) {
      return {
        ok: false,
        rule: "required-flag",
        detail: `missing ${flag}`,
      };
    }
  }

  if (attrs.samesite !== REQUIRED_SAMESITE) {
    return {
      ok: false,
      rule: "samesite",
      detail: `expected ${REQUIRED_SAMESITE}, got ${attrs.samesite ?? "(missing)"}`,
    };
  }
  // FORBIDDEN_SAMESITE is documented in the spec for clarity but
  // the REQUIRED_SAMESITE equality above already rejects any other
  // value; no separate loop needed.

  for (const forbidden of FORBIDDEN_ATTRS) {
    if (forbidden.toLowerCase() in attrs) {
      return {
        ok: false,
        rule: "forbidden-attr",
        detail: `${forbidden} attribute is prohibited by spec`,
      };
    }
  }

  // Max-Age must be present and be a positive integer OR exactly 0
  // (for the revocation case). Non-numeric or negative is a bug.
  const maxAge = attrs["max-age"];
  if (maxAge === undefined) {
    return {
      ok: false,
      rule: "max-age-missing",
      detail: "Max-Age is required (use 0 for revocation, positive for issuance)",
    };
  }
  if (typeof maxAge !== "string" || !/^\d+$/.test(maxAge)) {
    return {
      ok: false,
      rule: "max-age-invalid",
      detail: `Max-Age must be non-negative integer, got ${String(maxAge)}`,
    };
  }

  return { ok: true };
}
