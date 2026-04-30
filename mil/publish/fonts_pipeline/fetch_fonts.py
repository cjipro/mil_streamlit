"""fetch_fonts.py — download Source Serif 4 + Inter WOFF2 for self-hosting (MIL-136).

Spec (panel 2026-04-26 Reichenstein + Kravets):
    Source Serif 4 — headings, display, citations
    Inter          — body, UI, forms

Why self-host: cjipro.com is reached on Barclays / HSBC / Lloyds corp
networks where Google Fonts CDN can be blocked or flagged. Self-hosted at
cjipro.com/fonts/ keeps every byte under our domain.

How: this script asks Google Fonts CSS endpoint for the @font-face block
with a modern-Chrome User-Agent (so we get WOFF2 not TTF), filters down to
latin + latin-ext unicode ranges (English banking deployment — no cyrillic /
vietnamese / greek needed), downloads each .woff2 to mil/publish/site/fonts/,
and rewrites the @font-face URLs to local /fonts/<file>.woff2 paths.

Fonts are OFL-licensed; redistribution is explicitly allowed by the licence.
We bundle OFL.txt next to the woff2 files to keep that note visible.

Run:
    py mil/publish/fonts_pipeline/fetch_fonts.py
    py mil/publish/fonts_pipeline/fetch_fonts.py --check  # verify present, no fetch

Outputs:
    mil/publish/site/fonts/<font>-<weight>-<subset>.woff2
    mil/publish/site/fonts/fonts.css
    mil/publish/site/fonts/OFL.txt
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
OUT_DIR = REPO / "mil" / "publish" / "site" / "fonts"

# Latin + latin-ext only. The Google Fonts CSS gives us each unicode-range
# block annotated as a comment; we keep only the two we need.
KEEP_SUBSETS = {"latin", "latin-ext"}

# Chrome UA so Google returns WOFF2 (older UAs get TTF).
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# MIL-136 — marketing site fonts (cjipro.com/*).
SITE_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;700"
    "&family=Source+Serif+4:wght@400;700"
    "&display=swap"
)

# MIL-157 — Sonar briefings fonts (V1/V2/V3/V4). Different palette: Plus
# Jakarta Sans for body + DM Mono for numbers/dashboard chrome. Same
# self-hosting story; same corp-proxy risk class.
BRIEFINGS_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Plus+Jakarta+Sans:wght@400;500;600;700;800"
    "&family=DM+Mono:wght@400;500"
    "&display=swap"
)

# Backward-compat for callers/tests that referenced the old name.
GOOGLE_CSS_URL = SITE_CSS_URL

OFL_LICENSE_TEXT = """\
All fonts in this directory are licensed under the SIL Open Font Licence
(OFL) version 1.1. The full licence text is at https://openfontlicense.org.

Source Serif 4    © Adobe, contributors.
                    https://github.com/adobe-fonts/source-serif
Inter             © Rasmus Andersson, contributors.
                    https://github.com/rsms/inter
Plus Jakarta Sans © Tokotype, contributors.
                    https://github.com/tokotype/PlusJakartaSans
DM Mono           © Colophon Foundry, Jonny Pinhorn, contributors.
                    https://github.com/googlefonts/dm-mono

