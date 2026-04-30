"""scripts/scan_history_secrets.py — MIL-112 git-history secret scanner.

Pattern-scans `git log -p --all` for known token shapes. Stdlib + the
git CLI only — no third-party dependencies. The companion gitleaks run
covers anything we miss with proper entropy heuristics; this script is
the always-available baseline.

Usage:
    py scripts/scan_history_secrets.py                  # scan all branches
    py scripts/scan_history_secrets.py --since 30.days  # scan recent only
    py scripts/scan_history_secrets.py --json           # machine-readable

Exit code:
    0 — clean OR all hits matched against the known-rotated allowlist
    1 — at least one hit needs attention

Pattern catalogue (additive — file an issue when a new shape appears):
    Anthropic                 sk-ant-...
    OpenAI legacy             sk-...
    Stripe-style (WorkOS too) sk_test_..., sk_live_...
    GitHub PAT                ghp_..., gho_..., ghs_..., ghr_...
    GitHub fine-grained PAT   github_pat_...
    GitLab PAT                glpat-...
    Slack webhook             hooks.slack.com/services/...
    Slack token               xox(b|p|a|s)-...
    AWS access key            AKIA[A-Z0-9]{16}, ASIA[A-Z0-9]{16}
    Google API key            AIza[0-9A-Za-z-_]{35}
    Cloudflare API token      40-char alphanumeric (advisory — many false +)
    Twilio                    SK[a-f0-9]{32}, AC[a-f0-9]{32}
    SSH private key block     -----BEGIN ... PRIVATE KEY-----

Allowlist:
    Past leaks already rotated and confirmed dead are listed in
    KNOWN_ROTATED below. A hit matching one of those secrets is reported
    but does NOT cause exit-1.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

# ── Patterns ──────────────────────────────────────────────────────────────────

PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # (label, severity, regex)
    ("anthropic_api_key",       "HIGH",  re.compile(r"sk-ant-(?:api|admin)\d+-[A-Za-z0-9_\-]{60,}")),
    ("openai_api_key_legacy",   "HIGH",  re.compile(r"sk-(?!ant-)[A-Za-z0-9]{48}")),
    ("stripe_workos_test",      "HIGH",  re.compile(r"sk_test_[A-Za-z0-9]{24,}")),
    ("stripe_workos_live",      "CRIT",  re.compile(r"sk_live_[A-Za-z0-9]{24,}")),
    ("github_pat_classic",      "HIGH",  re.compile(r"gh[posr]_[A-Za-z0-9]{36,}")),
    ("github_pat_fine_grained", "HIGH",  re.compile(r"github_pat_[A-Za-z0-9_]{60,}")),
    ("gitlab_pat",              "HIGH",  re.compile(r"glpat-[A-Za-z0-9_\-]{20,}")),
    ("slack_webhook",           "HIGH",  re.compile(r"https?://hooks\.slack\.com/services/[A-Z0-9/_\-]{30,}")),
    ("slack_token",             "HIGH",  re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("aws_access_key",          "CRIT",  re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("google_api_key",          "HIGH",  re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("twilio_sid",              "MED",   re.compile(r"\bAC[a-f0-9]{32}\b")),
    ("twilio_secret",           "HIGH",  re.compile(r"\bSK[a-f0-9]{32}\b")),
    ("private_key_block",       "CRIT",  re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("cloudflare_token_advisory","LOW",  re.compile(r"\bcloudflare[_\- ]?api[_\- ]?token\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{40,})['\"]?", re.IGNORECASE)),
    ("password_assignment",     "LOW",   re.compile(r"\bpassword\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]", re.IGNORECASE)),
]


# ── Allowlist of known-rotated secrets ──────────────────────────────────────
#
# Documented in CLAUDE.md and memory. Any hit whose secret-portion ends in
# one of these tails was rotated in Slack / Anthropic / etc. and is dead
# tape today. Matching this list demotes a HIGH/CRIT to INFO and does NOT
# cause exit-1.
#
# Add new entries with: rotation date, original incident, remediation link.

KNOWN_ROTATED: list[str] = [
    # 2026-04-20 — Slack webhook scrubbed via git filter-branch (rewrote 214
    # commits). The filter-branch removed every blob from history, but git
    # may have unreachable objects pre-gc/repack. URLs matching the old
    # tenant prefix that survive are dead — rotation logged in CLAUDE.md.
    # The webhook prefix "T0..." is the historical Slack workspace; if we
    # see a hit on hooks.slack.com from before that date, it's the rotated one.
]


# Common false-positive tails — strings that look like secrets but are
# example/placeholder values inside code or docs.
PLACEHOLDER_TAILS = [
    "REPLACE-ME",
    "REPLACE_ME",
    "your-token-here",
    "FOOBAR",
    "0000000000",
    "YOUR_API_KEY",
    "client_x",
    "client_TEST",
]


@dataclass
class Hit:
    pattern: str
    severity: str
    commit: str
    author: str
    date: str
    path: str
    line: int
    matched: str
    rotated: bool = False

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "severity": self.severity,
            "commit": self.commit,
            "author": self.author,
            "date": self.date,
            "path": self.path,
            "line": self.line,
            "matched": self.matched_redacted(),
            "rotated": self.rotated,
        }

    def matched_redacted(self) -> str:
        """Show only the leading + trailing chars so the report doesn't
        re-leak the secret. Helps when the report itself is committed."""
        s = self.matched
        if len(s) <= 16:
            return s[:4] + "***"
        return s[:8] + "..." + s[-4:]


# ── Scanner ───────────────────────────────────────────────────────────────────

def _git_log_p(since: str | None) -> Iterable[str]:
    """Stream `git log -p --all --no-color` line by line."""
    cmd = ["git", "log", "--all", "--no-color", "-p", "--encoding=utf-8"]
    if since:
        cmd += [f"--since={since}"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            yield line
    finally:
        proc.stdout.close()
        proc.wait()


def _is_placeholder(matched: str) -> bool:
    upper = matched.upper()
    for tail in PLACEHOLDER_TAILS:
        if tail.upper() in upper:
            return True
    return False


def _is_rotated(matched: str) -> bool:
    return any(matched.endswith(suffix) for suffix in KNOWN_ROTATED)


def scan(since: str | None = None) -> list[Hit]:
    hits: list[Hit] = []
    cur_commit = ""
    cur_author = ""
    cur_date = ""
    cur_path = ""
    line_no = 0
    in_diff = False

    for raw in _git_log_p(since):
        line = raw.rstrip("\n")

        # Commit metadata
        if line.startswith("commit "):
            cur_commit = line.split(" ", 1)[1][:12]
            in_diff = False
            continue
        if line.startswith("Author:"):
            cur_author = line[7:].strip()
            continue
        if line.startswith("Date:"):
            cur_date = line[5:].strip()
            continue

        # Diff header
        if line.startswith("diff --git"):
            # diff --git a/path b/path  →  use the b/ side
            parts = line.split()
            if len(parts) >= 4:
                cur_path = parts[3].removeprefix("b/")
            in_diff = True
            line_no = 0
            continue

        # Hunk header — reset line number to the +N from "@@ -A,B +N,M @@"
        if in_diff and line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if m:
                line_no = int(m.group(1)) - 1
            continue

        if not in_diff:
            continue

        # Track + / - / context lines for line numbering
        if line.startswith("+") and not line.startswith("+++"):
            line_no += 1
            content = line[1:]
        elif line.startswith("-") and not line.startswith("---"):
            # Removed line — counts in the diff but not in the destination file
            content = line[1:]
        elif line.startswith(" "):
            line_no += 1
            content = line[1:]
        else:
            continue

        # Run every pattern against the line
        for label, severity, pat in PATTERNS:
            for m in pat.finditer(content):
                matched = m.group(0)
                if _is_placeholder(matched):
                    continue
                hits.append(Hit(
                    pattern=label,
                    severity=severity,
                    commit=cur_commit,
                    author=cur_author,
                    date=cur_date,
                    path=cur_path,
                    line=line_no if line.startswith("+") else 0,
                    matched=matched,
                    rotated=_is_rotated(matched),
                ))
    return hits


# ── Reporting ─────────────────────────────────────────────────────────────────

SEV_RANK = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3, "INFO": 4}


def _sev_rank(h: Hit) -> int:
    return (4 if h.rotated else SEV_RANK.get(h.severity, 5),
            -h.line, h.commit, h.path)


def render_text(hits: list[Hit]) -> str:
    if not hits:
        return "scan_history_secrets — clean (no pattern hits in repo history)\n"

    lines: list[str] = []
    lines.append(f"scan_history_secrets — {len(hits)} hit(s)")
    lines.append("")
    lines.append("Severity legend:")
    lines.append("  CRIT  — committed credential with broad blast radius (private key, AWS, sk_live)")
    lines.append("  HIGH  — committed credential")
    lines.append("  MED   — likely credential, lower blast radius")
    lines.append("  LOW   — pattern-only, frequent false positives")
    lines.append("  ROT   — matches a KNOWN_ROTATED entry (rotated + dead)")
    lines.append("")

    by_pattern: dict[str, list[Hit]] = defaultdict(list)
    for h in hits:
        by_pattern[h.pattern].append(h)

    for pattern, group in sorted(by_pattern.items(), key=lambda kv: SEV_RANK.get(kv[1][0].severity, 9)):
        sev = group[0].severity
        marker = "ROT" if all(h.rotated for h in group) else sev
        lines.append(f"== {pattern} ({marker}) — {len(group)} hit(s) ==")
        for h in sorted(group, key=_sev_rank):
            sev_tag = "ROT " if h.rotated else f"{h.severity:<4s}"
            lines.append(f"  [{sev_tag}] {h.commit}  {h.path}:{h.line}  {h.matched_redacted()}")
            lines.append(f"           {h.author}  {h.date}")
        lines.append("")

    n_unrotated = sum(1 for h in hits if not h.rotated)
    n_rotated = sum(1 for h in hits if h.rotated)
    lines.append(f"Summary: {len(hits)} hit(s) ({n_unrotated} live, {n_rotated} known-rotated)")
    if n_unrotated:
        lines.append("")
        lines.append("ACTION: Inspect each unrotated HIGH/CRIT hit. Rotate the credential, then add")
        lines.append("        the rotated tail to KNOWN_ROTATED in this script.")
    return "\n".join(lines) + "\n"


def render_json(hits: list[Hit]) -> str:
    return json.dumps([h.to_dict() for h in hits], indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Pattern-scan git history for committed secrets")
    parser.add_argument("--since", help="git log --since= argument (e.g. 30.days, 2026-01-01)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    hits = scan(since=args.since)

    if args.json:
        print(render_json(hits))
    else:
        print(render_text(hits))

    n_unrotated = sum(1 for h in hits if not h.rotated)
    return 1 if n_unrotated > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
