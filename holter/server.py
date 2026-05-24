"""Full-page Pulse front-end — Flask (HOL-72).

Serves the locked design surfaces directly over HTTP, full-page (no iframe), on
an approved production stack: Flask (dev server locally) / gunicorn (bank/Linux).
Each surface is a complete self-contained HTML document — its own CSS *and*
client-side JS — rendered server-side with live data baked in at render time.

Run (local dev):  py holter/server.py        (Flask dev server, :8600)
Run (bank/prod):  gunicorn -w 4 -b 127.0.0.1:8600 holter.server:app
"""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import yaml
from flask import Flask, Response, request

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from holter.preview import render_holter, render_home, render_mlops  # noqa: E402
from holter.preview._shared import discover_packs  # noqa: E402  (HOL-81 healthz)

app = Flask(__name__)

# (route, label) for the surface switcher, in display order.
_SURFACES: tuple[tuple[str, str], ...] = (
    ("/", "Decisions"),
    ("/workspace", "Intelligence"),
    ("/mlops", "Verification"),
)

# Anchor inside the design's existing dark top bar — identical across surfaces.
_BRAND = '<span class="brand-logo">Cerno</span>'

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


# ── Row-1 Themes context picker (HOL-85) ──────────────────────────────────────
# Config-driven decision-output selector that sits between the Cerno brand and
# the view-tabs — locked order Cerno · Themes ▾ · tabs. Themes read from
# holter/themes.yaml (adding one is a config line, no code change). A theme is
# the bar's PRIMARY context (the subject), so its selection persists via ?theme=
# (mirrors the ?pack= precedent) and rides through view-tab switches. Content
# behind a theme lands with the engine theme model (PULSE-136); this is the
# selector shell, shipped ahead of that content. Tab labels (Home/Workspace/
# MLOps) are renamed to Decisions/Intelligence/Verification by HOL-83, not here.
_THEMES_PATH = Path(__file__).resolve().parent / "themes.yaml"


@functools.lru_cache(maxsize=1)
def _load_themes() -> tuple[dict[str, str], ...]:
    """Themes registry from holter/themes.yaml, in display order. Fails soft to a
    single 'The App' default so the bar still renders if the file is missing."""
    fallback = ({"slug": "the-app", "label": "The App",
                 "status": "active", "tooltip": "The mobile banking app."},)
    try:
        data = yaml.safe_load(_THEMES_PATH.read_text(encoding="utf-8")) or {}
        out = tuple(
            {
                "slug": str(t["slug"]),
                "label": str(t["label"]),
                "status": str(t.get("status", "active")),
                "tooltip": str(t.get("tooltip", "")),
            }
            for t in (data.get("themes") or [])
            if t.get("slug") and t.get("label")
        )
        return out or fallback
    except Exception:
        import logging
        logging.exception("themes.yaml unreadable — row-1 picker falls back to 'The App'")
        return fallback


def _default_theme_slug() -> str:
    """First ACTIVE theme is the default context — placeholders are never default."""
    for t in _load_themes():
        if t["status"] == "active":
            return t["slug"]
    return _load_themes()[0]["slug"]


def _resolve_theme(slug: str | None) -> str:
    """Map a requested ?theme= to a real, selectable slug, else the default.
    Unknown slugs AND placeholders both fall back — a placeholder (disabled,
    'coming soon') can never become the active context."""
    if slug:
        for t in _load_themes():
            if t["slug"] == slug and t["status"] == "active":
                return slug
    return _default_theme_slug()


def _theme_label(slug: str) -> str:
    for t in _load_themes():
        if t["slug"] == slug:
            return t["label"]
    return slug


def _themes_html(current_path: str, active_slug: str) -> str:
    """Row-1 context picker — a native <details> chip dropdown (no JS, CSP-safe).
    Active themes are links that set ?theme= on the current surface; placeholders
    render disabled with a 'soon' badge and no href — never empty-but-live."""
    items = []
    for t in _load_themes():
        slug, label = t["slug"], t["label"]
        tip = t["tooltip"].replace('"', "&quot;")
        if t["status"] != "active":
            items.append(
                f'<span class="cji-theme-item is-placeholder" aria-disabled="true" '
                f'title="{tip}">{label}<span class="cji-theme-soon">soon</span></span>'
            )
            continue
        cls = "cji-theme-item is-active" if slug == active_slug else "cji-theme-item"
        cur = ' aria-current="true"' if slug == active_slug else ""
        items.append(
            f'<a class="{cls}" href="{current_path}?theme={slug}"{cur} '
            f'title="{tip}">{label}</a>'
        )
    return (
        '<details class="cji-theme-picker">'
        '<summary class="cji-theme-summary" title="Switch decision output">'
        '<span class="cji-theme-kicker">Theme</span>'
        f'<span class="cji-theme-current">{_theme_label(active_slug)}</span>'
        '<span class="cji-theme-caret">▾</span>'
        '</summary>'
        f'<div class="cji-theme-menu" role="menu">{"".join(items)}</div>'
        '</details>'
    )


