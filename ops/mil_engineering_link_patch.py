"""MIL-160 follow-up — add 'Engineering' link to cjipro.com footer-bottom.

The Engineering posture page lives at app.cjipro.com/engineering behind
the ENFORCE auth gate. This script adds a public-facing entrypoint from
the cjipro.com marketing footer:

    Privacy · Security · security.txt · Engineering · Contact

The href takes visitors through the magic-link flow with return_to
encoded so they land on /engineering after sign-in:

    https://login.cjipro.com/?return_to=https%3A%2F%2Fapp.cjipro.com%2Fengineering

Pattern mirrors MIL-150 (Partner sign-in everywhere). Idempotent — running
twice is a no-op.

Targets every page that already carries the footer-bottom strip; pages
without it (sign_in, thank_you, research_*, etc.) are deliberately
skipped — they're utility surfaces that don't need the link.

Run: py ops/mil_engineering_link_patch.py
Then: py -m mil.publish.publish_site
"""

from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "mil" / "publish" / "site"

# Insert position: between security.txt and Contact, mirroring the
# information-density of the row (privacy → trust signals → contact).
OLD = '<a href="/.well-known/security.txt">security.txt</a>\n        <a href="mailto:hello@cjipro.com">Contact</a>'
NEW = (
    '<a href="/.well-known/security.txt">security.txt</a>\n'
    '        <a href="https://login.cjipro.com/?return_to=https%3A%2F%2Fapp.cjipro.com%2Fengineering">Engineering</a>\n'
    '        <a href="mailto:hello@cjipro.com">Contact</a>'
)

# Idempotency marker — if the engineering link is already present, skip.
ALREADY = 'href="https://login.cjipro.com/?return_to=https%3A%2F%2Fapp.cjipro.com%2Fengineering"'


def patch(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if ALREADY in text:
        return "SKIP (already patched)"
    if OLD not in text:
        return "MISS (footer pattern not found)"
    new_text = text.replace(OLD, NEW)
    path.write_text(new_text, encoding="utf-8", newline="\n")
    return "PATCHED"


def main() -> int:
    targets = sorted(SITE.glob("*.html"))
    if not targets:
        print(f"No HTML files under {SITE}")
        return 1
    patched = skipped = missed = 0
    for f in targets:
        result = patch(f)
        print(f"{result:35} {f.name}")
        if result.startswith("PATCHED"):
            patched += 1
        elif result.startswith("SKIP"):
            skipped += 1
        else:
            missed += 1
    print(f"\nSummary: {patched} patched, {skipped} skipped (already done), {missed} missed (no footer-bottom)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
