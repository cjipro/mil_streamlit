"""HOL-90 — Cerno Friction surface (render + serve).

Pins that the Cerno surface renders through the Holter design system: the
render module emits the _page() injection anchors (brand-logo / </header> /
</head> / </body>) + the .holter-app shell + boxes; the served surface gets the
Row-1/Row-2 chrome + the Friction nav tab; the drill route works and 404s
cleanly; example event_step tokens are HTML-escaped; and CERNO_PRIMARY redirects
`/` → `/cerno`.

Run:  python -m pytest holter/tests/test_cerno_surface.py -q
"""
from __future__ import annotations

import holter.server as server
from holter.preview import render_cerno as rc
from holter.server import app

_PAGE_ANCHORS = ('<span class="brand-logo">Cerno</span>', "</header>", "</head>", "</body>")


def test_render_page_has_page_anchors_and_shell():
    html = rc.render_page()
    for a in _PAGE_ANCHORS:
        assert a in html, f"missing _page anchor: {a}"
    for cls in ("holter-app", "holter-topnav", "holter-main", "holter-box"):
        assert cls in html
    # marts evidence boxes
    for m in ("C_WEAK_LINKS", "C_FRICTION_MATRIX", "C_ERROR_CASCADES"):
        assert m in html


def test_render_candidate_page_sections_and_escaping():
    html = rc.render_candidate_page(1)
    assert html is not None
    for s in ("FRICTION SIGNATURE", "NEIGHBOURHOOD", "EXAMPLE SESSIONS", "ACTION"):
        assert s in html
    # event_step tokens must be escaped, never raw
    assert "&lt;END:abandoned&gt;" in html
    assert "<END:abandoned>" not in html
    assert rc.render_candidate_page(999) is None


def test_served_cerno_has_holter_chrome():
    # The friction surface now lives under /exploration (HOL-94); /cerno redirects.
    client = app.test_client()
    assert client.get("/cerno").status_code == 302
    r = client.get("/exploration")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # _page injects Row-1 (themes) + Row-2 (journey) + surface nav
    assert "cji-theme-picker" in body
    assert "cji-row2" in body
    assert "cji-surface-nav" in body
    assert ">Exploration</a>" in body


def test_drill_route_and_404():
    client = app.test_client()
    assert client.get("/cerno/candidate/1").status_code == 200
    assert client.get("/cerno/candidate/999").status_code == 404


def test_cerno_primary_redirects_root():
    old = server._CERNO_PRIMARY
    server._CERNO_PRIMARY = True
    try:
        r = app.test_client().get("/")
        assert r.status_code == 302
        assert "/exploration" in r.headers["Location"]
    finally:
        server._CERNO_PRIMARY = old


def test_root_default_is_decisions_when_not_primary():
    old = server._CERNO_PRIMARY
    server._CERNO_PRIMARY = False
    try:
        r = app.test_client().get("/")
        assert r.status_code == 200
    finally:
        server._CERNO_PRIMARY = old
