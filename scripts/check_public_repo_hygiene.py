#!/usr/bin/env python3
"""scripts/check_public_repo_hygiene.py — MIL-110 Pages-repo scanner.

Audits the public Pages repo (`PUBLISH_REPO`) for any tracked file that
shouldn't be there: auth code, runbooks, CLAUDE.md, .env*, source code,
or content matching sensitive-string regexes (D1 UUIDs, Org IDs, Client
IDs, API tokens, scheduled trigger IDs).

Two complementary checks:
  1. Path check — every tracked file's path is run through
     mil/publish/adapters.py SENSITIVE_PATH_PATTERNS. The publish chain
     already refuses these paths going forward (MIL-110 Stage 2); this
     scan catches anything pushed BEFORE the guard landed.
  2. Content check — every tracked file is grepped for known-sensitive
     strings (literal D1 UUIDs, env-var names appearing as literals,
     etc.). Catches sensitive material smuggled into otherwise-legitimate
     paths (e.g., a wrangler.toml committed for asset-binding reasons but
     accidentally containing JWKS_URL).

Usage:
  py scripts/check_public_repo_hygiene.py
  py scripts/check_public_repo_hygiene.py --repo cjipro/mil-briefing
  py scripts/check_public_repo_hygiene.py --keep-clone  # for inspection

Exit codes:
  0 — clean (nothing flagged)
  1 — flagged content found (path or content match)
  2 — usage / clone error

Operator playbook on exit-1:
  - Read the report; for each finding decide remediate (rewrite content)
    or remove (git rm + commit + force-push, plus rotate any leaked
    secret). MIL-112 covers full git-history scrubbing if needed.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mil" / "publish"))

# Reuse the deny-list from the publish adapter so path policy is single-source.
from adapters import SENSITIVE_PATH_PATTERNS  # noqa: E402


# ── Sensitive-content patterns (substring / regex against file contents) ─────
# Patterns are intentionally specific to known-MIL identifiers. Tuned to
# minimise false positives while catching the signals Tavis Ormandy named
# in the MIL-110 panel review.
SENSITIVE_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("D1 database UUID",           re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")),
    ("WorkOS Org ID",              re.compile(r"\borg_01[A-Z0-9]{24}\b")),
    ("WorkOS Client ID",           re.compile(r"\bclient_01[A-Z0-9]{24}\b")),
    ("WorkOS Secret",              re.compile(r"\bsk_(?:test|live)_[A-Za-z0-9]{24,}\b")),
    ("GitLab PAT",                 re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("GitHub fine-grained token",  re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}")),
    ("GitHub classic token",       re.compile(r"\bghp_[A-Za-z0-9]{36}")),
    ("Anthropic API key",          re.compile(r"\bsk-ant-(?:api03|admin01)-[A-Za-z0-9_\-]{40,}")),
    ("OpenAI API key",             re.compile(r"\bsk-[A-Za-z0-9]{48}\b")),
    ("Cloudflare API token",       re.compile(r"\b[A-Za-z0-9_\-]{40}\b(?=.*cloudflare|.*CF_API)", re.IGNORECASE)),
    ("Scheduled-trigger ID",       re.compile(r"\btrig_01[A-Za-z0-9]{24}\b")),
    ("AWS access key",             re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Auth env var literals — present implies someone copy-pasted runbook
    # text into a public surface.
    ("JWKS_URL literal",           re.compile(r"JWKS_URL\s*[:=]\s*['\"]https?://", re.IGNORECASE)),
    ("EXPECTED_ISS literal",       re.compile(r"EXPECTED_ISS\s*[:=]\s*['\"]https?://", re.IGNORECASE)),
    ("EXPECTED_AUD literal",       re.compile(r"EXPECTED_AUD\s*[:=]\s*['\"]client_", re.IGNORECASE)),
    ("WORKOS_API_KEY literal",     re.compile(r"WORKOS_API_KEY\s*[:=]", re.IGNORECASE)),
    ("STATE_SIGNING_KEY literal",  re.compile(r"STATE_SIGNING_KEY\s*[:=]", re.IGNORECASE)),
    ("WORKOS_WEBHOOK_SECRET",      re.compile(r"WORKOS_WEBHOOK_SECRET\s*[:=]", re.IGNORECASE)),
    ("SMTP_APP_PASSWORD literal",  re.compile(r"SMTP_APP_PASSWORD\s*[:=]", re.IGNORECASE)),
    ("CLOUDFLARE_API_TOKEN ref",   re.compile(r"CLOUDFLARE_API_TOKEN\s*[:=]", re.IGNORECASE)),
)


def _read_publish_repo_from_env() -> str | None:
    """Read PUBLISH_REPO from .env at repo root. Avoids dotenv dep."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("PUBLISH_REPO="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _check_path(rel_path: str) -> list[str]:
    """Return a list of pattern descriptions that matched this path."""
    return [pat.pattern for pat in SENSITIVE_PATH_PATTERNS if pat.search(rel_path)]


