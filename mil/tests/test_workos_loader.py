"""test_workos_loader.py — MIL-120 workos.yaml loader behaviour.

Covers active_env validation, env-block accessors, derived expected_iss,
api_key env-var indirection, and require_*() variants.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mil.config import workos_loader as wl


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "workos.yaml"
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _reset_cache():
    wl._load.cache_clear()
    yield
    wl._load.cache_clear()


# ── active_env ──────────────────────────────────────────────────────────────

class TestActiveEnv:
    def test_default_when_missing(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "envs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.active_env() == "staging"

    def test_explicit_staging(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "active_env: staging\nenvs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.active_env() == "staging"

    def test_explicit_production(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "active_env: production\nenvs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.active_env() == "production"

    def test_invalid_value_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "active_env: dev\nenvs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="must be one of"):
            wl.active_env()


# ── env-block accessors ─────────────────────────────────────────────────────

class TestEnvBlock:
    def test_explicit_values(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: staging
envs:
  staging:
    organisation_id: org_TEST
    client_id: client_TEST
    jwks_url: https://test.example/oauth2/jwks
    authkit_domain: test.example
    custom_domain_pending: login.test.example
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.organisation_id() == "org_TEST"
        assert wl.client_id() == "client_TEST"
        assert wl.jwks_url() == "https://test.example/oauth2/jwks"
        assert wl.authkit_domain() == "test.example"
        assert wl.custom_domain_pending() == "login.test.example"

    def test_unset_fields_return_none(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: production
envs:
  production:
    organisation_id: null
    client_id: null
    jwks_url: null
    authkit_domain: null
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.organisation_id() is None
        assert wl.client_id() is None
        assert wl.jwks_url() is None
        assert wl.authkit_domain() is None
        assert wl.expected_iss() is None
        assert wl.expected_aud() is None

    def test_active_env_block_missing(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: production
envs:
  staging:
    client_id: client_OnlyStaging
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        # Active env (production) has no block — every accessor returns None.
        assert wl.client_id() is None
        assert wl.organisation_id() is None

    def test_jwks_url_must_be_absolute(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: staging
envs:
  staging:
    jwks_url: /oauth2/jwks
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="absolute URL"):
            wl.jwks_url()

    def test_authkit_domain_rejects_scheme(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: staging
envs:
  staging:
    authkit_domain: https://test.example
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="bare hostname"):
            wl.authkit_domain()


# ── derived values ──────────────────────────────────────────────────────────

class TestDerivedValues:
    def test_expected_iss_derives_from_client_id(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: staging
envs:
  staging:
    client_id: client_DERIVE_TEST
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.expected_iss() == "https://api.workos.com/user_management/client_DERIVE_TEST"

    def test_expected_aud_equals_client_id(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: staging
envs:
  staging:
    client_id: client_AUD_TEST
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.expected_aud() == "client_AUD_TEST"

    def test_expected_iss_none_when_client_id_unset(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "active_env: staging\nenvs:\n  staging:\n    client_id: null\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.expected_iss() is None


# ── API key indirection ─────────────────────────────────────────────────────

class TestApiKey:
    def test_default_env_var_name(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "envs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.api_key_env_var() == "WORKOS_API_KEY"

    def test_custom_env_var_name(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "api_key_env_var: ACME_WORKOS_KEY\nenvs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.api_key_env_var() == "ACME_WORKOS_KEY"

    def test_api_key_reads_from_environ(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "envs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        monkeypatch.setenv("WORKOS_API_KEY", "sk_test_FOOBAR")
        assert wl.api_key() == "sk_test_FOOBAR"

    def test_api_key_none_when_unset(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "envs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        monkeypatch.delenv("WORKOS_API_KEY", raising=False)
        assert wl.api_key() is None


# ── require_*() variants ────────────────────────────────────────────────────

class TestRequireVariants:
    def test_require_raises_on_unset_client_id(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "active_env: production\nenvs:\n  production:\n    client_id: null\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="unset.*populate"):
            wl.require_client_id()

    def test_require_returns_value_when_set(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
active_env: staging
envs:
  staging:
    client_id: client_REQUIRED
""")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        assert wl.require_client_id() == "client_REQUIRED"

    def test_require_api_key_raises_when_unset(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "envs: {}\n")
        monkeypatch.setattr(wl, "_CONFIG_PATH", p)
        monkeypatch.delenv("WORKOS_API_KEY", raising=False)
        with pytest.raises(ValueError, match="WorkOS API key not set"):
            wl.require_api_key()


# ── live YAML smoke ─────────────────────────────────────────────────────────

class TestLiveYAML:
    """Live cjipro.com tenant — the staging WorkOS env must load cleanly."""

    def test_active_env_is_staging(self):
        assert wl.active_env() == "staging"

    def test_staging_identifiers_loaded(self):
        assert wl.client_id() == "client_01KPY7CA07ZD1WG3DMQE1FZQE1"
        assert wl.organisation_id() == "org_01KPY8K0RGC6ABNTC73YMW9ERP"
        assert wl.authkit_domain() == "ideal-log-65-staging.authkit.app"

    def test_expected_iss_matches_wrangler_toml_pattern(self):
        # Same shape that edge-bouncer / magic-link / app-cjipro use.
        assert wl.expected_iss() == (
            "https://api.workos.com/user_management/client_01KPY7CA07ZD1WG3DMQE1FZQE1"
        )

    def test_jwks_url_on_authkit_domain(self):
        # Must be on the AuthKit domain, not api.workos.com — the SSO-domain
        # path serves keys that don't validate AuthKit-issued tokens.
        assert wl.jwks_url() == "https://ideal-log-65-staging.authkit.app/oauth2/jwks"
