"""gen_partner_domains.py — emit partner_domains.generated.ts from clients.yaml.

MIL-155. Source of truth for partner email-domain → client_slug mapping is
mil/config/clients.yaml. The Worker can't read YAML at runtime (no Node fs
in CF Workers), so we generate a TypeScript artefact at deploy time.

The generated file is gitignored — the predeploy/pretest hook regenerates
it before each upload, eliminating the drift class entirely.

Output: mil/auth/app_cjipro/src/partner_domains.generated.ts
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_CJIPRO = HERE.parent
REPO = APP_CJIPRO.parent.parent.parent
sys.path.insert(0, str(REPO))

from mil.config.clients_loader import domain_to_slug  # noqa: E402

OUTPUT = APP_CJIPRO / "src" / "partner_domains.generated.ts"

HEADER = """\
// AUTO-GENERATED from mil/config/clients.yaml. DO NOT EDIT.
// Regenerate via: py mil/auth/app_cjipro/scripts/gen_partner_domains.py
//
// MIL-155 — keeps firm_resolution.ts in lockstep with the canonical
// client registry without requiring two-file edits when a partner is
// onboarded. The npm "predeploy" + "pretest" hooks invoke this script
// so the artefact is always fresh.

export interface PartnerDomainEntry {
  slug: string;
  display: string;
}

export const PARTNER_DOMAIN_TO_SLUG: Record<string, PartnerDomainEntry> = {
"""

FOOTER = "};\n"


def _ts_string(s: str) -> str:
    # YAML loader rejects backslash + control chars at load time, so the
    # only escapes we need are " and \.
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render() -> str:
    mapping = domain_to_slug()
    if not mapping:
        # Empty mapping is valid — no partners with email_domains set yet.
        # Emit an empty record so the import still resolves.
        return HEADER + FOOTER
    # Sort for stable output — diffs only fire on real changes.
    rows: list[str] = []
    width = max(len(_ts_string(d)) for d in mapping)
    for domain in sorted(mapping):
        entry = mapping[domain]
        key = _ts_string(domain).ljust(width)
        slug = _ts_string(entry["slug"])
        display = _ts_string(entry["display_name"])
        rows.append(f"  {key}: {{ slug: {slug}, display: {display} }},\n")
    return HEADER + "".join(rows) + FOOTER


def main() -> int:
    content = render()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # LF line endings — matches mil/publish/adapters.py write_text_lf rule.
    OUTPUT.write_bytes(content.encode("utf-8"))
    print(f"wrote {OUTPUT.relative_to(REPO)} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
