"""
mil/publish/publish_login_site.py — login.cjipro.com placeholder publisher

Pushes the static HTML from mil/publish/login_site/ into the cjipro/mil_briefing
deploy repo under /login/. Cloudflare Pages reads from that repo + subdirectory
and serves login.cjipro.com.

Why mil_briefing and not Cloudflare-Pages-off-mil_streamlit? Cleaner build
environment — mil_briefing contains only published assets (no requirements.txt,
no Python, no CUDA auto-detect). Cloudflare Pages builds are fast + predictable
because there's nothing for the build system to misidentify.

Run:
    py -m mil.publish.publish_login_site            # deploy
    py -m mil.publish.publish_login_site --dry-run  # print what would deploy

Source files:
    mil/publish/login_site/index.html   -> /login/index.html

Retired when MIL-61 Edge Bouncer takes over login.cjipro.com routing.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mil.publish.adapters import get_adapter

logger = logging.getLogger(__name__)

_LOGIN_SITE_DIR = Path(__file__).parent / "login_site"

# (source_filename, destination_relative_path)
_FILES: list[tuple[str, str]] = [
    ("index.html",    "login/index.html"),
    ("wrangler.toml", "login/wrangler.toml"),
]


def _load(source: str) -> str:
    return (_LOGIN_SITE_DIR / source).read_text(encoding="utf-8")


def publish_all(dry_run: bool = False) -> int:
    adapter = get_adapter()
    failures = 0
    for source, dest in _FILES:
        content = _load(source)
        if dry_run:
            print(f"  [DRY] {source:20s} -> {dest:32s} ({len(content)} bytes)")
            continue
        ok, msg = adapter.publish(dest, content)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {source:20s} -> {dest:32s} {msg}")
        if not ok:
            failures += 1
    return failures


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Deploy login.cjipro.com placeholder to mil_briefing")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without deploying")
    args = parser.parse_args()
    failures = publish_all(dry_run=args.dry_run)
    if failures:
        print(f"\n  [FAIL] {failures} file(s) failed to deploy")
        return 1
    print("\n  [OK] login site deployed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
