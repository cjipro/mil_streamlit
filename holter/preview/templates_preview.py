"""Decision-pack templates preview — Streamlit, dev-time only.

Bloomberg-terminal aesthetic per direction 2026-05-18. Amber-on-black,
all-monospace, function-key navigation, multi-page (one screen per altitude
or per artifact). Replaces the editorial/news-portal version.

Departs from HOL-1 lock ("news portal aesthetic"). The Workspace surface
audience is investigation pros, for whom Bloomberg-density is closer-fit
than newspaper-article. Decide before rolling this into HOL-3 proper.

Run with: streamlit run holter/preview/templates_preview.py
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path

import streamlit as st
import yaml

PACKS_DIR = Path(__file__).resolve().parents[2] / "pulse" / "decision_packs"

# Function-key screen codes — Bloomberg-style 4-char mnemonics.
SCREENS = [
    ("PACK", "Packs",     "index"),
    ("DETL", "Detail",    "detail"),
    ("BANK", "Bank alt",  "bank"),
    ("JRNY", "Journey",   "journey"),
    ("SGNL", "Signal",    "signal"),
    ("TMPL", "Template",  "template"),
    ("HYPO", "Hypothesis","hypothesis"),
    ("META", "Metadata",  "metadata"),
]
SCREEN_BY_KEY = {code: (label, key) for code, label, key in SCREENS}


# ─────────────────────────────────────────────────────────────────────────────
# CSS — Bloomberg terminal
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* hide streamlit chrome */
#MainMenu, footer, header[data-testid="stHeader"],
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }

[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
    padding: 0 !important;
}
[data-testid="stMain"] { background: #000000 !important; }

html, body, [class*="st-emotion"], .stMarkdown, .stMarkdown p,
.stMarkdown li, .stMarkdown td, .stMarkdown th, .stMarkdown code, p, div, span {
    font-family: 'JetBrains Mono', 'Cascadia Mono', 'Consolas', monospace !important;
    color: #f5a623 !important;
    font-size: 12.5px !important;
    line-height: 1.45 !important;
    letter-spacing: 0 !important;
    background: transparent !important;
}
body, [data-testid="stApp"], [data-testid="stAppViewContainer"] { background: #000000 !important; }

h1, h2, h3, h4, h5, h6 {
    font-family: 'JetBrains Mono', monospace !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin: 0 !important;
}

/* command bar */
.pulse-cmdbar {
    background: #000000;
    border-bottom: 1px solid #f5a623;
    padding: 6px 14px;
    font-size: 12.5px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #f5a623;
}
.pulse-cmdbar-prompt { color: #00ff66; font-weight: 700; }
.pulse-cmdbar-current { color: #ffffff; }
.pulse-cmdbar-meta { color: #888888; font-size: 11.5px; }

/* function-key strip */
.pulse-funcstrip {
    background: #0a0a0a;
    border-bottom: 1px solid #2a2a2a;
    padding: 4px 8px;
    display: flex;
    gap: 0;
    font-size: 11.5px;
}
.pulse-funckey {
    color: #888888;
    padding: 4px 12px;
    border-right: 1px solid #2a2a2a;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.pulse-funckey strong { color: #f5a623; font-weight: 700; margin-right: 6px; }
.pulse-funckey.active { color: #ffffff; background: #1a1400; border-bottom: 1px solid #f5a623; margin-bottom: -1px; }
.pulse-funckey.active strong { color: #ffffff; }

/* status bar */
.pulse-statbar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: #0a0a0a;
    border-top: 1px solid #f5a623;
    padding: 4px 14px;
    font-size: 11px;
    color: #888888;
    display: flex;
    justify-content: space-between;
    z-index: 1000;
}
.pulse-statbar-cell { padding: 0 12px; border-right: 1px solid #2a2a2a; }
.pulse-statbar-cell:last-child { border-right: none; }
.pulse-statbar-cell strong { color: #f5a623; }
.pulse-statbar-cell.ok strong { color: #00ff66; }
.pulse-statbar-cell.warn strong { color: #ff4444; }

/* main content area */
.pulse-main {
    padding: 14px 18px 60px 18px;
    background: #000000;
    min-height: calc(100vh - 100px);
}

/* panel — the Bloomberg pane */
.pulse-panel {
    border: 1px solid #2a2a2a;
    margin-bottom: 12px;
    background: #050505;
}
.pulse-panel-head {
    background: #1a1400;
    border-bottom: 1px solid #f5a623;
    padding: 4px 12px;
    color: #ffffff;
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    display: flex;
    justify-content: space-between;
}
.pulse-panel-head .right { color: #888888; font-weight: 400; letter-spacing: 0; text-transform: none; }
.pulse-panel-body { padding: 10px 14px; }

/* key/value grid inside panels */
.pulse-kv { display: grid; grid-template-columns: 160px 1fr; gap: 4px 18px; font-size: 12.5px; }
.pulse-kv .k { color: #888888; text-transform: uppercase; letter-spacing: 0.04em; font-size: 11px; }
.pulse-kv .v { color: #f5a623; }
.pulse-kv .v.white { color: #ffffff; }
.pulse-kv .v.green { color: #00ff66; }
.pulse-kv .v.red { color: #ff4444; }
.pulse-kv .v.blue { color: #4488ff; }
.pulse-kv .v.mono { font-variant-numeric: tabular-nums; }

/* tables — terminal grid */
.pulse-table { width: 100%; border-collapse: collapse; font-size: 12px; margin: 6px 0; }
.pulse-table th {
    background: #1a1400;
    color: #ffffff;
    text-align: left;
    padding: 4px 10px;
    border-bottom: 1px solid #f5a623;
    text-transform: uppercase;
    font-size: 10.5px;
    letter-spacing: 0.06em;
    font-weight: 600;
}
.pulse-table td {
    padding: 3px 10px;
    border-bottom: 1px solid #1a1a1a;
    color: #f5a623;
    font-variant-numeric: tabular-nums;
}
.pulse-table td.white { color: #ffffff; }
.pulse-table td.gray  { color: #888888; }
.pulse-table td.green { color: #00ff66; }
.pulse-table td.red   { color: #ff4444; }
.pulse-table td.blue  { color: #4488ff; }
.pulse-table tr:hover td { background: #1a1400; }
.pulse-table.selectable tr td { cursor: pointer; }

/* buttons — terminal style */
.stButton > button {
    background: #0a0a0a !important;
    color: #f5a623 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11.5px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    padding: 4px 12px !important;
    height: auto !important;
    min-height: 0 !important;
    box-shadow: none !important;
}
.stButton > button:hover {
    background: #1a1400 !important;
    color: #ffffff !important;
    border-color: #f5a623 !important;
}
.stButton > button:focus { box-shadow: none !important; }

/* selectbox */
[data-baseweb="select"] > div {
    background: #0a0a0a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 0 !important;
    color: #f5a623 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    min-height: 28px !important;
}
[data-baseweb="select"] div { color: #f5a623 !important; }
.stSelectbox label {
    color: #888888 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* code blocks */
pre, code, .stCodeBlock {
    background: #050505 !important;
    border: 1px solid #2a2a2a !important;
    color: #f5a623 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11.5px !important;
    border-radius: 0 !important;
}
pre code { border: none !important; padding: 0 !important; }

/* alerts → terminal warnings */
[data-testid="stAlert"] {
    background: #050505 !important;
    border: 1px solid #ff4444 !important;
    border-radius: 0 !important;
    color: #ff4444 !important;
}
[data-testid="stAlert"] * { color: #ff4444 !important; }

/* hide expanders entirely (we use pages now) */
[data-testid="stExpander"] { display: none !important; }

/* scrollbar */
*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-track { background: #000; }
*::-webkit-scrollbar-thumb { background: #2a2a2a; }
*::-webkit-scrollbar-thumb:hover { background: #f5a623; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def discover_packs() -> list[dict]:
    packs: list[dict] = []
    if not PACKS_DIR.exists():
        return packs
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        meta_path = pack_dir / "metadata.yaml"
        samples_dir = pack_dir / "samples"
        if not meta_path.exists() or not samples_dir.exists():
            continue
        raw_bytes = meta_path.read_bytes()
        metadata = yaml.safe_load(raw_bytes.decode("utf-8"))
        hypothesis_path = pack_dir / "hypothesis.yaml"
        hypothesis = (
            yaml.safe_load(hypothesis_path.read_text(encoding="utf-8"))
            if hypothesis_path.exists()
            else None
        )
        packs.append(
            {
                "pack_dir": pack_dir,
                "metadata": metadata,
                "metadata_raw": raw_bytes.decode("utf-8"),
                "metadata_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "hypothesis": hypothesis,
            }
        )
    return packs


# ─────────────────────────────────────────────────────────────────────────────
# Chrome (command bar, function strip, status bar)
# ─────────────────────────────────────────────────────────────────────────────

def render_cmdbar(current_screen: str, selected_pack: dict | None) -> None:
    pack_name = selected_pack["metadata"]["pack_name"] if selected_pack else "—"
    pack_ver = selected_pack["metadata"]["pack_version"] if selected_pack else ""
    st.markdown(
        f"""
        <div class="pulse-cmdbar">
            <div>
                <span class="pulse-cmdbar-prompt">PULSE&gt;</span>
                &nbsp;[<span class="pulse-cmdbar-current">{current_screen}</span>]
                &nbsp;{pack_name} {('v'+pack_ver) if pack_ver else ''}
            </div>
            <div class="pulse-cmdbar-meta">DEV BUILD · Investigation preview · holter/preview/templates_preview.py</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_funcstrip(current_screen: str) -> None:
    items = ""
    for i, (code, label, _) in enumerate(SCREENS, start=1):
        active = "active" if code == current_screen else ""
        items += (
            f'<span class="pulse-funckey {active}">'
            f'<strong>{i}</strong>{code}'
            f'</span>'
        )
    st.markdown(f'<div class="pulse-funcstrip">{items}</div>', unsafe_allow_html=True)


