"""test_tenant_loader.py — MIL-148 tenant.yaml loader behaviour.

Covers default lang, compliance_notices validation, and the
compliance_notices_html escaping rule (raw HTML in YAML must not
land in the rendered output unescaped).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mil.config import tenant_loader as tl


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tenant.yaml"
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _reset_cache():
    tl._load.cache_clear()
    yield
    tl._load.cache_clear()


class TestLang:
    def test_default_when_field_missing(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 1\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.lang() == "en-GB"

    def test_explicit_value_overrides_default(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 1\nlang: zh-CN\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.lang() == "zh-CN"

    def test_whitespace_in_lang_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, 'schema_version: 1\nlang: "en GB"\n')
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="whitespace"):
            tl.lang()

    def test_empty_lang_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, 'schema_version: 1\nlang: ""\n')
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        # Empty string falls through to the default — non-string values
        # raise; empty string is forgiven and replaced with en-GB.
        assert tl.lang() == "en-GB"

    def test_missing_file_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tl, "_CONFIG_PATH", tmp_path / "nope.yaml")
        assert tl.lang() == "en-GB"


class TestComplianceNotices:
    def test_default_empty(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 1\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.compliance_notices() == ()
        assert tl.compliance_notices_html() == ""

    def test_explicit_empty_list(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 1\ncompliance_notices: []\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.compliance_notices() == ()
        assert tl.compliance_notices_html() == ""

    def test_single_notice_rendered(self, tmp_path, monkeypatch):
        p = _write_yaml(
            tmp_path,
            'schema_version: 1\ncompliance_notices:\n  - "ICP备XXXXXXXX号"\n',
        )
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.compliance_notices() == ("ICP备XXXXXXXX号",)
        html = tl.compliance_notices_html()
        assert html == '<p class="compliance-notice-line">ICP备XXXXXXXX号</p>'

    def test_multiple_notices_rendered_in_order(self, tmp_path, monkeypatch):
        p = _write_yaml(
            tmp_path,
            'schema_version: 1\ncompliance_notices:\n  - "First"\n  - "Second"\n',
        )
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        html = tl.compliance_notices_html()
        assert "First" in html
        assert "Second" in html
        assert html.index("First") < html.index("Second")

    def test_html_in_notice_is_escaped(self, tmp_path, monkeypatch):
        p = _write_yaml(
            tmp_path,
            'schema_version: 1\ncompliance_notices:\n  - "<script>alert(1)</script>"\n',
        )
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        html = tl.compliance_notices_html()
        # XSS payload is neutralised — no executable script tags survive.
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_non_list_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(
            tmp_path,
            'schema_version: 1\ncompliance_notices: "not a list"\n',
        )
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="must be a list"):
            tl.compliance_notices()

    def test_empty_string_entry_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(
            tmp_path,
            'schema_version: 1\ncompliance_notices:\n  - ""\n',
        )
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="non-empty strings"):
            tl.compliance_notices()


class TestLiveYAML:
    """Live cjipro.com tenant must load cleanly today."""

    def test_loads_default_en_gb_with_no_notices(self):
        # No monkeypatch — uses the real mil/config/tenant.yaml shipped today.
        assert tl.lang() == "en-GB"
        assert tl.compliance_notices() == ()
        assert tl.compliance_notices_html() == ""

    def test_organisation_loads(self):
        assert tl.organisation_name() == "CJI"
        assert tl.organisation_display_name() == "CJI Briefing"
        assert "@" in tl.organisation_contact_email()

    def test_domains_load(self):
        assert tl.domain_apex() == "cjipro.com"
        assert tl.domain_app() == "app.cjipro.com"
        assert tl.domain_login() == "login.cjipro.com"
        assert tl.domain_admin() == "admin.cjipro.com"

    def test_url_accessors(self):
        assert tl.apex_url() == "https://cjipro.com"
        assert tl.app_url() == "https://app.cjipro.com"
        assert tl.login_url() == "https://login.cjipro.com"
        assert tl.admin_url() == "https://admin.cjipro.com"

    def test_sonar_briefing_url(self):
        assert tl.sonar_briefing_url("barclays") == "https://app.cjipro.com/sonar/barclays/"
        assert tl.sonar_briefing_url("hsbc") == "https://app.cjipro.com/sonar/hsbc/"

    def test_fonts_base_url(self):
        assert tl.fonts_base_url() == "https://cjipro.com/fonts"

    def test_git_committer(self):
        assert tl.git_committer_email().endswith("@cjipro.com")
        assert tl.git_committer_name()  # non-empty

    def test_harvester_contact(self):
        assert "@" in tl.harvester_contact_email()


# ── MIL-119 — schema v2 sections ────────────────────────────────────────────

class TestOrganisationOverrides:
    def test_explicit_values(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
organisation:
  name: "Acme Insights"
  display_name: "Acme Daily"
  contact_email: "ops@acme.example"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.organisation_name() == "Acme Insights"
        assert tl.organisation_display_name() == "Acme Daily"
        assert tl.organisation_contact_email() == "ops@acme.example"

    def test_missing_section_falls_back_to_default(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 2\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.organisation_name() == "CJI"
        assert tl.organisation_contact_email() == "hello@cjipro.com"

    def test_non_mapping_organisation_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, 'schema_version: 2\norganisation: "not a dict"\n')
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="must be a mapping"):
            tl.organisation_name()


class TestDomainOverrides:
    def test_explicit_values(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
domains:
  apex: "acme.example"
  app: "app.acme.example"
  login: "login.acme.example"
  admin: "admin.acme.example"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.apex_url() == "https://acme.example"
        assert tl.app_url() == "https://app.acme.example"
        assert tl.login_url() == "https://login.acme.example"
        assert tl.admin_url() == "https://admin.acme.example"

    def test_scheme_in_domain_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
domains:
  apex: "https://acme.example"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="bare hostname.*scheme"):
            tl.domain_apex()

    def test_path_in_domain_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
domains:
  app: "app.acme.example/foo"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="bare hostname.*path"):
            tl.domain_app()


class TestSonarUrlTemplate:
    def test_default_template(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 2\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.sonar_briefing_url("barclays") == "https://app.cjipro.com/sonar/barclays/"

    def test_explicit_template(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
sonar_briefing_url_template: "https://acme.example/briefings/{slug}/latest/"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.sonar_briefing_url("hsbc") == "https://acme.example/briefings/hsbc/latest/"

    def test_empty_slug_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 2\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="non-empty slug"):
            tl.sonar_briefing_url("")
        with pytest.raises(ValueError, match="non-empty slug"):
            tl.sonar_briefing_url("   ")

    def test_template_without_slug_placeholder_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
sonar_briefing_url_template: "https://acme.example/briefings/latest/"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match=r"\{slug\}"):
            tl.sonar_briefing_url("barclays")


class TestFontsBaseUrl:
    def test_default(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 2\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.fonts_base_url() == "https://cjipro.com/fonts"

    def test_strips_trailing_slash(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
fonts_base_url: "https://acme.example/fonts/"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.fonts_base_url() == "https://acme.example/fonts"

    def test_relative_url_rejected(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
fonts_base_url: "/fonts"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        with pytest.raises(ValueError, match="absolute URL"):
            tl.fonts_base_url()


class TestGitCommitter:
    def test_default(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, "schema_version: 2\n")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.git_committer_name() == "MIL Sonar Publisher"
        assert tl.git_committer_email() == "sonar-publish@cjipro.com"

    def test_explicit(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 2
git_committer:
  name: "Acme Bot"
  email: "bot@acme.example"
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        assert tl.git_committer_name() == "Acme Bot"
        assert tl.git_committer_email() == "bot@acme.example"


class TestSchemaV1Compatibility:
    """A schema_version:1 tenant.yaml (locale-only, pre-MIL-119) must
    continue to load — every v2 accessor falls back to defaults."""

    def test_v1_yaml_still_loads(self, tmp_path, monkeypatch):
        p = _write_yaml(tmp_path, """
schema_version: 1
lang: en-GB
compliance_notices: []
""")
        monkeypatch.setattr(tl, "_CONFIG_PATH", p)
        # Locale fields work (the v1 contract).
        assert tl.lang() == "en-GB"
        # v2 accessors fall back to defaults.
        assert tl.organisation_name() == "CJI"
        assert tl.domain_apex() == "cjipro.com"
        assert tl.git_committer_email() == "sonar-publish@cjipro.com"
        assert tl.fonts_base_url() == "https://cjipro.com/fonts"
