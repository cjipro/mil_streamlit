"""Full-page Pulse front-end (no iframe).

Serves the locked design surfaces directly over HTTP, replacing the Streamlit
``components.html`` harness (HOL-65) that boxed each design inside a sandboxed
iframe with Streamlit-native widgets bolted around it.

Each surface is a complete, self-contained HTML document — its own CSS *and*
client-side JS (filters, RUN ANALYSIS, the MLOps decision log) — rendered
server-side with live data baked in at render time (PULSE-127). Because the
designs carry their own interactivity, they never needed Streamlit's native
controls; serving them full-page restores the design-stage look (the
``serve_*.py`` / dist preview aesthetic) while keeping the surfaces live.

A slim surface-switcher nav is injected into the design's existing top bar, and
the design-stage cross-surface links are rewired to the live routes.

Run:  py -m uvicorn holter.server:app --port 8600
  or: py holter/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from holter.preview import render_holter, render_home, render_mlops  # noqa: E402

app = FastAPI(title="CJI Pulse — Holter front-end", version="1.0.0")

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


def _page(html: str, active: str) -> str:
    """Inject the surface nav + its styles into a rendered design, and rewire
    the design-stage cross-surface link to the live route."""
    html = html.replace(_BRAND, _BRAND + _nav_html(active), 1)
    html = html.replace("</head>", _NAV_CSS + "</head>", 1)
    html = html.replace(_STALE_LINK, "/workspace")
    return html


# Inline ECG-line favicon (Holter = the wearable ECG monitor) — keeps the
# console clean; the pages are otherwise fully self-contained (no external assets).
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#0b1f30"/>'
    '<path d="M3 17h6l2.5-8 4 15 3-10 2 3h6.5" fill="none" stroke="#34d3a6"'
    ' stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(content=_FAVICON, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _page(render_home.render_page(), "/")


@app.get("/workspace", response_class=HTMLResponse)
def workspace(pack: str | None = None) -> str:
    return _page(render_holter.render_page(selected_pack_name=pack), "/workspace")


@app.get("/mlops", response_class=HTMLResponse)
def mlops() -> str:
    return _page(render_mlops.render_page(), "/mlops")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("holter.server:app", host="127.0.0.1", port=8600, reload=False)
