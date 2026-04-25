"""ops/cloudflare/cf.py — Cloudflare API CLI wrapper (stdlib-only).

Uses a Cloudflare API Token (CLOUDFLARE_API_TOKEN env var or .env file)
with broader scope than the MCP OAuth grant. Generated per
ops/runbooks/cloudflare_api_token_setup.md.

Default zone: cjipro.com. Override: --zone NAME.

Subcommands:
    zone-info
    dns-list
    dns-add        --type TYPE --name N --content C [--proxied] [--ttl T] [--comment X]
    dns-delete     RECORD_ID
    email-route-list
    email-route-add  LOCAL_PART  DESTINATION
    email-route-delete  RULE_ID
    cache-purge    [--urls URL [URL ...]]
    worker-route-add  PATTERN  --service NAME

Examples:
    py ops/cloudflare/cf.py dns-list
    py ops/cloudflare/cf.py dns-add --type AAAA --name app --content 100:: --proxied --comment "MIL-82 reservation"
    py ops/cloudflare/cf.py email-route-add security hussain.marketing@gmail.com
    py ops/cloudflare/cf.py cache-purge --urls https://cjipro.com/ https://cjipro.com/insights/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_ZONE = "cjipro.com"
_ZONE_CACHE: dict[str, str] = {}


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _token() -> str:
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not tok:
        sys.exit(
            "error: CLOUDFLARE_API_TOKEN not set in env or .env. "
            "See ops/runbooks/cloudflare_api_token_setup.md."
        )
    return tok


def _request(method: str, path: str, *, body: Any = None, query: dict | None = None) -> dict:
    url = API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body_text)
        except ValueError:
            return {"success": False, "errors": [{"code": e.code, "message": body_text[:300]}]}


def _zone_id(name: str) -> str:
    if name in _ZONE_CACHE:
        return _ZONE_CACHE[name]
    p = _request("GET", "/zones", query={"name": name})
    if not p.get("success") or not p.get("result"):
        sys.exit(f"error: zone {name} not found / access denied: {p.get('errors')}")
    zid = p["result"][0]["id"]
    _ZONE_CACHE[name] = zid
    return zid


def _fail(p: dict) -> None:
    msg = p.get("errors") or p.get("messages") or p
    sys.exit(f"error: {json.dumps(msg, default=str)}")


# ── commands ─────────────────────────────────────────────────────

def cmd_zone_info(args) -> int:
    p = _request("GET", f"/zones/{_zone_id(args.zone)}")
    if not p.get("success"):
        _fail(p)
    r = p["result"]
    print(f"name:    {r['name']}")
    print(f"id:      {r['id']}")
    print(f"status:  {r['status']}")
    print(f"plan:    {r['plan']['name']}")
    print(f"ns:      {', '.join(r.get('name_servers', []))}")
    return 0


def cmd_dns_list(args) -> int:
    p = _request("GET", f"/zones/{_zone_id(args.zone)}/dns_records", query={"per_page": 200})
    if not p.get("success"):
        _fail(p)
    print(f"{'NAME':38s}  {'TYPE':6s}  {'PROX':4s}  {'ID':32s}  CONTENT")
    for r in p["result"]:
        prox = "yes" if r.get("proxied") else "no"
        content = (r.get("content") or "")[:80]
        print(f"{r['name']:38s}  {r['type']:6s}  {prox:4s}  {r['id']:32s}  {content}")
    return 0


def cmd_dns_add(args) -> int:
    body = {
        "type": args.type,
        "name": args.name,
        "content": args.content,
        "ttl": args.ttl,
        "proxied": args.proxied,
    }
    if args.comment:
        body["comment"] = args.comment
    p = _request("POST", f"/zones/{_zone_id(args.zone)}/dns_records", body=body)
    if not p.get("success"):
        _fail(p)
    r = p["result"]
    print(f"OK  {r['name']}  {r['type']}  -> {r['content']}  proxied={r['proxied']}  id={r['id']}")
    return 0


def cmd_dns_delete(args) -> int:
    p = _request("DELETE", f"/zones/{_zone_id(args.zone)}/dns_records/{args.record_id}")
    if not p.get("success"):
        _fail(p)
    print(f"OK  deleted {args.record_id}")
    return 0


def cmd_email_route_list(args) -> int:
    p = _request("GET", f"/zones/{_zone_id(args.zone)}/email/routing/rules", query={"per_page": 100})
    if not p.get("success"):
        _fail(p)
    for r in p.get("result", []):
        match = r.get("matchers", [{}])[0].get("value", "?")
        action = r.get("actions", [{}])[0]
        dest = ", ".join(action.get("value") or []) or action.get("type", "?")
        enabled = "on" if r.get("enabled") else "off"
        print(f"{enabled:3s}  {match:40s}  -> {dest}  tag={r.get('tag')}")
    return 0


def cmd_email_route_add(args) -> int:
    addr = f"{args.local_part}@{args.zone}"
    body = {
        "name": f"Route {addr}",
        "matchers": [{"type": "literal", "field": "to", "value": addr}],
        "actions": [{"type": "forward", "value": [args.destination]}],
        "enabled": True,
        "priority": 0,
    }
    p = _request("POST", f"/zones/{_zone_id(args.zone)}/email/routing/rules", body=body)
    if not p.get("success"):
        _fail(p)
    print(f"OK  routed {addr} -> {args.destination}  tag={p['result']['tag']}")
    return 0


def cmd_email_route_delete(args) -> int:
    p = _request("DELETE", f"/zones/{_zone_id(args.zone)}/email/routing/rules/{args.rule_id}")
    if not p.get("success"):
        _fail(p)
    print(f"OK  deleted route {args.rule_id}")
    return 0


def cmd_cache_purge(args) -> int:
    body: dict[str, Any] = {"files": args.urls} if args.urls else {"purge_everything": True}
    p = _request("POST", f"/zones/{_zone_id(args.zone)}/purge_cache", body=body)
    if not p.get("success"):
        _fail(p)
    target = f"{len(args.urls)} URLs" if args.urls else "everything"
    print(f"OK  purged {target}")
    return 0


def cmd_worker_route_add(args) -> int:
    body = {"pattern": args.pattern, "script": args.service}
    p = _request("POST", f"/zones/{_zone_id(args.zone)}/workers/routes", body=body)
    if not p.get("success"):
        _fail(p)
    print(f"OK  route {args.pattern} -> {args.service}  id={p['result']['id']}")
    return 0


# ── argparse plumbing ────────────────────────────────────────────

def main() -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="cf", description="Cloudflare API CLI wrapper")
    p.add_argument("--zone", default=DEFAULT_ZONE, help=f"zone name (default {DEFAULT_ZONE})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("zone-info", help="show zone summary").set_defaults(func=cmd_zone_info)
    sub.add_parser("dns-list", help="list DNS records").set_defaults(func=cmd_dns_list)

    a = sub.add_parser("dns-add", help="add a DNS record")
    a.add_argument("--type", required=True, choices=["A", "AAAA", "CNAME", "TXT", "MX"])
    a.add_argument("--name", required=True)
    a.add_argument("--content", required=True)
    a.add_argument("--ttl", type=int, default=1)
    a.add_argument("--proxied", action="store_true")
    a.add_argument("--comment", default="")
    a.set_defaults(func=cmd_dns_add)

    d = sub.add_parser("dns-delete", help="delete a DNS record by id")
    d.add_argument("record_id")
    d.set_defaults(func=cmd_dns_delete)

    sub.add_parser("email-route-list", help="list Email Routing rules").set_defaults(func=cmd_email_route_list)

    er = sub.add_parser("email-route-add", help="add an Email Routing forward rule")
    er.add_argument("local_part", help="address local-part, e.g. security")
    er.add_argument("destination", help="forward destination email")
    er.set_defaults(func=cmd_email_route_add)

    erd = sub.add_parser("email-route-delete", help="delete an Email Routing rule by tag/id")
    erd.add_argument("rule_id")
    erd.set_defaults(func=cmd_email_route_delete)

    cp = sub.add_parser("cache-purge", help="purge Cloudflare cache (everything or specific URLs)")
    cp.add_argument("--urls", nargs="*", default=[])
    cp.set_defaults(func=cmd_cache_purge)

    wr = sub.add_parser("worker-route-add", help="bind a Worker route pattern to a service")
    wr.add_argument("pattern", help='route pattern e.g. "app.cjipro.com/*"')
    wr.add_argument("--service", required=True, help="Worker script name")
    wr.set_defaults(func=cmd_worker_route_add)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
