// MIL-63 — session cookie construction
//
// The cookie must be valid across ALL of *.cjipro.com (cjipro.com,
// sonar.cjipro.com, any future subdomain) so that one login covers
// the whole property. Set Domain=.cjipro.com to achieve that.
//
// Flags (locked — MIL-64 cookie spec ticket will reference this):
//   __Secure-*  → browser rejects if not https + refuses non-secure set
//   HttpOnly    → not accessible to JS (mitigates XSS exfil)
//   Secure      → only sent over https
//   SameSite=Lax → allows the top-level GET redirect back from
//                  login.cjipro.com to cjipro.com/briefing* to carry
//                  the cookie, but blocks it on cross-site POST /
//                  iframe contexts. Strict would break the login
//                  return redirect.
//   Path=/      → visible to every path
//   Max-Age     → from caller; WorkOS access_tokens typically live ~1h
//
// NB: the cookie *name* being "__Secure-cjipro-session" is load-bearing
// with MIL-61 (Edge Bouncer reads this exact name via env var).

export type CookieConfig = {
  name: string;
  domain: string;
  maxAgeSeconds: number;
};

export function buildSessionCookie(
  token: string,
  cfg: CookieConfig,
): string {
  const attrs = [
    `${cfg.name}=${token}`,
    `Max-Age=${cfg.maxAgeSeconds}`,
    `Domain=${cfg.domain}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
  ];
  return attrs.join("; ");
}

export function buildClearCookie(cfg: CookieConfig): string {
  const attrs = [
    `${cfg.name}=`,
    "Max-Age=0",
    `Domain=${cfg.domain}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
  ];
  return attrs.join("; ");
}
