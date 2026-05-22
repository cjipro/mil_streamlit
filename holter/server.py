"""Full-page Pulse front-end — Flask (HOL-72, supersedes the HOL-71 FastAPI build).

Serves the locked design surfaces directly over HTTP, full-page (no iframe), on
an approved production stack: Flask (dev server locally) / gunicorn (bank/Linux).
Each surface is a complete self-contained HTML document — its own CSS *and*
client-side JS — rendered server-side with live data baked in at render time.

On top of the static surfaces, filter controls run **live on change**: a vanilla
``fetch`` GETs an HTML *fragment* from a ``/fragment/*`` route (which runs the
DuckDB engine read), and a small injected script swaps it into the page. No SPA,
no node/npm, no new dependency — only Flask + the browser's built-in fetch.

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
from holter import fragments  # noqa: E402

app = Flask(__name__)

# (route, label) for the surface switcher, in display order.
_SURFACES: tuple[tuple[str, str], ...] = (
    ("/", "Home"),
    ("/workspace", "Workspace"),
    ("/mlops", "MLOps"),
)

# Anchor inside the design's existing dark top bar — identical across surfaces.
_BRAND = '<span class="brand-logo">CJI&nbsp;PULSE</span>'

# Design-stage link baked into the Home cards; point it at the live Workspace.
_STALE_LINK = "http://localhost:8504/"

_NAV_CSS = """
<style id="cji-surface-nav-css">
.cji-surface-nav{display:inline-flex;gap:.2rem;margin-left:1.1rem;align-items:center;vertical-align:middle}
.cji-surface-nav a{font:600 11px/1 ui-sans-serif,system-ui,-apple-system,sans-serif;
  letter-spacing:.09em;text-transform:uppercase;color:#7da8c9;text-decoration:none;
  padding:.42rem .72rem;border-radius:6px;border:1px solid transparent;transition:all .12s}
.cji-surface-nav a:hover{color:#e8f4fa;background:rgba(125,168,201,.12)}
.cji-surface-nav a[aria-current="page"]{color:#e8f4fa;background:rgba(125,168,201,.18);
  border-color:rgba(125,168,201,.38)}
.cji-live-frag.cji-loading{opacity:.45;transition:opacity .12s}
.cji-live-frag .cji-frag-err{color:#ff8a8a;font:600 12px/1.4 ui-sans-serif,sans-serif;padding:.6rem 0}
</style>
"""

# Injected vanilla-fetch wiring (no dependency). Binds the Workspace journey/cell
# selector to the live fragment endpoint; swaps the returned HTML into the panel.
# Loaded only on /workspace (where the target + selector exist).
_FETCH_JS = """
<script id="cji-live-fetch">
(function () {
  function bind() {
    var host = document.getElementById('cji-verdict-live');
    var sel = document.getElementById('filter-product');  // design's Product selector; value = pack name
    if (!host || !sel) return;
    function load(pack) {
      host.classList.add('cji-loading');
      fetch('/fragment/verdict?pack=' + encodeURIComponent(pack || ''))
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (html) { host.innerHTML = html; })
        .catch(function () { host.innerHTML = '<div class="cji-frag-err">Live fragment failed to load.</div>'; })
        .finally(function () { host.classList.remove('cji-loading'); });
    }
    sel.addEventListener('change', function (e) { load(e.target.value); });
    load(sel.value || '');  // populate live on first paint
  }
  if (document.readyState !== 'loading') bind();
  else document.addEventListener('DOMContentLoaded', bind);
})();
</script>
"""


def _nav_html(active: str) -> str:
    """Surface-switcher markup. Built without backslashes inside f-string
    expressions (SyntaxError before Python 3.12; bank env is 3.11-locked)."""
    parts = []
    for path, label in _SURFACES:
        current = ' aria-current="page"' if path == active else ""
        parts.append(f'<a href="{path}"{current}>{label}</a>')
    return '<nav class="cji-surface-nav">' + "".join(parts) + "</nav>"


# Live strip injected at the top of the Workspace content; recomputes on the
# Product filter change. Anchored before the first content row (data-row="topbar").
_TOPBAR_ROW = '<div class="holter-row" data-row="topbar">'
_LIVE_HOST = (
    '<div style="padding:.7rem 1.4rem 0">'
    '<div style="font:700 10px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.1em;'
    'text-transform:uppercase;color:#5b7a92;margin:0 0 .5rem">'
    'Live · recomputes on Product filter change</div>'
    '<div id="cji-verdict-live" class="cji-live-frag"></div>'
    '</div>'
)


def _page(html: str, active: str, *, live_fetch: bool = False) -> str:
    """Inject the surface nav + styles, rewire the design-stage cross-surface
    link, and (on the Workspace) inject the live host + fetch wiring."""
    html = html.replace(_BRAND, _BRAND + _nav_html(active), 1)
    html = html.replace("</head>", _NAV_CSS + "</head>", 1)
    html = html.replace(_STALE_LINK, "/workspace")
    if live_fetch:
        html = html.replace(_TOPBAR_ROW, _LIVE_HOST + _TOPBAR_ROW, 1)
        html = html.replace("</body>", _FETCH_JS + "</body>", 1)
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
    pack = request.args.get("pack")
    return _page(render_holter.render_page(selected_pack_name=pack), "/workspace", live_fetch=True)


@app.get("/mlops")
def mlops() -> str:
    return _page(render_mlops.render_page(), "/mlops")


@app.get("/fragment/verdict")
def fragment_verdict() -> str:
    """Live verdict fragment for the selected journey/pack — runs the DuckDB
    engine read on each call and returns just the panel HTML (no full page)."""
    return fragments.verdict_fragment(request.args.get("pack"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8600, debug=False)
