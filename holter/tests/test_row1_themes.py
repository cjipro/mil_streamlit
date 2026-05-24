"""HOL-85 — Row-1 Themes context selector.

Covers the config-driven themes registry + the picker chrome that server.py
injects between the Cerno brand and the view-tabs (locked order: Cerno · Themes ▾
· tabs). The selector is the shell — content behind a theme lands with PULSE-136
— so these tests assert the registry, the picker markup, placeholder gating, the
?theme= round-trip, and that the chosen theme rides through the surface nav.

Run:  python -m pytest holter/tests/test_row1_themes.py -q
"""

from __future__ import annotations

import holter.server as S
from holter.server import app

# Brand anchor + the markup (not CSS) selectors used for ordering assertions.
_BRAND_MARK = '<span class="brand-logo">'
_PICKER_MARK = '<details class="cji-theme-picker">'
_DIVIDER_MARK = '<span class="cji-nav-divider">'
_NAV_MARK = '<nav class="cji-surface-nav">'


# ── Registry (holter/themes.yaml) ───────────────────────────────────────────────

def test_registry_has_13_themes_2_placeholders():
    themes = S._load_themes()
    assert len(themes) == 13
    placeholders = [t for t in themes if t["status"] == "placeholder"]
    actives = [t for t in themes if t["status"] == "active"]
    assert len(placeholders) == 2
    assert len(actives) == 11
    assert {t["slug"] for t in placeholders} == {"app-and-disputes", "app-and-fraud"}


def test_every_theme_has_slug_label_tooltip():
    for t in S._load_themes():
        assert t["slug"] and t["label"] and t["tooltip"]
        assert t["status"] in ("active", "placeholder")


# ── Default + resolution ────────────────────────────────────────────────────────

def test_default_is_the_app():
    assert S._default_theme_slug() == "the-app"


def test_resolve_none_and_unknown_fall_back_to_default():
    assert S._resolve_theme(None) == "the-app"
    assert S._resolve_theme("") == "the-app"
    assert S._resolve_theme("not-a-real-theme") == "the-app"


def test_resolve_active_theme_keeps_it():
    assert S._resolve_theme("app-and-call-centre") == "app-and-call-centre"


def test_resolve_placeholder_falls_back_to_default():
    # A placeholder (disabled / "coming soon") can never become the active context.
    assert S._resolve_theme("app-and-disputes") == "the-app"
    assert S._resolve_theme("app-and-fraud") == "the-app"


def test_theme_label_lookup():
    assert S._theme_label("app-and-nps") == "App and NPS"
    assert S._theme_label("app-and-cx") == "App and Customer Experience (CX)"


# ── Picker markup ─────────────────────────────────────────────────────────────--

def test_picker_renders_every_theme_label():
    html = S._themes_html("/", "the-app")
    for t in S._load_themes():
        assert t["label"] in html


def test_picker_current_label_is_selected_theme():
    html = S._themes_html("/", "app-and-call-centre")
    assert '<span class="cji-theme-current">App and Call Centre</span>' in html


def test_picker_active_theme_is_a_link_marked_active():
    html = S._themes_html("/", "the-app")
    assert 'class="cji-theme-item is-active"' in html
    # a non-selected active theme is a normal link to ?theme=<slug>
    assert 'href="/?theme=app-and-call-centre"' in html


def test_picker_placeholders_are_disabled_not_links():
    html = S._themes_html("/", "the-app")
    assert "is-placeholder" in html
    assert '<span class="cji-theme-soon">soon</span>' in html
    # placeholders must NOT be navigable
    assert 'href="/?theme=app-and-disputes"' not in html
    assert 'href="/?theme=app-and-fraud"' not in html
    assert 'aria-disabled="true"' in html


def test_picker_links_target_current_surface():
    html = S._themes_html("/workspace", "the-app")
    assert 'href="/workspace?theme=app-and-call-centre"' in html


# ── Surface nav carries the theme ────────────────────────────────────────────--

def test_nav_carries_theme_through_every_tab():
    nav = S._nav_html("/", "app-and-nps")
    assert 'href="/?theme=app-and-nps"' in nav
    assert 'href="/workspace?theme=app-and-nps"' in nav
    assert 'href="/mlops?theme=app-and-nps"' in nav


def test_nav_marks_active_surface():
    nav = S._nav_html("/workspace", "the-app")
    assert 'href="/workspace?theme=the-app" aria-current="page"' in nav


# ── _page injection order: Cerno · Themes · divider · tabs ───────────────────--

def test_page_injects_row1_in_locked_order():
    html = "<head></head><body>" + S._BRAND + "</body>"
    out = S._page(html, "/", "the-app")
    i_brand = out.find(_BRAND_MARK)
    i_pick = out.find(_PICKER_MARK)
    i_div = out.find(_DIVIDER_MARK)
    i_nav = out.find(_NAV_MARK)
    assert -1 not in (i_brand, i_pick, i_div, i_nav)
    assert i_brand < i_pick < i_div < i_nav


def test_page_injects_picker_css_once():
    html = "<head></head><body>" + S._BRAND + "</body>"
    out = S._page(html, "/", "the-app")
    assert "cji-theme-picker-css" in out
    assert out.count(_PICKER_MARK) == 1


# ── Live app integration ─────────────────────────────────────────────────────--

def test_home_renders_picker_with_default_theme():
    body = app.test_client().get("/").get_data(as_text=True)
    assert _PICKER_MARK in body
    assert '<span class="cji-theme-current">The App</span>' in body


def test_theme_param_selects_active_theme():
    body = app.test_client().get("/?theme=app-and-call-centre").get_data(as_text=True)
    assert '<span class="cji-theme-current">App and Call Centre</span>' in body
    assert 'class="cji-theme-item is-active"' in body


def test_placeholder_param_falls_back_to_default_in_bar():
    body = app.test_client().get("/?theme=app-and-disputes").get_data(as_text=True)
    assert '<span class="cji-theme-current">The App</span>' in body


def test_theme_rides_through_to_other_surfaces_in_nav():
    body = app.test_client().get("/?theme=app-and-nps").get_data(as_text=True)
    assert 'href="/workspace?theme=app-and-nps"' in body
    assert 'href="/mlops?theme=app-and-nps"' in body


def test_workspace_and_mlops_also_carry_picker():
    for path in ("/workspace", "/mlops"):
        body = app.test_client().get(path).get_data(as_text=True)
        assert _PICKER_MARK in body


def test_healthz_reports_theme_count():
    data = app.test_client().get("/healthz").get_json()
    assert data["themes"] == 13
