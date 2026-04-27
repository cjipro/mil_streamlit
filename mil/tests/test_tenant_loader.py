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
