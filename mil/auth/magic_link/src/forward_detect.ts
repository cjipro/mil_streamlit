// MIL-146 — heuristic "did this magic-link get forwarded?" check.
//
// Forwarding is intentional and supported (Hussain decision Q4, panel
// 2026-04-26). This module is observability only — it never blocks the
// callback. The heuristic compares the IP class + UA family captured at
// /authorize (carried inside the HMAC-signed state token) to the same
// values at /callback. If either differs, we emit a non-blocking audit
// event so partner-portal UX can later surface "this link was forwarded
// — make sure they see the request-access page" hints.
//
// Specifically scoped:
//   * IP class = /24 prefix (IPv4) or /64 prefix (IPv6). Corp NATs all
//     employees through the same /24, so two Barclays employees clicking
//     the same forwarded link from inside the office won't trigger.
//   * UA family = the major browser engine identifier (chrome / firefox
//     / safari / edge / opera / other). Two Chrome versions on different
//     OSes don't trigger; Chrome → Firefox does.
//
// Acceptance contract (test file pins this):
//   same context           -> not forwarded
//   different IP, same UA  -> forwarded
//   same IP, different UA  -> forwarded
//   different both         -> forwarded

export type UAFamily =
  | "chrome"
  | "firefox"
  | "safari"
  | "edge"
  | "opera"
  | "other";

export function ipClass(ip: string | null | undefined): string {
  if (!ip) return "";
  // IPv6 — first 4 hextets (i.e. /64) is the customary "subnet" boundary
  // for forwarding inference. Strip everything after that.
  if (ip.includes(":")) {
    const parts = ip.split(":");
    return parts.slice(0, 4).join(":") + "::";
  }
  // IPv4 — first three octets (/24).
  const oct = ip.split(".");
  if (oct.length !== 4) return ip; // malformed — return as-is
  return `${oct[0]}.${oct[1]}.${oct[2]}.0`;
}

export function uaFamily(ua: string | null | undefined): UAFamily {
  if (!ua) return "other";
  const s = ua.toLowerCase();
  // Order matters — Chrome and Edge both contain "chrome" in their UA
  // string; Edge must be checked first. Likewise Opera contains "chrome"
  // (via Chromium) and must precede the chrome check.
  if (s.includes("edg/") || s.includes("edge/")) return "edge";
  if (s.includes("opr/") || s.includes("opera/")) return "opera";
  if (s.includes("firefox/")) return "firefox";
  if (s.includes("chrome/")) return "chrome";
  // Safari is the trailing token — every Safari UA contains "Safari/"
  // but so do iOS Chromes (which would have caught above on chrome/).
  if (s.includes("safari/")) return "safari";
  return "other";
}

export interface ForwardDetectResult {
  forwarded: boolean;
  ip_changed: boolean;
  ua_changed: boolean;
}

export function looksForwarded(
  originalIp: string | null | undefined,
  originalUa: string | null | undefined,
  currentIp: string | null | undefined,
  currentUa: string | null | undefined,
): ForwardDetectResult {
  // If we don't have an original context to compare against (older
  // states pre-MIL-146, or local testing), treat as not-forwarded —
  // observability is opt-in, never accusatory.
  if (!originalIp && !originalUa) {
    return { forwarded: false, ip_changed: false, ua_changed: false };
  }
  const ipChanged = ipClass(originalIp) !== ipClass(currentIp);
  const uaChanged = uaFamily(originalUa) !== uaFamily(currentUa);
  return {
    forwarded: ipChanged || uaChanged,
    ip_changed: ipChanged,
    ua_changed: uaChanged,
  };
}
