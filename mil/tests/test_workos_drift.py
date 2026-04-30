"""test_workos_drift.py — MIL-120 drift gate.

Compares mil/config/workos.yaml (single source of truth) against each
Cloudflare Worker's wrangler.toml [vars] block. CI fails if any value
disagrees, so a fork operator who edits one but not the others gets
caught at PR time rather than at deploy time.

The actual drift logic lives in mil/auth/scripts/check_workos_drift.py;
this test imports it and asserts a clean run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mil.auth.scripts import check_workos_drift as drift  # noqa: E402
from mil.config import workos_loader as wl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    wl._load.cache_clear()
    yield
    wl._load.cache_clear()


class TestLiveDrift:
    """Live tree — workos.yaml must agree with all three wrangler.toml files."""

    def test_no_drift_in_live_tree(self):
        drifts = drift.check_drift()
        assert drifts == [], "WorkOS drift detected:\n  " + "\n  ".join(drifts)


class TestDriftDetection:
    """Synthetic drift — verify the checker actually catches mismatches."""

    def test_detects_mismatched_client_id(self, tmp_path, monkeypatch):
        # Build a minimal wrangler.toml with a deliberately wrong CLIENT_ID.
        bad_toml = tmp_path / "wrangler.toml"
        bad_toml.write_text(
            'name = "test"\n'
            "[vars]\n"
            'CLIENT_ID = "client_WRONG"\n'
            'JWKS_URL = "https://ideal-log-65-staging.authkit.app/oauth2/jwks"\n'
            'EXPECTED_AUD = "client_WRONG"\n'
            'EXPECTED_ISS = "https://api.workos.com/user_management/client_WRONG"\n'
            'AUTHKIT_HOST = "ideal-log-65-staging.authkit.app"\n',
            encoding="utf-8",
        )
        # Override WORKERS to point at our bad fixture.
        monkeypatch.setattr(drift, "WORKERS", [
            ("test-fixture", bad_toml, [
                ("CLIENT_ID",     wl.client_id),
                ("EXPECTED_AUD",  wl.expected_aud),
                ("EXPECTED_ISS",  wl.expected_iss),
            ]),
        ])
        drifts = drift.check_drift()
        assert len(drifts) == 3  # CLIENT_ID + EXPECTED_AUD + EXPECTED_ISS
        assert any("CLIENT_ID" in d and "client_WRONG" in d for d in drifts)
        assert any("EXPECTED_ISS" in d for d in drifts)

    def test_detects_missing_var(self, tmp_path, monkeypatch):
        bad_toml = tmp_path / "wrangler.toml"
        bad_toml.write_text(
            'name = "test"\n'
            "[vars]\n"
            # Deliberately no JWKS_URL set
            'CLIENT_ID = "client_01KPY7CA07ZD1WG3DMQE1FZQE1"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(drift, "WORKERS", [
            ("test-fixture", bad_toml, [
                ("JWKS_URL", wl.jwks_url),
            ]),
        ])
        drifts = drift.check_drift()
        assert len(drifts) == 1
        assert "missing from wrangler.toml" in drifts[0]
        assert "JWKS_URL" in drifts[0]

    def test_clean_when_values_match(self, tmp_path, monkeypatch):
        good_toml = tmp_path / "wrangler.toml"
        good_toml.write_text(
            'name = "test"\n'
            "[vars]\n"
            f'CLIENT_ID = "{wl.client_id()}"\n'
            f'JWKS_URL = "{wl.jwks_url()}"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(drift, "WORKERS", [
            ("test-fixture", good_toml, [
                ("CLIENT_ID", wl.client_id),
                ("JWKS_URL",  wl.jwks_url),
            ]),
        ])
        assert drift.check_drift() == []

    def test_skips_check_when_workos_value_is_none(self, tmp_path, monkeypatch):
        # Production env may have null values pre-populate. Drift checker
        # should silently skip rather than report drift in that case.
        good_toml = tmp_path / "wrangler.toml"
        good_toml.write_text('name = "test"\n[vars]\nFOO = "bar"\n', encoding="utf-8")
        # accessor returns None
        monkeypatch.setattr(drift, "WORKERS", [
            ("test-fixture", good_toml, [
                ("ANY_VAR", lambda: None),
            ]),
        ])
        assert drift.check_drift() == []
