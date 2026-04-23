// MIL-61 — public path allowlist
//
// Pattern syntax (from PUBLIC_PATHS env var, comma-separated):
//   /path        -> the literal prefix match "/path"
//   =/path       -> exact match (URL pathname === "/path")
//   ^/prefix/    -> pathname starts with "/prefix/"
//
// The Apr 23 Barclays corp-proxy lesson is load-bearing here: the
// landing + privacy + trust-signal paths MUST never redirect. If in
// doubt, add to PUBLIC_PATHS rather than gate.

export type Matcher = {
  kind: "exact" | "prefix";
  value: string;
};

export function parsePatterns(raw: string): Matcher[] {
  return raw
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .map<Matcher>((p) => {
      if (p.startsWith("=")) return { kind: "exact", value: p.slice(1) };
      if (p.startsWith("^")) return { kind: "prefix", value: p.slice(1) };
      // Bare token: treat as prefix for convenience
      return { kind: "prefix", value: p };
    });
}

export function isPublic(pathname: string, matchers: Matcher[]): boolean {
  for (const m of matchers) {
    if (m.kind === "exact" && pathname === m.value) return true;
    if (m.kind === "prefix" && pathname.startsWith(m.value)) return true;
  }
  return false;
}