Redistribution of the unmodified font binaries (as bundled here, fetched
from Google Fonts CDN at build time) is explicitly permitted by the OFL.
"""


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — pinned URL
        return resp.read()


def _parse_blocks(css: str) -> list[dict]:
    """Split the Google Fonts CSS into one record per @font-face block.

    Each block is preceded by `/* <subset> */` and contains a font-family,
    font-weight, src, and unicode-range. We capture all four.
    """
    pattern = re.compile(
        r"/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{([^}]+)\}",
        re.DOTALL,
    )
    blocks: list[dict] = []
    for m in pattern.finditer(css):
        subset = m.group(1).strip()
        body = m.group(2)

        family_m = re.search(r"font-family:\s*'([^']+)'", body)
        weight_m = re.search(r"font-weight:\s*(\d+)", body)
        src_m = re.search(r"src:\s*url\(([^)]+)\)\s*format\('woff2'\)", body)
        urange_m = re.search(r"unicode-range:\s*([^;]+);", body)

        if not (family_m and weight_m and src_m and urange_m):
            continue

        blocks.append({
            "subset": subset,
            "family": family_m.group(1),
            "weight": int(weight_m.group(1)),
            "src_url": src_m.group(1).strip(),
            "unicode_range": urange_m.group(1).strip(),
        })
    return blocks


def _local_filename(family: str, weight: int, subset: str) -> str:
    family_slug = family.lower().replace(" ", "-")
    return f"{family_slug}-{weight}-{subset}.woff2"


# MIL-158 — destination for the Worker-side TS module. Workers live on
# app.<apex> / login.<apex> / admin.<apex> — different origins from the
# apex — so relative `/fonts/` paths don't resolve. The TS module inlines
# @font-face rules with ABSOLUTE URLs (read from tenant.yaml) so the
# browser fetches the woff2 cross-origin from the same Pages origin.
WORKERS_FONTS_BLOCK_DEST = (
    REPO / "mil" / "auth" / "fonts_block" / "src" / "fonts_block.generated.ts"
)
# MIL-119 — read absolute fonts host from tenant.yaml. The constant is kept
# for back-compat with anything that imports it; it's resolved at module
# import time, not at call time, so a fork that wants to swap fonts hosts
# without restarting Python should call tenant_loader.fonts_base_url() directly.
from mil.config import tenant_loader as _tenant_loader
ABSOLUTE_FONTS_BASE = _tenant_loader.fonts_base_url()


def _build_css(blocks: list[dict], header_comment: str) -> str:
    """Re-emit the @font-face rules with local /fonts/<file>.woff2 URLs."""
    lines: list[str] = [
        "/* AUTO-GENERATED by mil/publish/fonts_pipeline/fetch_fonts.py.",
        f" * {header_comment}",
        " * Edit fetch_fonts.py + re-run if the font set changes. */",
        "",
    ]
    for b in blocks:
        local = _local_filename(b["family"], b["weight"], b["subset"])
        lines.append("@font-face {")
        lines.append(f'  font-family: "{b["family"]}";')
        lines.append(f"  font-style: normal;")
        lines.append(f"  font-weight: {b['weight']};")
        lines.append(f"  font-display: swap;")
        lines.append(f'  src: url("/fonts/{local}") format("woff2");')
        lines.append(f"  unicode-range: {b['unicode_range']};")
        lines.append("}")
    return "\n".join(lines) + "\n"


def _fetch_set(css_url: str, label: str) -> tuple[list[dict], int]:
    """Download one font-set (call once per CSS URL) and write its woff2 files.

    Returns (parsed-blocks, total-bytes-written-or-already-present).
    """
    print(f"  ->Fetching CSS index for {label}...")
    css = _fetch(css_url).decode("utf-8")
    blocks = _parse_blocks(css)
    blocks = [b for b in blocks if b["subset"] in KEEP_SUBSETS]
    if not blocks:
        print(f"  ! no latin / latin-ext @font-face blocks parsed for {label}", file=sys.stderr)
        return [], 0
    print(f"  ->Parsed {len(blocks)} @font-face blocks (latin + latin-ext)")

    total_bytes = 0
    for b in blocks:
        local = _local_filename(b["family"], b["weight"], b["subset"])
        dest = OUT_DIR / local
        if dest.exists():
            total_bytes += dest.stat().st_size
            print(f"     skip   {local}  ({dest.stat().st_size} bytes, exists)")
            continue
        data = _fetch(b["src_url"])
        dest.write_bytes(data)
        total_bytes += len(data)
        print(f"     write  {local}  ({len(data)} bytes)")
    return blocks, total_bytes


def _build_workers_fonts_block(blocks: list[dict]) -> str:
    """MIL-158 — Worker-side TS module with absolute URLs to cjipro.com.

    Emits a single template-literal exporting the @font-face <style> tag
    plus the SERIF / SANS font-stack constants Workers use to update
    their --serif and --sans CSS variables. Workers import this once
    and inject FONTS_BLOCK into their HTML `<head>`.
    """
    lines: list[str] = [
        "// AUTO-GENERATED by mil/publish/fonts_pipeline/fetch_fonts.py.",
        "// MIL-158 — Worker-side fonts: absolute URLs to cjipro.com so",
        "// pages on app.cjipro.com / login.cjipro.com / admin.cjipro.com",
        "// can pull self-hosted Source Serif 4 + Inter from the canonical",
        "// origin. CSP requirement on every Worker that injects this:",
        '//   font-src https://cjipro.com (in addition to \'self\').',
        "// Edit fetch_fonts.py + re-run if the font set changes.",
        "",
        "export const FONTS_BLOCK = `<style>",
    ]
    for b in blocks:
        local = _local_filename(b["family"], b["weight"], b["subset"])
        lines.append("@font-face {")
        lines.append(f'  font-family: "{b["family"]}";')
        lines.append("  font-style: normal;")
        lines.append(f"  font-weight: {b['weight']};")
        lines.append("  font-display: swap;")
        lines.append(f'  src: url("{ABSOLUTE_FONTS_BASE}/{local}") format("woff2");')
        lines.append(f"  unicode-range: {b['unicode_range']};")
        lines.append("}")
    lines.extend([
        "</style>`;",
        "",
        "// Font stacks. Workers swap their existing --serif / --sans CSS",
        "// variables to reference these so the cascade flips at one site.",
        "export const FONT_STACK_SERIF =",
        '  \'"Source Serif 4", Georgia, "Times New Roman", "DejaVu Serif", serif\';',
        "export const FONT_STACK_SANS =",
        '  \'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif\';',
        "",
    ])
    return "\n".join(lines)


def fetch_all() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grand_total = 0

    print("[site] MIL-136 — Source Serif 4 + Inter for cjipro.com/*")
    site_blocks, site_bytes = _fetch_set(SITE_CSS_URL, "site fonts")
    if not site_blocks:
        return 1
    (OUT_DIR / "fonts.css").write_bytes(
        _build_css(site_blocks, "MIL-136 — self-hosted Source Serif 4 + Inter (OFL).").encode("utf-8")
    )
    # MIL-158 — Worker-side TS module with absolute URLs.
    WORKERS_FONTS_BLOCK_DEST.parent.mkdir(parents=True, exist_ok=True)
    WORKERS_FONTS_BLOCK_DEST.write_bytes(
        _build_workers_fonts_block(site_blocks).encode("utf-8")
    )
    print(f"  -> wrote {WORKERS_FONTS_BLOCK_DEST.relative_to(REPO)}")
    grand_total += site_bytes

    print("\n[briefings] MIL-157 — Plus Jakarta Sans + DM Mono for Sonar V1-V4")
    brief_blocks, brief_bytes = _fetch_set(BRIEFINGS_CSS_URL, "briefings fonts")
    if not brief_blocks:
        return 1
    (OUT_DIR / "briefings_fonts.css").write_bytes(
        _build_css(brief_blocks, "MIL-157 — self-hosted Plus Jakarta Sans + DM Mono (OFL).").encode("utf-8")
    )
    grand_total += brief_bytes

    (OUT_DIR / "OFL.txt").write_bytes(OFL_LICENSE_TEXT.encode("utf-8"))
    print(
        f"\nOK — {len(site_blocks) + len(brief_blocks)} woff2 files total, "
        f"{grand_total} bytes ({grand_total // 1024} KB)"
    )
    return 0


def check_only() -> int:
    """Verify expected files exist (used as a build-time sanity check)."""
    missing: list[str] = []
    for name in ("fonts.css", "OFL.txt"):
        if not (OUT_DIR / name).exists():
            missing.append(name)
    if not OUT_DIR.exists() or not any(OUT_DIR.glob("*.woff2")):
        missing.append("*.woff2 (none found)")
    if missing:
        print(f"FAIL: missing in {OUT_DIR.relative_to(REPO)}: {missing}", file=sys.stderr)
        print("Run: py mil/publish/fonts_pipeline/fetch_fonts.py", file=sys.stderr)
        return 1
    woff_count = sum(1 for _ in OUT_DIR.glob("*.woff2"))
    print(f"OK — fonts.css present + {woff_count} woff2 files in {OUT_DIR.relative_to(REPO)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="Verify presence, no fetch")
    args = parser.parse_args()
    if args.check:
        return check_only()
    return fetch_all()


if __name__ == "__main__":
    sys.exit(main())
