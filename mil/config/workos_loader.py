"""mil/config/workos_loader.py — typed accessors for workos.yaml (MIL-120).

WorkOS is the auth provider for the cjipro.com hosted reference instance.
A fork that wants to operate its own auth tenant edits mil/config/workos.yaml
(non-secret identifiers) and sets WORKOS_API_KEY in .env (secret).

The TypeScript Workers (mil/auth/edge_bouncer, magic_link, app_cjipro) read
identical values from their wrangler.toml [vars] blocks. That duplication is
unavoidable because Cloudflare Workers can't read the Python YAML at runtime,
but it IS load-bearing for forkability — the drift checker in
mil/auth/scripts/check_workos_drift.py compares workos.yaml to each
wrangler.toml on every test run, so a fork operator who edits one but not
the others gets a CI failure rather than a silent broken auth flow.

Public API:
    active_env()             -> str            "staging" or "production"
    organisation_id()        -> str | None
    client_id()              -> str | None
    jwks_url()               -> str | None
    authkit_domain()         -> str | None
    expected_iss()           -> str | None     derived from client_id
    expected_aud()           -> str | None     equal to client_id
    custom_domain_pending()  -> str | None
    api_key_env_var()        -> str            name of the env var holding the secret
    api_key()                -> str | None     reads the actual secret from os.environ

Production env values default to None when not yet populated (the YAML ships
with `null` placeholders). Callers expecting a string must guard, OR call
require_*() variants that raise instead of returning None.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "workos.yaml"

_DEFAULT_API_KEY_ENV_VAR = "WORKOS_API_KEY"
_VALID_ENVS = {"staging", "production"}


@lru_cache(maxsize=1)
def _load() -> dict:
    if not _CONFIG_PATH.exists():
        logger.warning("workos.yaml not found at %s — accessors return None", _CONFIG_PATH)
        return {}
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"workos.yaml root must be a mapping, got {type(raw).__name__}")
    return raw


def active_env() -> str:
    raw = _load()
    val = raw.get("active_env")
    if val is None:
        return "staging"
    if not isinstance(val, str) or val not in _VALID_ENVS:
        raise ValueError(f"workos.yaml active_env must be one of {sorted(_VALID_ENVS)}, got {val!r}")
    return val


def _env_block() -> dict:
    raw = _load()
    envs = raw.get("envs") or {}
    if not isinstance(envs, dict):
        raise ValueError(f"workos.yaml envs must be a mapping, got {type(envs).__name__}")
    block = envs.get(active_env()) or {}
    if not isinstance(block, dict):
        raise ValueError(f"workos.yaml envs.{active_env()} must be a mapping")
    return block


def _opt_str(field: str) -> str | None:
    val = _env_block().get(field)
    if val is None:
        return None
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"workos.yaml envs.{active_env()}.{field} must be a non-empty string when present, got {val!r}")
    return val.strip()


def organisation_id() -> str | None:
    return _opt_str("organisation_id")


def client_id() -> str | None:
    return _opt_str("client_id")


def jwks_url() -> str | None:
    val = _opt_str("jwks_url")
    if val and not val.startswith(("http://", "https://")):
        raise ValueError(f"workos.yaml envs.{active_env()}.jwks_url must be an absolute URL, got {val!r}")
    return val


def authkit_domain() -> str | None:
    val = _opt_str("authkit_domain")
    if val and ("://" in val or "/" in val):
        raise ValueError(f"workos.yaml envs.{active_env()}.authkit_domain must be a bare hostname, got {val!r}")
    return val


def custom_domain_pending() -> str | None:
    val = _opt_str("custom_domain_pending")
    if val and ("://" in val or "/" in val):
        raise ValueError(f"workos.yaml envs.{active_env()}.custom_domain_pending must be a bare hostname, got {val!r}")
    return val


def expected_iss() -> str | None:
    """Issuer string used by Cloudflare Workers' jose JWT verifier.

    WorkOS access tokens (the JWTs riding in the session cookie) carry
    `iss = https://api.workos.com/user_management/<client_id>`. The
    AuthKit domain is the iss of ID tokens, NOT access tokens —
    documented in CLAUDE.md from the 2026-04-25 wrangler tail incident.
    """
    cid = client_id()
    if not cid:
        return None
    return f"https://api.workos.com/user_management/{cid}"


def expected_aud() -> str | None:
    """Audience claim — equal to the OAuth client_id."""
    return client_id()


def api_key_env_var() -> str:
    raw = _load()
    val = raw.get("api_key_env_var")
    if val is None:
        return _DEFAULT_API_KEY_ENV_VAR
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"workos.yaml api_key_env_var must be a non-empty string, got {val!r}")
    return val.strip()


def api_key() -> str | None:
    """Read the API secret from os.environ — never from YAML."""
    return os.environ.get(api_key_env_var()) or None


# ── require_*() variants that raise on None ──────────────────────────────────

def _require(name: str, val: object) -> str:
    if not val or not isinstance(val, str):
        raise ValueError(
            f"workos.yaml envs.{active_env()}.{name} is unset — populate before deploying"
        )
    return val


def require_organisation_id() -> str:
    return _require("organisation_id", organisation_id())


def require_client_id() -> str:
    return _require("client_id", client_id())


def require_jwks_url() -> str:
    return _require("jwks_url", jwks_url())


def require_authkit_domain() -> str:
    return _require("authkit_domain", authkit_domain())


def require_expected_iss() -> str:
    return _require("expected_iss", expected_iss())


def require_api_key() -> str:
    val = api_key()
    if not val:
        raise ValueError(
            f"WorkOS API key not set — expected env var {api_key_env_var()!r}"
        )
    return val


# ── CLI smoke ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    print(f"active_env:              {active_env()!r}")
    print(f"organisation_id:         {organisation_id()!r}")
    print(f"client_id:               {client_id()!r}")
    print(f"jwks_url:                {jwks_url()!r}")
    print(f"authkit_domain:          {authkit_domain()!r}")
    print(f"expected_iss:            {expected_iss()!r}")
    print(f"expected_aud:            {expected_aud()!r}")
    print(f"custom_domain_pending:   {custom_domain_pending()!r}")
    print(f"api_key_env_var:         {api_key_env_var()!r}")
    print(f"api_key:                 {'<set>' if api_key() else '<unset>'}")
