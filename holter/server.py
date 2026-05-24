"""Full-page Pulse front-end — Flask (HOL-72).

Serves the locked design surfaces directly over HTTP, full-page (no iframe), on
an approved production stack: Flask (dev server locally) / gunicorn (bank/Linux).
Each surface is a complete self-contained HTML document — its own CSS *and*
client-side JS — rendered server-side with live data baked in at render time.

Run (local dev):  py holter/server.py        (Flask dev server, :8600)
Run (bank/prod):  gunicorn -w 4 -b 127.0.0.1:8600 holter.server:app
"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, Response, request

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from holter.preview import render_holter, render_home, render_mlops  # noqa: E402

app = Flask(__name__)

# (route, label) for the surface switcher, in display order.
_SURFACES: tuple[tuple[str, str], ...] = (
    ("/", "Home"),
    ("/workspace", "Workspace"),
    ("/mlops", "MLOps"),
)

# Anchor inside the design's existing dark top bar — identical across surfaces.
_BRAND = '<span class="brand-logo">CJI&nbsp;PULSE</span>'

_NAV_CSS = """
<style id="cji-surface-nav-css">
.cji-surface-nav{display:inline-flex;gap:.2rem;margin-left:1.1rem;align-items:center;vertical-align:middle}
.cji-surface-nav a{font:600 11px/1 ui-sans-serif,system-ui,-apple-system,sans-serif;
  letter-spacing:.09em;text-transform:uppercase;color:#7da8c9;text-decoration:none;
  padding:.42rem .72rem;border-radius:6px;border:1px solid transparent;transition:all .12s}
.cji-surface-nav a:hover{color:#e8f4fa;background:rgba(125,168,201,.12)}
.cji-surface-nav a[aria-current="page"]{color:#e8f4fa;background:rgba(125,168,201,.18);
  border-color:rgba(125,168,201,.38)}
</style>
"""


def _nav_html(active: str) -> str:
    """Surface-switcher markup. Built without backslashes inside f-string
    expressions (SyntaxError before Python 3.12; bank env is 3.11-locked)."""
    parts = []
    for path, label in _SURFACES:
        current = ' aria-current="page"' if path == active else ""
        parts.append(f'<a href="{path}"{current}>{label}</a>')
    return '<nav class="cji-surface-nav">' + "".join(parts) + "</nav>"


# HOL-73 — responsive layout. Adapts the locked design for full-page serving
# without editing the locked render_* templates. Governing rule: "fit-or-wrap,
# never overflow" — a box fits on its row or wraps whole to the next; nothing
# clips or scrolls horizontally. Boxes are uniform fixed-size cells: a wider
# screen adds COLUMNS and pulls boxes up from the next row — boxes never widen.
# Full rationale + decision log in HOL-73.
_LAYOUT_CSS = """
<style id="cji-layout">
/* Bounded app shell — the app owns its boundary (viewport height), so layout
   no longer depends on browser window / scrollbar / zoom quirks. Toolbar +
   filter strip are fixed; only the main region scrolls (vertically). Combined
   with the shrink rules below, content wraps to fit the boundary instead of
   clipping or forcing a horizontal scrollbar. */
html,body{height:100%!important;margin:0!important}
body{overflow:hidden!important}
.holter-app{height:100vh!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}
.holter-topnav,.holter-filter-strip{flex:0 0 auto!important;flex-wrap:wrap!important;height:auto!important;position:static!important}
/* main = the single scroll region + responsive grid for the analytical clusters */
main.holter-main{flex:1 1 auto!important;min-height:0!important;overflow-y:auto!important;overflow-x:hidden!important;
  display:grid!important;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))!important;gap:14px!important;align-items:start!important}
/* marquee + journey-KPI strip → full-width header bands at the top (out of the
   way so the box grid below can fill every row) */
main.holter-main>.holter-ticker{grid-column:1 / -1!important;order:-2!important}
main.holter-main>.holter-journey-strip{grid-column:1 / -1!important;order:-1!important}
/* HOL-78 — the altitude band is a full-width element (markdown + tables), not a
   uniform cell; span it across the grid. No order → it sits in source position
   (after the verdict trio), below the top bands. */
main.holter-main>.holter-altitude{grid-column:1 / -1!important}
/* ALL box rows dissolve → one uniform grid of fixed-size cells. A wider screen
   adds COLUMNS and pulls boxes up from the next row — boxes never widen. */
main.holter-main>.holter-row{display:contents!important}
/* shrink rules — fit-or-wrap, never overflow */
main.holter-main .holter-box{min-width:0!important}
main.holter-main img,main.holter-main svg,main.holter-main canvas{max-width:100%!important;height:auto!important}
.holter-ticker,.holter-ticker-track,.holter-ticker-wrap{overflow:hidden!important;max-width:100%!important}

/* HOL-77 — only the Workspace ships the .holter-app wrapper that the bounded
   shell above targets. Home + MLOps are body > header.holter-topnav +
   main.{home-main|mlops-page} (no wrapper), so the global body{overflow:hidden}
   above clipped them with no scroll region — MLOps lost ~1145px below the fold.
   Make BODY their bounded shell: fixed topnav + the page-main as the single
   vertical scroll region. The html height:100vh is load-bearing — body's
   100vh resolves cleanly only when the root height is definite too. Scoped via
   :has(>main.home-main|mlops-page) + body>main.* child selectors, so the
   Workspace (topnav + main live inside .holter-app, not direct body children)
   never matches and is untouched. */
html:has(body>main.home-main),html:has(body>main.mlops-page){height:100vh!important}
body:has(>main.home-main),body:has(>main.mlops-page){
  height:100vh!important;overflow:hidden!important;display:flex!important;flex-direction:column!important}
body:has(>main.home-main)>header.holter-topnav,
body:has(>main.mlops-page)>header.holter-topnav{flex:0 0 auto!important}
body>main.home-main,body>main.mlops-page{
  flex:1 1 auto!important;min-height:0!important;overflow-y:auto!important;overflow-x:hidden!important}
</style>
"""


def _page(html: str, active: str) -> str:
    """Inject the surface nav + styles into a rendered design surface.

    Cards now emit their own in-app deep links at the source (HOL-76), so the
    legacy stale-link string-replace is gone — no surface emits localhost:8504.
    """
    html = html.replace(_BRAND, _BRAND + _nav_html(active), 1)
    html = html.replace("</head>", _NAV_CSS + _LAYOUT_CSS + "</head>", 1)
    return html


# Inline ECG-line favicon (Holter = the wearable ECG monitor) — keeps the
# console clean; the pages are otherwise fully self-contained (no external assets).
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#0b1f30"/>'
    '<path d="M3 17h6l2.5-8 4 15 3-10 2 3h6.5" fill="none" stroke="#34d3a6"'
    ' stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(_FAVICON, mimetype="image/svg+xml")


@app.get("/")
def home() -> str:
    return _page(render_home.render_page(), "/")


@app.get("/workspace")
def workspace() -> str:
    pack = request.args.get("pack")  # optional deep-link to a pack selection
    return _page(render_holter.render_page(selected_pack_name=pack), "/workspace")


@app.get("/mlops")
def mlops() -> str:
    return _page(render_mlops.render_page(), "/mlops")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8600, debug=False)
