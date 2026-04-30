"""mil/auth/scripts/check_workos_drift.py — MIL-120 drift gate.

Compares mil/config/workos.yaml (single source of truth for non-secret
WorkOS identifiers) against the [vars] blocks of each Cloudflare Worker's
wrangler.toml. A fork operator who edits one but forgets the others gets
a CI failure rather than a silent broken auth flow.

Why this matters: Cloudflare Workers can't read filesystem at runtime, so
the Workers' WorkOS identifiers must be inlined into wrangler.toml as env
[vars]. That duplicates workos.yaml. The fix isn't to remove the dup
(deploy needs them) but to verify it.

Usage:
    py mil/auth/scripts/check_workos_drift.py
        Exit 0 = drift-clean. Exit 1 = drift detected, drift report printed.

Also invoked by mil/tests/test_workos_drift.py so `py -m pytest` catches
drift on every test run.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MIL_ROOT = REPO_ROOT / "mil"
sys.path.insert(0, str(REPO_ROOT))

from mil.config import workos_loader  # noqa: E402

# Workers whose wrangler.toml [vars] blocks must agree with workos.yaml.
# Each entry is a (label, path, fields) triple where `fields` lists the
# wrangler.toml var names this Worker is expected to set + the workos_loader
# accessor that produces the canonical value.
WORKERS: list[tuple[str, Path, list[tuple[str, callable]]]] = [
    (
        "edge-bouncer",
        MIL_ROOT / "auth" / "edge_bouncer" / "wrangler.toml",
        [
            ("JWKS_URL",     workos_loader.jwks_url),
            ("EXPECTED_AUD", workos_loader.expected_aud),
            ("EXPECTED_ISS", workos_loader.expected_iss),
        ],
    ),
    (
        "magic-link",
        MIL_ROOT / "auth" / "magic_link" / "wrangler.toml",
        [
            ("AUTHKIT_HOST",  workos_loader.authkit_domain),
            ("CLIENT_ID",     workos_loader.client_id),
            ("JWKS_URL",      workos_loader.jwks_url),
            ("EXPECTED_AUD",  workos_loader.expected_aud),
            ("EXPECTED_ISS",  workos_loader.expected_iss),
        ],
    ),
    (
        "app-cjipro",
        MIL_ROOT / "auth" / "app_cjipro" / "wrangler.toml",
        [
            ("JWKS_URL",     workos_loader.jwks_url),
            ("EXPECTED_AUD", workos_loader.expected_aud),
            ("EXPECTED_ISS", workos_loader.expected_iss),
        ],
    ),
]


class DriftError(Exception):
    """Raised when a wrangler.toml [vars] value disagrees with workos.yaml."""


def _vars_block(toml_path: Path) -> dict:
    """Read the [vars] block of a wrangler.toml. Returns {} if missing."""
    if not toml_path.exists():
        raise DriftError(f"wrangler.toml not found: {toml_path}")
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    block = data.get("vars") or {}
    if not isinstance(block, dict):
        raise DriftError(f"{toml_path}: [vars] is not a table")
    return block


def check_drift() -> list[str]:
    """Returns a list of drift messages. Empty list = drift-clean."""
    drifts: list[str] = []

    for label, toml_path, fields in WORKERS:
        try:
            block = _vars_block(toml_path)
        except DriftError as exc:
            drifts.append(str(exc))
            continue

        for var_name, accessor in fields:
            expected = accessor()
            actual = block.get(var_name)

            if expected is None:
                # workos.yaml hasn't populated this env (e.g. production
                # block is null). Nothing to compare against — skip.
                continue

            if actual is None:
                drifts.append(
                    f"[{label}] {var_name}: missing from wrangler.toml [vars] "
                    f"(workos.yaml expects {expected!r})"
                )
                continue

            if not isinstance(actual, str):
                drifts.append(
                    f"[{label}] {var_name}: wrangler.toml has {type(actual).__name__}, "
                    f"expected string {expected!r}"
                )
                continue

            if actual != expected:
                drifts.append(
                    f"[{label}] {var_name}: wrangler.toml = {actual!r}, "
                    f"workos.yaml expects {expected!r}"
                )

    return drifts


def main() -> int:
    drifts = check_drift()
    if not drifts:
        print(f"[workos-drift] OK — workos.yaml ({workos_loader.active_env()}) "
              f"matches all {len(WORKERS)} wrangler.toml [vars] blocks")
        return 0

    print(f"[workos-drift] {len(drifts)} drift(s) detected:", file=sys.stderr)
    for msg in drifts:
        print(f"  {msg}", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "Fix: edit each wrangler.toml [vars] block to match workos.yaml "
        f"(active_env={workos_loader.active_env()!r}), or update workos.yaml "
        "if the wrangler value is the new ground truth.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
