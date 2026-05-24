"""HOL-77 — Home + MLOps bounded-shell scroll regression guard.

Only the Workspace ships the .holter-app wrapper that the laptop-first bounded
shell targets. Home + MLOps are `body > header.holter-topnav + main.{home-main|
mlops-page}`; without a compensating scroll region the global body{overflow:
hidden} clipped them (MLOps lost ~1145px below the fold — unscrollable).

The fix lives in holter/server.py `_LAYOUT_CSS`: body becomes the bounded shell
and the page-main the single vertical scroll region, scoped via :has() so the
Workspace is untouched. CSS scroll behaviour itself is verified in-browser; this
test guards against the rules being silently dropped from the served pages.

Run:  python -m pytest holter/tests/test_layout_scroll.py -q
"""

from __future__ import annotations

from holter.server import app


def _served(path: str) -> str:
    return app.test_client().get(path).get_data(as_text=True)


def test_home_and_mlops_get_a_scroll_region():
    # The page-main of each non-.holter-app surface is an overflow-y:auto region.
    css = _served("/")  # _LAYOUT_CSS is identical across surfaces (injected by _page)
    assert "body>main.home-main,body>main.mlops-page{" in css
    assert "overflow-y:auto!important" in css
    # body is made the bounded flex shell, scoped to the wrapperless surfaces.
    assert "body:has(>main.home-main),body:has(>main.mlops-page){" in css
    assert "html:has(body>main.home-main),html:has(body>main.mlops-page){height:100vh!important}" in css


def test_mlops_page_serves_the_bounded_shell_rules():
    css = _served("/mlops")
    assert "main.mlops-page" in css
    assert "body:has(>main.home-main),body:has(>main.mlops-page){" in css


def test_workspace_shell_untouched():
    # The Workspace keeps its own .holter-app / main.holter-main bounded shell;
    # the HOL-77 :has() rules must not target it (its topnav/main are nested,
    # not direct body children), so no body>main.holter-main scroll override.
    css = _served("/workspace")
    assert "main.holter-main{" in css and "overflow-y:auto!important" in css
    assert "body>main.holter-main" not in css