_THEMES_CSS = """
<style id="cji-theme-picker-css">
.cji-theme-picker{position:relative;display:inline-block;margin-left:1.1rem;vertical-align:middle}
.cji-theme-picker>summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;gap:.5rem;
  background:#001828;border:1px solid #003A5C;border-radius:6px;padding:.34rem .7rem;
  font:600 11px/1 ui-sans-serif,system-ui,-apple-system,sans-serif;color:#e8f4fa}
.cji-theme-picker>summary::-webkit-details-marker{display:none}
.cji-theme-picker>summary::marker{content:""}
.cji-theme-picker>summary:hover{border-color:#00B7F5}
.cji-theme-picker[open]>summary{border-color:#00B7F5}
.cji-theme-kicker{font:700 8px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.14em;
  text-transform:uppercase;color:#5A8199}
.cji-theme-current{color:#e8f4fa;letter-spacing:.01em}
.cji-theme-caret{color:#5A8199;font-size:9px}
.cji-theme-menu{position:absolute;top:calc(100% + 6px);left:0;z-index:300;
  min-width:248px;max-height:64vh;overflow-y:auto;
  background:#001828;border:1px solid #003A5C;border-radius:8px;padding:.35rem;
  box-shadow:0 12px 32px rgba(0,0,0,.55)}
.cji-theme-item{display:flex;align-items:center;justify-content:space-between;gap:.6rem;
  padding:.46rem .6rem;border-radius:5px;text-decoration:none;
  font:500 12px/1.2 ui-sans-serif,system-ui,-apple-system,sans-serif;color:#cfe4f0}
a.cji-theme-item:hover{background:rgba(125,168,201,.14);color:#fff}
.cji-theme-item.is-active{background:rgba(0,183,245,.16);color:#fff;font-weight:700}
.cji-theme-item.is-placeholder{color:#4d6a7d;cursor:not-allowed}
.cji-theme-soon{font:700 8px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.12em;
  text-transform:uppercase;color:#0b1f30;background:#5A8199;border-radius:3px;padding:2px 5px}
.cji-nav-divider{display:inline-block;width:1px;height:20px;background:#003A5C;
  margin:0 0 0 1rem;vertical-align:middle}
</style>
"""


def _nav_html(active: str, theme: str) -> str:
    """Surface-switcher markup. Carries the active ?theme= so the chosen subject
    survives view switches (theme is primary context, tab is the view). Built
    without backslashes inside f-string expressions (SyntaxError before Python
    3.12; bank env is 3.11-locked)."""
    parts = []
    for path, label in _SURFACES:
        current = ' aria-current="page"' if path == active else ""
        parts.append(f'<a href="{path}?theme={theme}"{current}>{label}</a>')
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


def _page(html: str, active: str, theme: str) -> str:
    """Inject the row-1 chrome (Themes picker + surface nav) + styles into a
    rendered design surface.

    Locked row-1 order: Cerno · Themes ▾ · view-tabs (HOL-85). The picker and a
    zone divider land right after the Cerno brand, before the tabs. Cards emit
    their own in-app deep links at the source (HOL-76), so the legacy stale-link
    string-replace is gone — no surface emits localhost:8504.
    """
    row1 = (
        _BRAND
        + _themes_html(active, theme)
        + '<span class="cji-nav-divider"></span>'
        + _nav_html(active, theme)
    )
    html = html.replace(_BRAND, row1, 1)
    html = html.replace("</head>", _NAV_CSS + _THEMES_CSS + _LAYOUT_CSS + "</head>", 1)
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
    theme = _resolve_theme(request.args.get("theme"))
    return _page(render_home.render_page(), "/", theme)


@app.get("/workspace")
def workspace() -> str:
    pack = request.args.get("pack")  # optional deep-link to a pack selection
    theme = _resolve_theme(request.args.get("theme"))
    return _page(render_holter.render_page(selected_pack_name=pack), "/workspace", theme)


@app.get("/mlops")
def mlops() -> str:
    theme = _resolve_theme(request.args.get("theme"))
    return _page(render_mlops.render_page(), "/mlops", theme)


@app.get("/healthz")
def healthz() -> Response:
    """Liveness + light readiness (HOL-81).

    200 if the process is up AND the engine can discover decision packs — this
    catches a broken deploy where `pulse/decision_packs/` is missing/unreadable,
    not just whether the port is open. 503 otherwise, so a load balancer / probe
    pulls the instance out of rotation. Cheap: metadata reads only, no DuckDB.
    """
    try:
        n = len(discover_packs())
    except Exception as e:  # readiness failure — surface, don't crash the probe
        return Response(
            json.dumps({"status": "degraded", "service": "holter", "error": str(e)}),
            status=503, mimetype="application/json",
        )
    return Response(
        json.dumps({"status": "ok", "service": "holter", "packs": n,
                    "themes": len(_load_themes()),
                    "surfaces": [r for r, _ in _SURFACES]}),
        mimetype="application/json",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8600, debug=False)