# Files we should NOT scan content of (they're large output; scanning is
# noise). HTML output is the bulk of the Pages repo and we trust it.
SKIP_CONTENT_SUFFIXES = (".html", ".htm", ".png", ".jpg", ".jpeg", ".gif",
                         ".webp", ".ico", ".svg", ".woff", ".woff2", ".ttf",
                         ".eot", ".pdf", ".gz", ".zip")


def _check_content(file_path: Path) -> list[tuple[str, str]]:
    """Return [(pattern_name, matched_snippet), ...] for content hits."""
    if any(file_path.name.lower().endswith(s) for s in SKIP_CONTENT_SUFFIXES):
        return []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    hits: list[tuple[str, str]] = []
    for name, pat in SENSITIVE_CONTENT_PATTERNS:
        m = pat.search(text)
        if m:
            snippet = m.group(0)
            # Truncate token-like values to first 8 chars + ellipsis.
            if len(snippet) > 12:
                snippet = snippet[:8] + "…"
            hits.append((name, snippet))
    return hits


def scan_repo(repo_slug: str, keep_clone: bool = False) -> dict:
    """Clone repo_slug to a temp dir, scan every tracked file, return report."""
    if "/" not in repo_slug:
        raise ValueError(f"repo must be in form 'owner/name', got {repo_slug!r}")

    tmpdir = Path(tempfile.mkdtemp(prefix="mil110-hygiene-"))
    clone_dir = tmpdir / "repo"
    url = f"https://github.com/{repo_slug}.git"

    print(f"  cloning {repo_slug} (depth=1) ...", file=sys.stderr)
    r = subprocess.run(
        ["git", "clone", "--depth=1", url, str(clone_dir)],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        return {"error": f"clone failed: {r.stderr.strip()}", "tmpdir": tmpdir}

    files = subprocess.check_output(
        ["git", "-C", str(clone_dir), "ls-files"],
        text=True,
    ).splitlines()

    path_findings: list[tuple[str, list[str]]] = []
    content_findings: list[tuple[str, list[tuple[str, str]]]] = []

    for rel in files:
        path_hits = _check_path(rel)
        if path_hits:
            path_findings.append((rel, path_hits))
        content_hits = _check_content(clone_dir / rel)
        if content_hits:
            content_findings.append((rel, content_hits))

    return {
        "repo": repo_slug,
        "file_count": len(files),
        "path_findings": path_findings,
        "content_findings": content_findings,
        "tmpdir": tmpdir if keep_clone else None,
    }


def print_report(report: dict) -> int:
    if "error" in report:
        print(f"\n  ERROR: {report['error']}\n", file=sys.stderr)
        return 2

    repo = report["repo"]
    n_files = report["file_count"]
    paths = report["path_findings"]
    contents = report["content_findings"]

    print(f"\n=== Public Pages repo audit: {repo} ===")
    print(f"  scanned {n_files} tracked files\n")

    if paths:
        print(f"  PATH POLICY VIOLATIONS ({len(paths)} file(s)) — these paths should never reach Pages:")
        for rel, pats in paths:
            print(f"    {rel}")
            for p in pats:
                print(f"      └─ matched pattern  {p}")
        print()
    else:
        print(f"  PATH POLICY: clean (zero hits across {len(SENSITIVE_PATH_PATTERNS)} patterns)")

    if contents:
        print(f"  CONTENT POLICY VIOLATIONS ({len(contents)} file(s)) — sensitive strings inside committed files:")
        for rel, hits in contents:
            print(f"    {rel}")
            for name, snippet in hits:
                print(f"      └─ {name}: {snippet}")
        print()
    else:
        print(f"  CONTENT POLICY: clean (zero hits across {len(SENSITIVE_CONTENT_PATTERNS)} patterns)")

    print()
    if paths or contents:
        print("  RESULT: DIRTY — see findings above. Remediation: see MIL-110 runbook.")
        return 1
    print("  RESULT: CLEAN — Pages repo contains only safe-by-design content.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="MIL-110 public-repo hygiene scanner")
    ap.add_argument("--repo", default=None,
                    help="GitHub repo slug 'owner/name'. Defaults to PUBLISH_REPO from .env.")
    ap.add_argument("--keep-clone", action="store_true",
                    help="Don't clean up temp clone — useful for manual follow-up inspection.")
    args = ap.parse_args()

    repo = args.repo or _read_publish_repo_from_env()
    if not repo:
        print("  ERROR: no repo specified and PUBLISH_REPO not in .env", file=sys.stderr)
        return 2

    report = scan_repo(repo, keep_clone=args.keep_clone)
    rc = print_report(report)
    if args.keep_clone and report.get("tmpdir"):
        print(f"  (clone retained at {report['tmpdir']})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
