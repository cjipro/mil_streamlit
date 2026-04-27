"""migrate_site_fonts.py — one-shot CSS rewrites for MIL-136.

Idempotent — running twice produces the same result. Run once, commit
output, then delete the script (or keep it around as a regression-aid).

Touches every file under mil/publish/site/*.html:

    * Injects <link rel="preload" .../> for the two critical weights and
      <link rel="stylesheet" href="/fonts/fonts.css"> immediately before the
      first <link rel="canonical"> or, failing that, before </head>.
    * In files that define CSS variables --serif / --sans, prepends
      Source Serif 4 / Inter to the existing fallback chain. (Mono stack
      is left alone — there's no Inter/Serif-Source mono variant in scope.)
    * In files without --serif / --sans (the redirect stubs), substitutes
      the inline font-family declaration on the body selector.

The "no mixed-surface intermediate state" rule (panel #14, Addy Osmani)
is satisfied at the source-commit level: every site file flips in the
same commit. Production rollout is sequenced via publish_site.py +
each Worker's deploy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
SITE_DIR = REPO / "mil" / "publish" / "site"

# The four canonical font stacks. SERIF + SANS are the new defaults; MONO
# stays system-only (no chosen mono in the Reichenstein/Kravets brief).
NEW_SERIF = '"Source Serif 4", Georgia, "Times New Roman", "DejaVu Serif", serif'
NEW_SANS = (
    'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", '
    'Helvetica, Arial, sans-serif'
)

# The <link> block to inject. Two preloads (the weights every page hits
# above-the-fold) + the stylesheet. font-display:swap inside fonts.css
# means missing-font-but-loading shows the system fallback rather than
# blank text — LCP is preserved.
FONT_LINKS = """\
<!-- MIL-136 — self-hosted Source Serif 4 + Inter (OFL). -->
<link rel="preload" href="/fonts/source-serif-4-700-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/inter-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/fonts/fonts.css">
"""


def _has_font_links(html: str) -> bool:
    return "/fonts/fonts.css" in html


def _inject_font_links(html: str) -> str:
    if _has_font_links(html):
        return html
    # Prefer to land just before <link rel="canonical"> for tidy diffs.
    canonical_re = re.compile(r"(\s*<link rel=\"canonical\")", re.IGNORECASE)
    if canonical_re.search(html):
        return canonical_re.sub("\n" + FONT_LINKS + r"\1", html, count=1)
    # Fallback: just before </head>.
    head_close_re = re.compile(r"(\s*</head>)", re.IGNORECASE)
    if head_close_re.search(html):
        return head_close_re.sub("\n" + FONT_LINKS + r"\1", html, count=1)
    return html  # no <head> — caller will spot the absence


def _swap_css_vars(html: str) -> str:
    """Update --serif and --sans declarations in :root blocks."""
    # --serif:    Georgia, "Times...";
    serif_re = re.compile(
        r"(--serif\s*:\s*)([^;]*?)(;)",
        re.IGNORECASE,
    )
    sans_re = re.compile(
        r"(--sans\s*:\s*)([^;]*?)(;)",
        re.IGNORECASE,
    )
    out = serif_re.sub(rf"\1{NEW_SERIF}\3", html)
    out = sans_re.sub(rf"\1{NEW_SANS}\3", out)
    return out


def _swap_inline_body_font(html: str) -> str:
    """For redirect stubs — body { font-family: <system stack> } → use Inter."""
    # Match patterns like:
    #   body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; ... }
    pattern = re.compile(
        r"(body\s*\{[^}]*?font-family\s*:\s*)([^;]+?)(;)",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(rf"\1{NEW_SANS}\3", html)


def migrate_file(path: Path) -> tuple[bool, str]:
    original = path.read_text(encoding="utf-8")
    out = _inject_font_links(original)

    if "--serif" in out and "--sans" in out:
        out = _swap_css_vars(out)
    else:
        out = _swap_inline_body_font(out)

    if out == original:
        return False, "no change"
    path.write_text(out, encoding="utf-8")
    return True, f"updated ({len(out) - len(original):+d} bytes)"


def main() -> int:
    if not SITE_DIR.exists():
        print(f"site dir not found: {SITE_DIR}", file=sys.stderr)
        return 1
    files = sorted(SITE_DIR.glob("*.html"))
    if not files:
        print("no .html files in site dir", file=sys.stderr)
        return 1
    changed = 0
    for f in files:
        did, msg = migrate_file(f)
        marker = "  *" if did else "   "
        print(f"{marker} {f.name:42s} {msg}")
        if did:
            changed += 1
    print(f"\n{changed} of {len(files)} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
