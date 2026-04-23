"""
mil/publish/publish_site.py — CJI Pro public site (cjipro.com)

Deploys the landing page + privacy + supporting trust files (robots.txt,
sitemap.xml, security.txt, .nojekyll) to the GitHub Pages repo serving
cjipro.com via the MIL-35 PublishAdapter.

This is the public face of the domain — the surface that bank URL
classifiers crawl, the surface alpha partners land on. Briefings
(briefing-v[1-4]) and sonar.cjipro.com are published elsewhere.

Run:
    py -m mil.publish.publish_site            # deploy all site files
    py -m mil.publish.publish_site --dry-run  # print what would deploy

Source files:
    mil/publish/site/home.html        -> /index.html
    mil/publish/site/privacy.html     -> /privacy/index.html
    mil/publish/site/robots.txt       -> /robots.txt
    mil/publish/site/sitemap.xml      -> /sitemap.xml
    mil/publish/site/security.txt     -> /.well-known/security.txt
    (empty)                           -> /.nojekyll
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mil.publish.adapters import get_adapter

logger = logging.getLogger(__name__)

_SITE_DIR = Path(__file__).parent / "site"

# (source_filename, destination_relative_path)
# An empty source_filename means "publish an empty file at destination".
_FILES: list[tuple[str, str]] = [
    ("home.html",    "index.html"),
    ("privacy.html", "privacy/index.html"),
    ("robots.txt",   "robots.txt"),
    ("sitemap.xml",  "sitemap.xml"),
    ("security.txt", ".well-known/security.txt"),
    ("",             ".nojekyll"),
]


def _load(source: str) -> str:
    if source == "":
        return ""
    path = _SITE_DIR / source
    return path.read_text(encoding="utf-8")


def publish_all(dry_run: bool = False) -> int:
    adapter = get_adapter()
    failures = 0
    for source, dest in _FILES:
        content = _load(source)
        label = source or "(empty)"
        if dry_run:
            print(f"  [DRY] {label:20s} -> {dest:32s} ({len(content)} bytes)")
            continue
        ok, msg = adapter.publish(dest, content)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {label:20s} -> {dest:32s} {msg}")
        if not ok:
            failures += 1
    return failures


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Deploy CJI Pro public site")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without deploying")
    args = parser.parse_args()
    failures = publish_all(dry_run=args.dry_run)
    if failures:
        print(f"\n  [FAIL] {failures} file(s) failed to deploy")
        return 1
    print("\n  [OK] site deployed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
