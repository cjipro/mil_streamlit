"""Holter production front-end — Streamlit shell (HOL-65 + HOL-66 + HOL-67).

Runs the design-locked surfaces on the production stack. Per the HOL-65
decision, bespoke locked layouts are injected via ``components.html`` (sandboxed
iframe → CSS isolation), so they render verbatim. Interactivity therefore lives
in Streamlit-native controls *outside* the iframe, which re-query live data
(PULSE-127) and re-render the boxes.

  - Home (HOL-66): live friction volume in the verdict-driven cards.
  - Workspace (HOL-67): journey selector drives Box 1/3; RUN ANALYSIS pulls
    the live friction aggregate for the selection.

Run:  py -m streamlit run holter/app/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from holter.preview import render_holter, render_home, render_mlops  # noqa: E402
from holter.preview._shared import discover_packs  # noqa: E402
from pulse.serving import read as friction_read  # noqa: E402

st.set_page_config(
    page_title="CJI Pulse — Holter",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

_HOME, _WORKSPACE, _MLOPS = "Pulse Home", "Investigation Workspace", "MLOps Console"


@st.cache_data(show_spinner=False)
def _home_html() -> str:
    return render_home.render_page()


@st.cache_data(show_spinner=False)
def _mlops_html() -> str:
    return render_mlops.render_page()


def _workspace_options() -> dict[str, tuple[str, str, str]]:
    """label -> (pack_name, screen_id, signature_id) for the journey selector."""
    options: dict[str, tuple[str, str, str]] = {}
    for p in discover_packs():
        h = p.get("hypothesis") or {}
        screen = h.get("screen_id", "")
        sig = h.get("signature_id", "")
        if not screen:
            continue
        label = f"{screen} · {sig.replace('_', ' ')}"
        options[label] = (p["meta"]["pack_name"], screen, sig)
    return dict(sorted(options.items()))


def _render_workspace() -> None:
    options = _workspace_options()
    if not options:
        components.html(render_holter.render_page(), height=1500, scrolling=True)
        return

    ctrl, action = st.columns([4, 1])
    with ctrl:
        choice = st.selectbox("Journey · signature (drives VERDICT + EVIDENCE)", list(options))
    with action:
        st.write("")  # vertical align with the selectbox
        run = st.button("RUN ANALYSIS", use_container_width=True, type="primary")

    pack_name, screen_id, signature = options[choice]
    if run:
        st.session_state["ws_ran"] = choice

    # Live analysis panel (PULSE-127) — shown after RUN for the current pick.
    if st.session_state.get("ws_ran") == choice:
        match = [
            r for r in friction_read.friction_by_journey()
            if r["screen_id"] == screen_id and r["signature"] == signature
        ]
        if match:
            r = match[0]
            st.caption(f"LIVE detection · {screen_id} · {signature.replace('_', ' ')} (PULSE-127)")
            a, b, c, d = st.columns(4)
            a.metric("Sessions", f"{r['sessions']:,}")
            b.metric("Friction sessions", f"{r['friction_sessions']:,}")
            c.metric("Fire-rate", f"{r['fire_rate']:.0%}")
            mc = r.get("mean_confidence")
            d.metric("Mean confidence", f"{mc:.2f}" if mc is not None else "—")
        else:
            st.info("No live detections for this selection in the current mart.")

    components.html(
        render_holter.render_page(selected_pack_name=pack_name),
        height=1500, scrolling=True,
    )


def _record_decision(action: str, scope: str) -> None:
    import datetime as _dt
    st.session_state.setdefault("mlops_log", []).append({
        "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%H:%M:%S"),
        "scope": scope,
        "action": action,
    })


def _render_mlops() -> None:
    """HOL-68 — MRM decision actions wired to live state. Streamlit-native
    controls outside the locked iframe; decisions append to an in-session log
    (the prod-stack equivalent of the locked design's window.holterEventLog).
    The 'business held' metric is live from PULSE-127."""
    try:
        rows = friction_read.friction_by_journey()
    except Exception:
        rows = []
    total_friction = sum(r["friction_sessions"] for r in rows)
    n_journeys = len({r["journey"] for r in rows})

    st.caption(
        "MRM decision · model cards_credit_apply_eligibility__multi_back_press "
        "· ACUTE (drift -13pp on cell 8)"
    )
    m1, m2 = st.columns(2)
    m1.metric("Journeys gated by this workflow", n_journeys)
    m2.metric("Friction sessions held (live · PULSE-127)", f"{total_friction:,}")

    st.write("**Model-scope decision**")
    a, b, c = st.columns(3)
    if a.button("APPROVE FOR PROD · 14D", use_container_width=True, type="primary"):
        _record_decision("APPROVE FOR PROD · 14D", "model")
    if b.button("ROUTE TO COMMITTEE", use_container_width=True):
        _record_decision("ROUTE TO COMMITTEE", "model")
    if c.button("REQUEST RETRAINING", use_container_width=True):
        _record_decision("REQUEST RETRAINING", "model")

    if rows:
        labels = {f"{r['journey']} · {r['signature'].replace('_', ' ')}": r for r in rows}
        st.write("**Pack-scope attestation**")
        pack_choice = st.selectbox("Pending pack", list(labels), key="mlops_pack")
        d, e, f = st.columns(3)
        if d.button("ATTEST", use_container_width=True):
            _record_decision(f"ATTEST · {pack_choice}", "pack")
        if e.button("CHALLENGE", use_container_width=True):
            _record_decision(f"CHALLENGE · {pack_choice}", "pack")
        if f.button("DEFER", use_container_width=True):
            _record_decision(f"DEFER · {pack_choice}", "pack")

    log = st.session_state.get("mlops_log", [])
    st.caption(f"SESSION LOG · {len(log)} decision(s) recorded this session")
    for entry in reversed(log[-6:]):
        st.write(f"- `{entry['ts']}` · [{entry['scope']}] {entry['action']}")

    components.html(_mlops_html(), height=2600, scrolling=True)


def main() -> None:
    st.sidebar.markdown("## CJI&nbsp;PULSE")
    st.sidebar.caption("Holter front-end · HOL-65/66/67")
    choice = st.sidebar.radio(
        "Surface", [_HOME, _WORKSPACE, _MLOPS], label_visibility="collapsed"
    )
    st.sidebar.divider()
    st.sidebar.caption(
        "Locked design via `components.html`; live data + interactivity "
        "via Streamlit controls (PULSE-127)."
    )

    if choice == _HOME:
        components.html(_home_html(), height=2400, scrolling=True)
    elif choice == _WORKSPACE:
        _render_workspace()
    else:
        _render_mlops()


main()
