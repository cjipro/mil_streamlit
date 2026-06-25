"""Exploration surface — explore the friction AND verify it, in one Holter shell.

Folds the former standalone Friction (`/cerno`) and Verification (`/mlops`)
surfaces into a single **Exploration** surface (3-tab IA: Decisions /
Intelligence / Exploration). A within-surface segmented control switches between:
  • EXPLORE — the D-014 friction feed + marts + drill (render_cerno)
  • VERIFY  — drift / fairness / lineage / synthesis (render_mlops pane builders)
so the MRM verifier isn't gated behind the friction scroll, and the explorer
isn't distracted by governance panes (R1 panel #1, the dual-job tension).

No iframe — both halves are composed server-side into one document; the
explore half is its own box grid so the holter layout survives the wrapping.
"""
from __future__ import annotations

from holter.preview import render_cerno, render_mlops
from holter.preview._shared import CSS, discover_packs
from holter.preview.render_cerno import _CERNO_CSS, render_topnav

_EXPLORE_CSS = """<style id="explore-css">
/* segmented control (R1 #1 — explore vs verify as views, not one scroll) */
.explore-switch{display:flex;gap:.4rem;margin:.1rem 0 1.1rem}
.explore-tab{background:#001828;border:1px solid var(--border);color:var(--text-2);
  font:700 11px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;
  padding:.58rem 1.15rem;border-radius:6px;cursor:pointer}
.explore-tab:hover{border-color:var(--blue);color:var(--text)}
.explore-tab.is-active{background:rgba(0,183,245,.16);border-color:var(--blue);color:#fff}
/* the switch + both views are full-width items in the holter-main grid */
main.holter-main>.explore-switch,
main.holter-main>#explore-view,
main.holter-main>#verify-view{grid-column:1 / -1!important}
/* explore-view IS the box grid (the wrapped holter-rows dissolve into it).
   :not([hidden]) so the grid display doesn't override the hidden attribute when
   the Verify view is active. */
#explore-view:not([hidden]){display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));
  gap:14px;align-items:start}
#explore-view>.holter-row{display:contents}
/* verify-view: panes flow normally (they were built as their own page main) */
#verify-view>.mlops-page{height:auto!important;max-height:none!important;
  overflow:visible!important;display:block!important;padding:0!important}
.verify-intro{margin:0 0 1.1rem;color:var(--text-2);font:400 13px/1.55 var(--sans);max-width:60rem}
.verify-intro b{color:var(--text)}
</style>"""

_SWITCH = (
    '<div class="explore-switch" role="tablist">'
    '<button class="explore-tab is-active" type="button" data-view="explore">Explore friction</button>'
    '<button class="explore-tab" type="button" data-view="verify">Verify</button>'
    "</div>"
)

_VERIFY_INTRO = (
    '<p class="verify-intro"><b>Verify — is the friction real &amp; defensible?</b> '
    "Drift, fairness, lineage and synthesis governance for the findings under "
    "Explore. Model-deployment risk sits with the deploying data-science team — "
    "this surface verifies journey findings, it doesn't deploy models.</p>"
)

_SWITCH_JS = """<script id="explore-switch-js">
(function(){
  var tabs = document.querySelectorAll('.explore-tab');
  var explore = document.getElementById('explore-view');
  var verify = document.getElementById('verify-view');
  tabs.forEach(function(btn){
    btn.addEventListener('click', function(){
      var v = btn.getAttribute('data-view');
      tabs.forEach(function(b){ b.classList.toggle('is-active', b === btn); });
      if (explore) explore.hidden = (v !== 'explore');
      if (verify) verify.hidden = (v !== 'verify');
      window.scrollTo(0, 0);
    });
  });
})();
</script>"""


def render_page() -> str:
    packs = discover_packs()
    explore_view = f'<div id="explore-view">{render_cerno.friction_main()}</div>'
    verify_view = (
        '<div id="verify-view" hidden>'
        + _VERIFY_INTRO
        + '<section class="mlops-page" data-window="14d">'
        + render_mlops.render_decision_frame(packs)
        + render_mlops.render_drift_pane(packs)
        + render_mlops.render_fairness_pane(packs)
        + render_mlops.render_lineage_pane(packs)
        + render_mlops.render_synthesis_pane(packs)
        + "</section></div>"
    )
    main = _SWITCH + explore_view + verify_view
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cerno — Exploration</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
{_CERNO_CSS}
<style>{render_mlops.CSS_EXTRA}</style>
{_EXPLORE_CSS}
</head>
<body>
<div class="holter-app">
  {render_topnav()}
  <main class="holter-main">{main}</main>
</div>
{_SWITCH_JS}
</body>
</html>'''