def render_funcbuttons(current_screen: str) -> None:
    """Streamlit buttons that mirror the function-key strip (the strip is visual only)."""
    cols = st.columns(len(SCREENS))
    for col, (code, label, _) in zip(cols, SCREENS):
        with col:
            if st.button(
                f"{code}",
                key=f"nav_{code}",
                use_container_width=True,
                type="primary" if code == current_screen else "secondary",
            ):
                st.session_state["current_screen"] = code
                st.rerun()


def render_statbar(packs: list[dict], selected_pack: dict | None) -> None:
    now = _dt.datetime.now(_dt.UTC).strftime("%H:%M:%S")
    pack_count = len(packs)
    lineage_short = (
        f"{selected_pack['metadata_sha256'][:8]}…"
        if selected_pack
        else "—"
    )
    st.markdown(
        f"""
        <div class="pulse-statbar">
            <div>
                <span class="pulse-statbar-cell"><strong>{now}</strong> UTC</span>
                <span class="pulse-statbar-cell ok">PACKS <strong>{pack_count} OK</strong></span>
                <span class="pulse-statbar-cell">ENG <strong>v1.0.0</strong></span>
                <span class="pulse-statbar-cell">LINEAGE <strong>sha256:{lineage_short}</strong></span>
            </div>
            <div>
                <span class="pulse-statbar-cell warn">SYNTH <strong>PULSE-93 PENDING</strong></span>
                <span class="pulse-statbar-cell">FAIRNESS <strong>ENFORCED</strong></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Panel helpers
# ─────────────────────────────────────────────────────────────────────────────

def panel_start(title: str, right: str = "") -> None:
    st.markdown(
        f'<div class="pulse-panel"><div class="pulse-panel-head"><span>{title}</span>'
        f'<span class="right">{right}</span></div><div class="pulse-panel-body">',
        unsafe_allow_html=True,
    )


def panel_end() -> None:
    st.markdown("</div></div>", unsafe_allow_html=True)


def kv_grid(rows: list[tuple[str, str, str]]) -> str:
    """Build a key/value HTML grid. rows: (key, value, class)."""
    parts = ['<div class="pulse-kv">']
    for k, v, cls in rows:
        parts.append(f'<div class="k">{k}</div><div class="v {cls}">{v}</div>')
    parts.append("</div>")
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

def page_index(packs: list[dict]) -> None:
    st.markdown('<div class="pulse-main">', unsafe_allow_html=True)
    panel_start("PACK INDEX", right=f"{len(packs)} packs registered")
    rows = []
    for p in packs:
        m = p["metadata"]
        h = p["hypothesis"] or {}
        cell = h.get("cell_id", "—")
        screen = h.get("screen_id", "—")
        sig = h.get("signature_id", "—")
        gt = h.get("ground_truth_expectation", "—")
        gt_cls = "green" if gt == "positive" else ("red" if gt == "negative" else "gray")
        rows.append(
            f"<tr>"
            f"<td class='white'>{cell}</td>"
            f"<td>{m['pack_name']}</td>"
            f"<td class='gray'>v{m['pack_version']}</td>"
            f"<td>{screen}</td>"
            f"<td class='blue'>{sig}</td>"
            f"<td class='{gt_cls}'>{gt.upper()}</td>"
            f"</tr>"
        )
    st.markdown(
        f"""
        <table class="pulse-table">
            <thead><tr>
                <th>CELL</th><th>PACK</th><th>VER</th>
                <th>SCREEN</th><th>SIGNATURE</th><th>GT</th>
            </tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    panel_end()

    panel_start("SELECT PACK")
    pack_names = [p["metadata"]["pack_name"] for p in packs]
    chosen = st.selectbox(
        "Pack",
        pack_names,
        index=pack_names.index(st.session_state.get("pack_name", pack_names[0]))
            if st.session_state.get("pack_name") in pack_names else 0,
        label_visibility="collapsed",
    )
    if chosen != st.session_state.get("pack_name"):
        st.session_state["pack_name"] = chosen
        st.rerun()
    st.markdown(
        '<div style="color:#888;font-size:11.5px;margin-top:8px;">'
        'Select a pack, then press <strong style="color:#f5a623">2 DETL</strong> '
        'or jump directly to <strong style="color:#f5a623">3 BANK</strong> / '
        '<strong style="color:#f5a623">4 JRNY</strong> / '
        '<strong style="color:#f5a623">5 SGNL</strong>.'
        '</div>',
        unsafe_allow_html=True,
    )
    panel_end()
    st.markdown("</div>", unsafe_allow_html=True)


def page_detail(pack: dict) -> None:
    m = pack["metadata"]
    h = pack["hypothesis"] or {}
    primary_att = (m.get("compliance_attestations") or [{}])[0]
    short_hash = f"{pack['metadata_sha256'][:16]}…{pack['metadata_sha256'][-8:]}"
    gt = h.get("ground_truth_expectation", "—")
    gt_cls = "green" if gt == "positive" else ("red" if gt == "negative" else "white")

    st.markdown('<div class="pulse-main">', unsafe_allow_html=True)

    panel_start("PACK · IDENTIFICATION")
    st.markdown(
        kv_grid([
            ("PACK_NAME",   m.get("pack_name", "—"), "white"),
            ("VERSION",     m.get("pack_version", "—"), ""),
            ("CELL ID",     str(h.get("cell_id", "—")), "white"),
            ("SCREEN",      h.get("screen_id", "—"), ""),
            ("SIGNATURE",   h.get("signature_id", "—"), "blue"),
            ("GROUND TRUTH",gt.upper(), gt_cls),
            ("QUESTION CL", h.get("question_class", "—"), ""),
        ]),
        unsafe_allow_html=True,
    )
    panel_end()

    panel_start("ENGINE · CONTRACT")
    st.markdown(
        kv_grid([
            ("SYNTHESIS",       m.get("synthesis_mode", "—"), ""),
            ("ENGINE REQUIRES", m.get("required_pulse_version", "—"), ""),
            ("FAIRNESS REQD",   "TRUE" if m.get("fairness_methods_required") else "FALSE",
                "green" if m.get("fairness_methods_required") else "red"),
            ("LICENSE",         m.get("license", "—"), ""),
            ("AUTHORS",         ", ".join(m.get("authors", [])), ""),
        ]),
        unsafe_allow_html=True,
    )
    panel_end()

    panel_start("COMPLIANCE · ATTESTATION")
    st.markdown(
        kv_grid([
            ("FRAMEWORK",   primary_att.get("name", "—"), "white"),
            ("STATUS",      primary_att.get("status", "—").upper(),
                "red" if primary_att.get("status") == "self_declared" else "green"),
            ("LAST REVIEWED", str(primary_att.get("last_reviewed", "—")), ""),
        ]),
        unsafe_allow_html=True,
    )
    panel_end()

    panel_start("LINEAGE · ANCHOR")
    st.markdown(
        kv_grid([
            ("METADATA SHA256", short_hash, "mono"),
            ("CHAIN STATUS",    "PINNED · awaiting PULSE-93 hydration", "red"),
        ]),
        unsafe_allow_html=True,
    )
    panel_end()

    st.markdown(
        '<div style="color:#888;font-size:11.5px;margin-top:14px;">'
        'Navigate the rendered altitudes via <strong style="color:#f5a623">3 BANK</strong>, '
        '<strong style="color:#f5a623">4 JRNY</strong>, <strong style="color:#f5a623">5 SGNL</strong>. '
        'Inspect the build artifacts via <strong style="color:#f5a623">6 TMPL</strong>, '
        '<strong style="color:#f5a623">7 HYPO</strong>, <strong style="color:#f5a623">8 META</strong>.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)


def page_altitude(pack: dict, altitude: str) -> None:
    """Render a sample altitude in a terminal panel."""
    code = {"bank": "BANK", "journey": "JRNY", "signal": "SGNL"}[altitude]
    label = {
        "bank": "ALT · BANK · executive headline · max compression",
        "journey": "ALT · JOURNEY · default · narrative + evidence",
        "signal": "ALT · SIGNAL · forensic · individual-event detail",
    }[altitude]

    st.markdown('<div class="pulse-main">', unsafe_allow_html=True)

    panel_start(label, right=f"PACK · {pack['metadata']['pack_name']}")
    sample_path = pack["pack_dir"] / "samples" / f"{altitude}.md"
    if sample_path.exists():
        # Render the sample text directly — markdown-in-terminal styling.
        st.markdown(sample_path.read_text(encoding="utf-8"))
    else:
        st.error(f"NO SAMPLE RENDER · {altitude}")
    panel_end()

    st.markdown(
        f'<div style="color:#888;font-size:11.5px;margin-top:10px;">'
        f'PRESS <strong style="color:#f5a623">6 TMPL</strong> for the Jinja source · '
        f'<strong style="color:#f5a623">7 HYPO</strong> for the detector hypothesis · '
        f'<strong style="color:#f5a623">8 META</strong> for raw metadata · '
        f'<strong style="color:#f5a623">1 PACK</strong> to switch packs.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def page_template(pack: dict) -> None:
    st.markdown('<div class="pulse-main">', unsafe_allow_html=True)
    altitudes = ["bank", "journey", "signal"]
    cols = st.columns(len(altitudes))
    chosen = st.session_state.get("tmpl_altitude", "journey")
    for col, alt in zip(cols, altitudes):
        with col:
            if st.button(
                f"{alt.upper()}",
                key=f"tmpl_{alt}",
                use_container_width=True,
                type="primary" if alt == chosen else "secondary",
            ):
                st.session_state["tmpl_altitude"] = alt
                st.rerun()
    panel_start(f"TEMPLATE · {chosen.upper()} · JINJA2 SOURCE",
                right=f"PACK · {pack['metadata']['pack_name']}")
    tpath = pack["pack_dir"] / "templates" / f"{chosen}.md.j2"
    if tpath.exists():
        st.code(tpath.read_text(encoding="utf-8"), language="jinja")
    else:
        st.error("NO TEMPLATE FOUND")
    panel_end()
    st.markdown("</div>", unsafe_allow_html=True)


def page_hypothesis(pack: dict) -> None:
    st.markdown('<div class="pulse-main">', unsafe_allow_html=True)
    panel_start("HYPOTHESIS · DETECTOR DECLARATION",
                right=f"PACK · {pack['metadata']['pack_name']}")
    if pack["hypothesis"]:
        st.code(yaml.safe_dump(pack["hypothesis"], sort_keys=False), language="yaml")
    else:
        st.error("NO hypothesis.yaml IN PACK")
    panel_end()
    st.markdown("</div>", unsafe_allow_html=True)


def page_metadata(pack: dict) -> None:
    st.markdown('<div class="pulse-main">', unsafe_allow_html=True)
    panel_start("METADATA · PACK CONTRACT",
                right=f"PACK · {pack['metadata']['pack_name']}")
    st.code(pack["metadata_raw"], language="yaml")
    panel_end()
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="PULSE · terminal",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    packs = discover_packs()
    if not packs:
        st.error("NO PACKS FOUND")
        st.stop()

    # default state
    st.session_state.setdefault("current_screen", "PACK")
    st.session_state.setdefault("pack_name", packs[0]["metadata"]["pack_name"])

    selected_pack = next(
        (p for p in packs if p["metadata"]["pack_name"] == st.session_state["pack_name"]),
        packs[0],
    )

    current = st.session_state["current_screen"]

    # chrome
    render_cmdbar(current, selected_pack)
    render_funcstrip(current)
    render_funcbuttons(current)

    # body
    if current == "PACK":
        page_index(packs)
    elif current == "DETL":
        page_detail(selected_pack)
    elif current == "BANK":
        page_altitude(selected_pack, "bank")
    elif current == "JRNY":
        page_altitude(selected_pack, "journey")
    elif current == "SGNL":
        page_altitude(selected_pack, "signal")
    elif current == "TMPL":
        page_template(selected_pack)
    elif current == "HYPO":
        page_hypothesis(selected_pack)
    elif current == "META":
        page_metadata(selected_pack)

    # status bar (last so it overlays)
    render_statbar(packs, selected_pack)


if __name__ == "__main__":
    main()
else:
    main()
