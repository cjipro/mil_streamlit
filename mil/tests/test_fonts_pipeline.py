"""test_fonts_pipeline.py — MIL-136 self-hosted fonts contract.

Tests run offline — they don't hit fonts.googleapis.com. Network fetch is
exercised manually by running fetch_fonts.py; this file pins the artefacts
the fetch produced and the contract publish_site.py / the site HTML rely on.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

REPO = Path(__file__).resolve().parent.parent.parent
SITE = REPO / "mil" / "publish" / "site"
FONTS = SITE / "fonts"


class TestFontsArtefacts:
    """The fetch_fonts.py output must exist + be self-consistent before
    publish_site.py is allowed to push. Catches an empty deploy class."""

    def test_fonts_directory_exists(self):
        assert FONTS.exists()
        assert FONTS.is_dir()

    def test_fonts_css_present_and_nonempty(self):
        assert (FONTS / "fonts.css").exists()
        assert (FONTS / "fonts.css").stat().st_size > 0

    def test_ofl_license_present(self):
        # OFL bundling is a load-bearing licence requirement for redist.
        assert (FONTS / "OFL.txt").exists()

    def test_woff2_files_present_for_both_families(self):
        files = sorted(p.name for p in FONTS.glob("*.woff2"))
        # We fetch latin + latin-ext for each weight. Inter ships in 400/500/700,
        # Source Serif 4 in 400/700.
        inter = [f for f in files if f.startswith("inter-")]
        serif = [f for f in files if f.startswith("source-serif-4-")]
        assert len(inter) >= 6, f"expected >=6 Inter weights/subsets, got {inter}"
        assert len(serif) >= 4, f"expected >=4 Source Serif 4 weights/subsets, got {serif}"

    def test_briefings_woff2_files_present(self):
        # MIL-157 — Plus Jakarta Sans (400/500/600/700/800) + DM Mono (400/500).
        # Each weight × 2 subsets = 10 + 4 = 14 files.
        files = sorted(p.name for p in FONTS.glob("*.woff2"))
        pjs = [f for f in files if f.startswith("plus-jakarta-sans-")]
        dm = [f for f in files if f.startswith("dm-mono-")]
        assert len(pjs) >= 10, f"expected >=10 Plus Jakarta Sans files, got {pjs}"
        assert len(dm) >= 4, f"expected >=4 DM Mono files, got {dm}"

    def test_briefings_fonts_css_present_and_local(self):
        # MIL-157 — separate CSS file from fonts.css so cjipro.com pages
        # don't pay the briefings-only bandwidth cost.
        path = FONTS / "briefings_fonts.css"
        assert path.exists()
        css = path.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in css
        assert "fonts.gstatic.com" not in css
        assert "Plus Jakarta Sans" in css
        assert "DM Mono" in css
        assert "font-display: swap" in css

    def test_fonts_css_references_only_local_paths(self):
        # No fonts.googleapis.com or fonts.gstatic.com URLs allowed in the
        # rendered CSS — the whole point of the migration is to keep every
        # byte under our domain.
        css = (FONTS / "fonts.css").read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in css
        assert "fonts.gstatic.com" not in css
        # All src URLs point at /fonts/<name>.woff2
        for m in re.finditer(r'src:\s*url\("([^"]+)"\)', css):
            assert m.group(1).startswith("/fonts/"), f"non-local font URL: {m.group(1)}"

    def test_fonts_css_uses_font_display_swap(self):
        # font-display:swap is what protects LCP — system font during the
        # ~150ms before woff2 lands, then a swap. Without it, FOIT blocks
        # paint until the font loads, blowing the <1.8s LCP target.
        css = (FONTS / "fonts.css").read_text(encoding="utf-8")
        assert "font-display: swap" in css


class TestSiteHTMLContract:
    """Every public site HTML must reference fonts.css + carry the new
    --serif / --sans CSS variable cascade. The migration was atomic at
    source level; if a page is missing the link, the build is broken."""

    @pytest.mark.parametrize("name", sorted(p.name for p in SITE.glob("*.html")))
    def test_page_links_fonts_css(self, name):
        html = (SITE / name).read_text(encoding="utf-8")
        assert "/fonts/fonts.css" in html, f"{name} missing fonts.css link"

    @pytest.mark.parametrize("name", sorted(p.name for p in SITE.glob("*.html")))
    def test_no_google_fonts_cdn_referenced(self, name):
        # Defence-in-depth: even if a page is later edited by hand, lint
        # for the corp-proxy risk pattern.
        html = (SITE / name).read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in html, f"{name} still hits Google Fonts CDN"
        assert "fonts.gstatic.com" not in html, f"{name} still hits gstatic CDN"

    def test_critical_pages_use_source_serif_in_css_vars(self):
        # The three highest-visibility partner-facing pages MUST flip.
        for name in ("home.html", "sign_in.html", "privacy.html"):
            html = (SITE / name).read_text(encoding="utf-8")
            assert '"Source Serif 4"' in html, f"{name} missing Source Serif 4 in stack"
            assert "Inter, -apple-system" in html, f"{name} missing Inter primary"

    def test_preload_critical_weights(self):
        # Without preload, the font request is discovered late (after CSS
        # parses) and FOUC is visible. Both critical weights preload on
        # every page so above-the-fold rendering doesn't whiplash.
        html = (SITE / "home.html").read_text(encoding="utf-8")
        assert 'rel="preload"' in html
        assert "source-serif-4-700-latin.woff2" in html
        assert "inter-400-latin.woff2" in html


class TestPublishSiteIncludesFonts:
    """publish_site.py must enumerate the fonts directory at publish time
    so the artefacts actually deploy."""

    def test_font_files_helper_returns_woff2_and_css(self):
        from mil.publish import publish_site as ps
        files = ps._font_files()
        names = [src for src, _ in files]
        assert any(n.endswith("fonts.css") for n in names)
        assert any(n.endswith(".woff2") for n in names)
        assert any(n.endswith("OFL.txt") for n in names)

    def test_load_returns_bytes_for_woff2(self):
        from mil.publish import publish_site as ps
        # Pick any font file the directory has
        any_font = next(FONTS.glob("*.woff2"))
        result = ps._load(f"fonts/{any_font.name}")
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 1000  # woff2 is never tiny

    def test_load_returns_str_for_css(self):
        from mil.publish import publish_site as ps
        result = ps._load("fonts/fonts.css")
        assert isinstance(result, str)
        assert "@font-face" in result


class TestBriefingsFontMigration:
    """MIL-157 — V1 publish.py drops Google Fonts CDN, points at our self-
    hosted briefings_fonts.css. V2/V3/V4 inherit from V1's HTML (per
    feedback_v1_publisher_load_bearing.md), so the V1 link change is
    sufficient — we test against the source file."""

    PUBLISH = REPO / "mil" / "publish" / "publish.py"
    PUBLISH_V2 = REPO / "mil" / "publish" / "publish_v2.py"
    PUBLISH_V3 = REPO / "mil" / "publish" / "publish_v3.py"
    PUBLISH_V4 = REPO / "mil" / "publish" / "publish_v4.py"
    BRIEFING_TEMPLATE = REPO / "mil" / "publish" / "templates" / "briefing_v4.html.j2"

    def test_v1_no_google_fonts_cdn(self):
        # Direct CSS-link reference to fonts.googleapis.com is the corp-
        # proxy risk we're closing. Catch any future re-introduction.
        src = self.PUBLISH.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in src
        assert "fonts.gstatic.com" not in src
        # preconnect to fonts.googleapis.com is also gone — the lookup
        # was paying for connection setup we no longer need.
        assert 'preconnect" href="https://fonts.googleapis.com"' not in src

    def test_v1_links_briefings_fonts_css(self):
        src = self.PUBLISH.read_text(encoding="utf-8")
        assert "/fonts/briefings_fonts.css" in src

    def test_v1_preloads_critical_briefing_weights(self):
        src = self.PUBLISH.read_text(encoding="utf-8")
        # Plus Jakarta 400 = body weight, DM Mono 400 = number weight.
        # Both above-the-fold on every briefing render.
        assert "plus-jakarta-sans-400-latin.woff2" in src
        assert "dm-mono-400-latin.woff2" in src

    def test_v2_v3_v4_have_no_google_fonts_link(self):
        # V2/V3/V4 inherit V1's HTML; if any of them sneaks back in a
        # direct CDN link they'd reintroduce the corp-proxy risk.
        for path in (self.PUBLISH_V2, self.PUBLISH_V3, self.PUBLISH_V4, self.BRIEFING_TEMPLATE):
            src = path.read_text(encoding="utf-8")
            assert "fonts.googleapis.com" not in src, f"{path.name} still references fonts.googleapis.com"
            assert "fonts.gstatic.com" not in src, f"{path.name} still references fonts.gstatic.com"
