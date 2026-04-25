"""Import MIL Jira tickets into GitLab Issues.

Reads ops/gitlab_import/jira_tickets.json (built from Atlassian MCP queries) and
posts one GitLab issue per Jira ticket. Closes issues whose Jira status == Done.

Idempotent on title prefix `[MIL-N]` — re-running skips tickets that already have
a matching issue title in GitLab.

Auth: GITLAB_TOKEN, GITLAB_BASE_URL, GITLAB_PROJECT_ID from .env (root of repo).

Usage:
    py ops/gitlab_import/import_jira_to_gitlab.py            # import + close
    py ops/gitlab_import/import_jira_to_gitlab.py --dry-run  # plan only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JIRA_FILE = REPO_ROOT / "ops" / "gitlab_import" / "jira_tickets.json"
JIRA_BROWSE = "https://cjipro.atlassian.net/browse"


def load_env() -> dict:
    env = {}
    env_path = REPO_ROOT / ".env"
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def gl_request(env, method, path, body=None):
    url = f"{env['GITLAB_BASE_URL']}/api/v4{path}"
    data = None
    headers = {"PRIVATE-TOKEN": env["GITLAB_TOKEN"]}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_existing_titles(env, pid):
    """Return set of titles already present in the project (any state)."""
    titles = set()
    page = 1
    while True:
        path = f"/projects/{pid}/issues?per_page=100&page={page}&state=all"
        try:
            issues = gl_request(env, "GET", path)
        except Exception as e:
            print(f"  WARN: could not list page {page}: {e}", file=sys.stderr)
            break
        if not issues:
            break
        for iss in issues:
            titles.add(iss["title"])
        if len(issues) < 100:
            break
        page += 1
    return titles


def status_label(status: str) -> str:
    return {
        "Done": "status::done",
        "In Progress": "status::in-progress",
        "To Do": "status::to-do",
    }.get(status, f"status::{status.lower().replace(' ', '-')}")


def phase_label(key: str) -> str:
    n = int(key.split("-")[1])
    if n <= 10:
        return "phase::0-foundation"
    if n <= 24:
        return "phase::1-harvester"
    if n <= 31:
        return "phase::2-intelligence"
    if 32 <= n <= 38 or n == 48:
        return "phase::a-clone-foundation"
    if 39 <= n <= 47:
        return "phase::ask-cji-pro-v1"
    if 49 <= n <= 58:
        return "phase::comms"
    if 59 <= n <= 72:
        return "phase::login-journey"
    if 73 <= n <= 74:
        return "phase::post-soak"
    if 75 <= n <= 108:
        return "phase::website-rebuild"
    return "phase::other"


def build_body(t: dict) -> str:
    return (
        f"**Jira:** [{t['key']}]({JIRA_BROWSE}/{t['key']})  \n"
        f"**Status (Jira):** {t['status']}  \n\n"
        f"Imported from Jira to GitLab on 2026-04-25. "
        f"Jira remains the source of truth for ticket workflow; "
        f"GitLab Issues mirror state at import time.\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Import only N tickets (debug)")
    args = ap.parse_args()

    env = load_env()
    for k in ("GITLAB_TOKEN", "GITLAB_BASE_URL", "GITLAB_PROJECT_ID"):
        if not env.get(k):
            print(f"ERROR: {k} missing from .env", file=sys.stderr)
            sys.exit(2)

    pid = env["GITLAB_PROJECT_ID"]
    tickets = json.loads(JIRA_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(tickets)} Jira tickets from {JIRA_FILE.relative_to(REPO_ROOT)}")

    print(f"Fetching existing GitLab issue titles for project {pid}...")
    existing = fetch_existing_titles(env, pid)
    print(f"  {len(existing)} existing titles")

    if args.limit:
        tickets = tickets[: args.limit]
        print(f"  --limit {args.limit}: importing first {len(tickets)} only")

    created = skipped = closed = errored = 0
    log_lines = []

    for i, t in enumerate(tickets, 1):
        title = f"[{t['key']}] {t['summary']}"
        if title in existing:
            skipped += 1
            log_lines.append(f"SKIP    {t['key']}  (already exists)")
            continue

        labels = ",".join(["mil", status_label(t["status"]), phase_label(t["key"])])
        body = {
            "title": title,
            "description": build_body(t),
            "labels": labels,
        }

        if args.dry_run:
            log_lines.append(f"PLAN    {t['key']}  -> {labels}  state={t['state']}")
            created += 1
            continue

        try:
            issue = gl_request(env, "POST", f"/projects/{pid}/issues", body)
            iid = issue["iid"]
            log_lines.append(f"CREATE  {t['key']}  -> #{iid}  {labels}")
            created += 1
            if t["state"] == "closed":
                gl_request(
                    env, "PUT",
                    f"/projects/{pid}/issues/{iid}?state_event=close",
                )
                closed += 1
                log_lines.append(f"CLOSE   {t['key']}  -> #{iid}")
            time.sleep(0.15)  # courtesy throttle, ~6 req/s
        except Exception as e:
            errored += 1
            log_lines.append(f"ERROR   {t['key']}  {e}")
            print(f"  [{i}/{len(tickets)}] {t['key']} ERROR: {e}", file=sys.stderr)
            continue

        if i % 20 == 0:
            print(f"  [{i}/{len(tickets)}] created={created} closed={closed} errored={errored}")

    print()
    print(f"DONE: created={created} closed={closed} skipped={skipped} errored={errored}")

    log_path = REPO_ROOT / "ops" / "gitlab_import" / "import_log.txt"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"Log: {log_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
