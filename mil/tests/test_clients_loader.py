"""test_clients_loader.py — MIL-85 + MIL-155 loader behaviour.

Focus on the email_domains validation rules added in MIL-155: lowercase,
no leading "@", duplicate-domain detection across slugs. Live YAML
sanity-check (barclays domains exist) at the bottom; the rest exercises
_validate_entry / clients() through synthetic dicts so test data does not
depend on real config drifting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mil.config.clients_loader import (
    _validate_entry,
    domain_to_slug,
    clients,
)


def _entry(**overrides):
    base = {
        "client_slug": "acme",
        "display_name": "Acme",
        "market_tier": "incumbent",
        "status": "monitored",
    }
    base.update(overrides)
    return base


class TestEmailDomainsValidation:
    def test_missing_field_defaults_to_empty(self):
        c = _validate_entry(0, _entry())
        assert c.email_domains == ()

    def test_empty_list_is_valid(self):
        c = _validate_entry(0, _entry(email_domains=[]))
        assert c.email_domains == ()

    def test_single_domain_loaded(self):
        c = _validate_entry(0, _entry(email_domains=["acme.com"]))
        assert c.email_domains == ("acme.com",)

    def test_multiple_domains_preserved_in_order(self):
        c = _validate_entry(0, _entry(email_domains=["acme.com", "acme.co.uk"]))
        assert c.email_domains == ("acme.com", "acme.co.uk")

    def test_uppercase_domain_rejected(self):
        with pytest.raises(ValueError, match="lowercase"):
            _validate_entry(0, _entry(email_domains=["Acme.com"]))

    def test_leading_at_rejected(self):
        with pytest.raises(ValueError, match="leading '@'"):
            _validate_entry(0, _entry(email_domains=["@acme.com"]))

    def test_empty_string_domain_rejected(self):
        with pytest.raises(ValueError, match="non-empty strings"):
            _validate_entry(0, _entry(email_domains=[""]))

    def test_whitespace_only_domain_rejected(self):
        with pytest.raises(ValueError, match="non-empty strings"):
            _validate_entry(0, _entry(email_domains=["   "]))

    def test_non_list_rejected(self):
        with pytest.raises(ValueError, match="must be a list"):
            _validate_entry(0, _entry(email_domains="acme.com"))

    def test_non_string_entry_rejected(self):
        with pytest.raises(ValueError, match="non-empty strings"):
            _validate_entry(0, _entry(email_domains=[123]))


class TestDuplicateDomainAcrossClients:
    def test_clients_loader_catches_cross_slug_duplicate(self, tmp_path, monkeypatch):
        """Same domain under two different client_slugs must raise."""
        from mil.config import clients_loader as loader

        bad = tmp_path / "clients.yaml"
        bad.write_text(
            """
schema_version: 1
clients:
  - client_slug: alpha
    display_name: Alpha
    market_tier: incumbent
    status: monitored
    email_domains:
      - shared.com
  - client_slug: beta
    display_name: Beta
    market_tier: incumbent
    status: monitored
    email_domains:
      - shared.com
""".lstrip(),
            encoding="utf-8",
        )
        loader.clients.cache_clear()
        monkeypatch.setattr(loader, "_CONFIG_PATH", bad)
        with pytest.raises(ValueError, match="claimed by both"):
            loader.clients()
        loader.clients.cache_clear()

    def test_same_slug_same_domain_repeated_is_fine(self, tmp_path, monkeypatch):
        """Two entries listing the same domain under the same slug isn't a
        real-world case, but the dedup check should not false-positive on it."""
        from mil.config import clients_loader as loader

        ok = tmp_path / "clients.yaml"
        ok.write_text(
            """
schema_version: 1
clients:
  - client_slug: alpha
    display_name: Alpha
    market_tier: incumbent
    status: monitored
    email_domains:
      - alpha.com
      - alpha.com
""".lstrip(),
            encoding="utf-8",
        )
        loader.clients.cache_clear()
        monkeypatch.setattr(loader, "_CONFIG_PATH", ok)
        cs = loader.clients()
        assert cs[0].email_domains == ("alpha.com", "alpha.com")
        loader.clients.cache_clear()


class TestDomainToSlugAccessor:
    def test_real_yaml_includes_barclays_seed(self):
        # Sanity check against the live YAML — predeploy generator depends
        # on these mappings being correct.
        clients.cache_clear()
        try:
            mapping = domain_to_slug()
        finally:
            clients.cache_clear()
        assert "barclays.com" in mapping
        assert mapping["barclays.com"]["slug"] == "barclays"
        assert mapping["barclays.com"]["display_name"] == "Barclays"
        assert "barclays.co.uk" in mapping
        assert mapping["barclays.co.uk"]["slug"] == "barclays"
