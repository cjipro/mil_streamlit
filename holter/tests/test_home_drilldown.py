"""HOL-76 — Home → Workspace drill-through.

Home cards deep-link, in-app, to the *focused* Workspace view: hero + flagged +
commercial cards open /workspace?pack=<name> (Bank-altitude headline → the same
investigation at Journey altitude); MLOps-alert cards open the /mlops Console;
synthetic awaiting-review stubs keep the generic /workspace (no fabricated pack).

No card uses the retired Streamlit dev port (localhost:8504) or target="_blank"
— the front-end is a single bounded surface, navigation stays in-page (HOL-73).

Run:  python -m pytest holter/tests/test_home_drilldown.py -q
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

from holter.preview import render_holter as W
from holter.preview import render_home as H
from holter.preview._shared import discover_packs
from holter.server import app


def _home_html() -> str:
    return H.render_page()


# ── no retired dev-stage artefacts leak into the served surface ───────────────

def test_home_has_no_stale_dev_links():
    html = _home_html()
    assert "localhost:8504" not in html
    assert 'target="_blank"' not in html


def test_server_no_longer_carries_stale_link_workaround():
    # The fragile blanket string-replace that masked the context-loss is gone.
    assert not hasattr(W, "_STALE_LINK")
    import holter.server as S
    assert not hasattr(S, "_STALE_LINK")


# ── cards emit correct in-app deep links at the source ────────────────────────

def test_hero_and_feed_cards_deep_link_to_their_pack():
    html = _home_html()
    # hero + 3 flagged + ≥1 commercial → comfortably ≥3 pack deep links.
    assert html.count("/workspace?pack=") >= 3
    packs = {p["meta"]["pack_name"] for p in discover_packs()}
    linked = {unquote(m) for m in re.findall(r'/workspace\?pack=([^"\s]+)', html)}
    assert linked, "no pack deep links emitted"
    # Every deep link names a real, discoverable pack — never a dangling target.
    assert linked <= packs, f"deep links to unknown packs: {linked - packs}"


def test_mlops_alert_cards_open_the_console():
    assert 'href="/mlops"' in _home_html()


def test_workspace_href_helper():
    assert H._workspace_href(None) == "/workspace"
    # URL-encoded so spaces / slashes can never break the attribute or route.
    assert H._workspace_href("a b/c") == "/workspace?pack=a%20b%2Fc"
    assert H._workspace_href("loans_apply_step3__dwell_after_error") == (
        "/workspace?pack=loans_apply_step3__dwell_after_error"
    )


# ── the deep link actually focuses the Workspace on that pack ─────────────────

def test_distinct_packs_render_distinct_workspace_views():
    names = [p["meta"]["pack_name"] for p in discover_packs()]
    assert len(names) >= 2
    a, b = names[0], names[1]
    assert W.render_page(selected_pack_name=a) != W.render_page(selected_pack_name=b)


def test_served_workspace_route_honours_pack_param():
    names = [p["meta"]["pack_name"] for p in discover_packs()]
    assert len(names) >= 2
    a, b = names[0], names[1]
    c = app.test_client()
    ra = c.get("/workspace?pack=" + quote(a, safe=""))
    rb = c.get("/workspace?pack=" + quote(b, safe=""))
    assert ra.status_code == 200 and rb.status_code == 200
    # The ?pack= param flows through the route into the render → distinct focus.
    assert ra.get_data(as_text=True) != rb.get_data(as_text=True)
