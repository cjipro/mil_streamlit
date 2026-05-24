"""HOL-78 — Workspace altitude band (Bank/Journey/Signal).

The band surfaces the SELECTED investigation's three real engine renderings
(samples/{bank,journey,signal}.md), client-side toggle, default Journey. These
tests pin: discover_packs carries all three samples; the band defaults to Journey
with the others hidden; the selected pack (?pack= deep-link) drives the content;
real sample content reaches the panes; an honest NO-RENDER fallback when a sample
is missing; and the served Workspace wires the band CSS + JS.

Run:  python -m pytest holter/tests/test_altitude_band.py -q
"""

from __future__ import annotations

from holter.preview import render_holter as W
from holter.preview._shared import discover_packs
from holter.server import app

_RUNNABLE = "loans_apply_step3__dwell_after_error"


def test_discover_packs_carries_all_three_altitudes():
    p = discover_packs()[0]
    for k in ("bank_md", "journey_md", "signal_md"):
        assert k in p and p[k].strip(), f"{k} missing/empty"


def test_band_defaults_to_journey_with_others_hidden():
    html = W.render_altitude_band(discover_packs(), _RUNNABLE)
    assert 'class="holter-altitude"' in html
    assert html.count('class="alt-pane"') == 3
    # Journey visible (no hidden attr), Bank + Signal hidden.
    assert '<div class="alt-pane" data-alt="journey">' in html
    assert '<div class="alt-pane" data-alt="bank" hidden>' in html
    assert '<div class="alt-pane" data-alt="signal" hidden>' in html
    assert 'data-alt="journey"' in html and 'is-active' in html


def test_selected_pack_drives_band_content():
    packs = discover_packs()
    a = W.render_altitude_band(packs, _RUNNABLE)
    b = W.render_altitude_band(packs, "cards_credit_apply_eligibility__abandon_before_submit")
    assert a != b
    assert _RUNNABLE in a
    assert "cards_credit_apply_eligibility__abandon_before_submit" in b


def test_real_sample_content_reaches_panes():
    html = W.render_altitude_band(discover_packs(), _RUNNABLE)
    # Bank headline marker, Journey cohort table, Signal forensic table all present.
    assert "Decision needed" in html                      # bank.md
    assert 'class="alt-md-table"' in html                 # journey/signal tables
    assert "Per-session evidence" in html                 # signal.md
    assert "<strong>" in html                             # bold converted, not raw **


def test_norender_fallback_when_sample_missing():
    packs = discover_packs()
    victim = next(p for p in packs if p["meta"]["pack_name"] == _RUNNABLE)
    saved = victim["signal_md"]
    victim["signal_md"] = ""                               # simulate missing sample
    try:
        html = W.render_altitude_band(packs, _RUNNABLE)
        assert "alt-norender" in html
        assert "signal altitude unavailable" in html
    finally:
        victim["signal_md"] = saved


def test_served_workspace_wires_band_css_and_js():
    html = app.test_client().get("/workspace?pack=" + _RUNNABLE).get_data(as_text=True)
    assert 'class="holter-altitude"' in html
    assert "cji-altitude-css" in html                      # scoped CSS in <head>
    assert "alt-seg-btn" in html                           # segmented control + toggle JS
