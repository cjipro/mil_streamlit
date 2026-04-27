"""test_publish_site_render.py — MIL-148 placeholder substitution at publish.

Pins the contract that publish_site._render() resolves {{ lang }} and
{{ compliance_notices_html }} from tenant.yaml. Runs against the real
shipped HTML so a future refactor that drops the placeholders gets caught.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mil.config import tenant_loader as tl
from mil.publish import publish_site as ps


@pytest.fixture(autouse=True)
def _reset_cache():
    tl._load.cache_clear()
    yield
    tl._load.cache_clear()


def _set_tenant(tmp_path, monkeypatch, body: str) -> None:
    p = tmp_path / "tenant.yaml"
    p.write_text(body, encoding="utf-8")
    monkeypatch.setattr(tl, "_CONFIG_PATH", p)


class TestRenderSubstitution:
    def test_lang_placeholder_resolved_to_default(self, tmp_path, monkeypatch):
        _set_tenant(tmp_path, monkeypatch, "schema_version: 1\n")
        out = ps._render('<html lang="{{ lang }}">')
        assert out == '<html lang="en-GB">'

    def test_lang_placeholder_resolved_to_override(self, tmp_path, monkeypatch):
        _set_tenant(
            tmp_path,
            monkeypatch,
            'schema_version: 1\nlang: "zh-CN"\ncompliance_notices: ["ICP备XXXXXXXX号"]\n',
        )
        out = ps._render('<html lang="{{ lang }}">...{{ compliance_notices_html }}')
        assert '<html lang="zh-CN">' in out
        assert 'ICP备XXXXXXXX号' in out
        assert '<p class="compliance-notice-line">' in out

    def test_compliance_slot_empty_when_no_notices(self, tmp_path, monkeypatch):
        _set_tenant(tmp_path, monkeypatch, "schema_version: 1\ncompliance_notices: []\n")
        slot = '<div class="compliance-notice">{{ compliance_notices_html }}</div>'
        out = ps._render(slot)
        assert out == '<div class="compliance-notice"></div>'

    def test_no_placeholders_returns_input_unchanged(self, tmp_path, monkeypatch):
        _set_tenant(tmp_path, monkeypatch, "schema_version: 1\n")
        plain = "<html>no templates here</html>"
        assert ps._render(plain) is plain  # short-circuit identity

    def test_zero_visual_drift_today(self, tmp_path, monkeypatch):
        # With the live YAML defaults (en-GB, []) the rendered slot must be
        # byte-identical to the pre-MIL-148 hardcoded form.
        _set_tenant(tmp_path, monkeypatch, "schema_version: 1\n")
        before_148 = '<html lang="en-GB"><div class="compliance-notice"></div>'
        after_148 = '<html lang="{{ lang }}"><div class="compliance-notice">{{ compliance_notices_html }}</div>'
        assert ps._render(after_148) == before_148


class TestRealSiteFiles:
    """Each real source HTML must round-trip through _render cleanly with
    today's defaults — no placeholder leaks, lang attribute correct."""

    SITE_DIR = Path(__file__).resolve().parent.parent / "publish" / "site"

    @pytest.mark.parametrize("name", [
        "home.html",
        "privacy.html",
        "insights_index.html",
        "products_reckoner.html",
        "security_index.html",
        "sign_in.html",
        "thank_you.html",
    ])
    def test_no_placeholder_residue_after_render(self, name):
        # Use the live tenant.yaml — no monkeypatch. Today: en-GB + no notices.
        src = (self.SITE_DIR / name).read_text(encoding="utf-8")
        out = ps._render(src)
        assert "{{ lang }}" not in out, f"{name} still has unrendered lang placeholder"
        assert "{{ compliance_notices_html }}" not in out, f"{name} still has unrendered notices placeholder"
        assert '<html lang="en-GB">' in out, f"{name} missing rendered lang attribute"
