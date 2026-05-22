"""Decision-pack Product Canvas — Streamlit, dev-time only.

Renders a Pulse decision pack in the **real_bank Data Product Canvas** layout
(Decision Intelligence Demand & Delivery Playbook, p.51) — but styled to
match the MIL Sonar V4 briefing aesthetic (dark navy + amber + DM Mono +
Plus Jakarta Sans).

Canvas slots are mapped onto pack metadata + hypothesis where present; gaps
are honestly marked "not yet declared in pack" rather than fabricated.

Color coding mirrors the canvas template legend:
  Green  · Business Vision   (Problem, Values, Risks)
  Blue   · Product Vision    (Data, Solution, Hypothesis)
  Amber  · Vision of Strategy (KPIs, Actions, Actors, Performance/Impact)

Run with: streamlit run holter/preview/canvas.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st
import yaml

PACKS_DIR = Path(__file__).resolve().parents[2] / "pulse" / "decision_packs"


# ─────────────────────────────────────────────────────────────────────────────
# Pack loading
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
        meta = yaml.safe_load(raw_bytes.decode("utf-8"))
        hyp_path = pack_dir / "hypothesis.yaml"
        hyp = (
            yaml.safe_load(hyp_path.read_text(encoding="utf-8"))
            if hyp_path.exists() else None
        )
        bank_md = (samples_dir / "bank.md").read_text(encoding="utf-8") \
            if (samples_dir / "bank.md").exists() else ""
        packs.append({
            "dir": pack_dir,
            "meta": meta,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "hypothesis": hyp,
            "bank_md": bank_md,
        })
    return packs


# ─────────────────────────────────────────────────────────────────────────────
# Slot extraction — pack → canvas
# ─────────────────────────────────────────────────────────────────────────────

NOT_DECLARED = "_Not yet declared in pack. Reserved canvas slot — see "\
               "hypothesis.yaml schema evolution._"


def canvas_data(pack: dict) -> dict:
    m = pack["meta"]
    h = pack["hypothesis"] or {}
    bank = pack["bank_md"]
    primary_att = (m.get("compliance_attestations") or [{}])[0]
    domain = (h.get("screen_id") or "").split(".")[0] or "—"

    # Data fields (evidence_required → bullets)
    evidence = h.get("evidence_required") or []
    data_bullets = "\n".join(f"- `{e}`" for e in evidence) or NOT_DECLARED

    # Solution
    altitudes = []
    for alt in ("bank", "journey", "signal"):
        if (pack["dir"] / "samples" / f"{alt}.md").exists():
            altitudes.append(alt)
    solution_text = (
        f"Decision pack with **{len(altitudes)} rendered altitudes** "
        f"({' / '.join(altitudes)}). "
        f"Synthesis mode: `{m.get('synthesis_mode', '—')}`. "
        f"Lineage anchor pinned (sha256 of metadata.yaml). "
        f"Templates render via Jinja2; PULSE-93 will hydrate at runtime."
    )

    # KPIs
    conf = h.get("confidence") or {}
    fairness = (h.get("fairness") or {}).get("required_methods", [])
    kpi_bullets = []
    if conf.get("reporting"):
        kpi_bullets.append(f"Confidence reporting: `{conf['reporting']}`")
    if conf.get("band_method"):
        kpi_bullets.append(f"Band method: `{conf['band_method']}`")
    kpi_bullets.append(f"Fairness gates: **{len(fairness)} methods**")
    kpi_bullets.append("FrictionBench score (6 axes, equal-weighted)")
    kpis_text = "\n".join(f"- {k}" for k in kpi_bullets)

    # Actions / remediation
    remediation = h.get("remediation_categories") or []
    actions_bullets = "\n".join(f"- `{r}`" for r in remediation) or NOT_DECLARED

    # Hypothesis
    analytic = h.get("analytic") or {}
    trigger = analytic.get("trigger") or {}
    gt = h.get("ground_truth_expectation", "—")
    hyp_lines = []
    if analytic.get("method"):
        hyp_lines.append(f"**Method:** `{analytic['method']}`")
    if trigger:
        trig_parts = []
        for k, v in trigger.items():
            trig_parts.append(f"`{k}={v}`")
        hyp_lines.append(f"**Trigger:** {', '.join(trig_parts)}")
    hyp_lines.append(f"**Ground truth:** `{gt.upper()}`")
    if h.get("question_class"):
        hyp_lines.append(f"**Question class:** `{h['question_class']}`")
    if h.get("negative_class_discriminator"):
        hyp_lines.append(
            "**Discriminator:** present — pack ships a "
            "`negative_class_discriminator` block (must NOT fire by default)."
        )
    hypothesis_text = "\n\n".join(hyp_lines)

    # Actors — synthesized + flagged as reserved
    actors_text = (
        f"_Reserved canvas slot — pack does not yet declare actors._\n\n"
        f"Inferred from pack shape:\n"
        f"- Investigation consumer (reads bank/journey altitudes)\n"
        f"- ML engineer (calibrates analytic + threshold)\n"
        f"- MRM reviewer (audits lineage chain, fairness methods)\n"
        f"- Compliance reviewer ({primary_att.get('name', '—')})"
    )

    # Values — extract opportunity cost / cohort impact from bank.md if present
    values_lines = [
        f"**Cell scope:** FrictionBench cell `{h.get('cell_id', '?')}`",
    ]
    # Crude scan for opportunity-cost hint in bank.md
    if "Estimated opportunity cost" in bank or "opportunity cost" in bank.lower():
        for ln in bank.split("\n"):
            if "opportunity cost" in ln.lower() or "£" in ln:
                values_lines.append(f"_From bank altitude:_ {ln.strip()[:200]}")
                break
    else:
        values_lines.append(
            "_Quantified business value not yet declared in pack. "
            "Reserved for hypothesis.yaml `values_size_and_uplift` field._"
        )
    if gt == "negative":
        values_lines.append(
            "**Load-bearing negative**: pack value = 0 false positives on "
            "the 754 non-target screens (FrictionBench success criterion)."
        )
    values_text = "\n\n".join(values_lines)

    # Risks — derived from fairness + audit + discriminator
    risk_bullets = []
    if fairness:
        risk_bullets.append(
            f"**Fairness disparity risk:** {len(fairness)} methods enforced; "
            "triggers independent review when disparity exceeds configured floor."
        )
    if h.get("negative_class_discriminator"):
        risk_bullets.append(
            "**False-positive risk:** load-bearing negative — detector must "
            "NOT fire. Discriminator suppression failure = regulator-visible "
            "FrictionBench score hit."
        )
    audit = h.get("audit") or {}
    if audit.get("bundle_required_fields"):
        risk_bullets.append(
            f"**Audit-bundle gap risk:** "
            f"{len(audit['bundle_required_fields'])} required fields must be "
            f"pinned at every detection; missing field = unreproducible output."
        )
    if primary_att.get("status") == "self_declared":
        risk_bullets.append(
            "**Attestation risk:** status is `self_declared` — starting "
            "evidence only. Independent assessment / certification required "
            "before regulator-facing use."
        )
    risks_text = "\n".join(f"- {r}" for r in risk_bullets) or NOT_DECLARED

    # Performance / Impact
    perf_bullets = [
        f"**FrictionBench cell:** `{h.get('cell_id', '?')}` "
        f"(`{h.get('screen_id', '—')}` × `{h.get('signature_id', '—')}`)",
        f"**Ground truth expectation:** `{gt.upper()}`",
    ]
    if conf.get("reporting") == "brier_calibrated":
        perf_bullets.append("**Calibration metric:** Brier score (reported per detection)")
    perf_bullets.append(
        "**Reproducibility:** byte-identical output on same inputs "
        "(deterministic synthesis)."
    )
    perf_text = "\n".join(f"- {p}" for p in perf_bullets)

    return {
        "product_name": m.get("pack_name", "—"),
        "owner": ", ".join(m.get("authors", []) or ["—"]),
        "domain": domain,
        "date": str(primary_att.get("last_reviewed", "—")),
        "lineage_short": f"{pack['sha256'][:12]}…{pack['sha256'][-4:]}",
        "version": m.get("pack_version", "—"),
        "synthesis_mode": m.get("synthesis_mode", "—"),

        "problem": m.get("description", NOT_DECLARED).strip(),
        "data": data_bullets,
        "solution": solution_text,
        "kpis": kpis_text,
        "actions": actions_bullets,
        "hypothesis": hypothesis_text,
        "actors": actors_text,
        "values": values_text,
        "risks": risks_text,
        "performance": perf_text,
        "budget": "_Not declared in pack. Reserved slot._",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CSS — MIL Sonar palette, Canvas-shaped layout
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap');

:root {
  --bg: #00273D; --topbar-bg: #001E30; --panel-bg: #001828; --card: #002A3F;
  --border: #003A5C; --blue: #00AEEF; --teal: #00AFA0; --amber: #F5A623;
  --red: #CC0000; --green: #2a9a5a;
  --text: #E8F4FA; --text-2: #7AACBF; --text-3: #4A7A8F; --muted: #3A6A7F;
  --mono: 'DM Mono', monospace;
  --sans: 'Plus Jakarta Sans', sans-serif;
  /* Canvas legend colours */
  --vision-business: #2a9a5a;
  --vision-product:  #00AEEF;
  --vision-strategy: #F5A623;
}

/* hide streamlit chrome */
#MainMenu, footer, header[data-testid="stHeader"],
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stMainBlockContainer"] { max-width: 100% !important; padding: 0 !important; }
[data-testid="stMain"], [data-testid="stApp"], [data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
}

html, body, [class*="st-emotion"] {
  font-family: var(--sans) !important;
  color: var(--text) !important;
}

/* canvas chrome ─────────────────────────────────────── */
.canvas-wrap { padding: 16px 20px 60px; background: var(--bg); min-height: 100vh; }

.canvas-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; margin-bottom: 14px;
  background: var(--topbar-bg); border: 1px solid var(--border); border-radius: 12px;
}
.canvas-brand { font-family: var(--sans); font-weight: 800; font-size: 16px;
                color: var(--blue); letter-spacing: 1.5px; }
.canvas-brand-sub { color: var(--text-3); font-family: var(--mono); font-size: 11px;
                    margin-left: 8px; letter-spacing: 0.5px; }
.canvas-meta { font-family: var(--mono); font-size: 11px; color: var(--text-3); }

.canvas-header {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  padding: 10px 14px;
  background: var(--panel-bg); border: 1px solid var(--border);
  border-radius: 12px 12px 0 0;
  margin-bottom: 0;
}
.canvas-hdr-cell { display: flex; flex-direction: column; gap: 2px; }
.canvas-hdr-label { font-family: var(--mono); font-size: 9px; color: var(--text-3);
                    text-transform: uppercase; letter-spacing: 1.2px; }
.canvas-hdr-value { font-family: var(--sans); font-size: 13px; font-weight: 600;
                    color: var(--text); word-break: break-word; }
.canvas-hdr-value.mono { font-family: var(--mono); font-size: 11px; }
.canvas-hdr-value.amber { color: var(--amber); }

/* the canvas grid — mirrors real_bank template
   Row 1: Problem (rowspan 2) | Data | Solution | KPIs | Actions
   Row 2: (Problem cont.)     | Hypothesis (col-span 2) | Actors (col-span 2)
   Row 3: Values | Risks (col-span 2 width) | Performance/Impact     */
.canvas-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  grid-template-rows: minmax(180px, auto) minmax(180px, auto) minmax(160px, auto);
  gap: 10px;
  padding: 10px 14px 14px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-top: none;
  border-radius: 0 0 12px 12px;
}
.cell {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex; flex-direction: column;
  min-width: 0; overflow: hidden;
}
.cell-head {
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px; margin-bottom: 8px;
}
.cell-title {
  font-family: var(--sans); font-weight: 700; font-size: 13px;
  letter-spacing: 0.8px; text-transform: uppercase;
}
.cell-vision {
  font-family: var(--mono); font-size: 9px;
  padding: 1px 6px; border-radius: 10px;
  text-transform: uppercase; letter-spacing: 0.8px;
}

/* vision flavours */
.cell.vision-business { border-left: 4px solid var(--vision-business); }
.cell.vision-business .cell-title { color: var(--vision-business); }
.cell.vision-business .cell-vision { background: rgba(42,154,90,0.12); color: var(--vision-business); border: 1px solid var(--vision-business); }

.cell.vision-product { border-left: 4px solid var(--vision-product); }
.cell.vision-product .cell-title { color: var(--vision-product); }
.cell.vision-product .cell-vision { background: rgba(0,174,239,0.12); color: var(--vision-product); border: 1px solid var(--vision-product); }

.cell.vision-strategy { border-left: 4px solid var(--vision-strategy); }
.cell.vision-strategy .cell-title { color: var(--vision-strategy); }
.cell.vision-strategy .cell-vision { background: rgba(245,166,35,0.12); color: var(--vision-strategy); border: 1px solid var(--vision-strategy); }

.cell-body {
  font-family: var(--sans); font-size: 12px; line-height: 1.55;
  color: var(--text-2);
  flex: 1; overflow: hidden;
  word-break: break-word; overflow-wrap: anywhere;
}
.cell-body p { margin: 0 0 6px 0; }
.cell-body strong { color: var(--text); font-weight: 600; }
.cell-body code, .cell-body kbd {
  font-family: var(--mono); font-size: 11px;
  background: var(--panel-bg); padding: 1px 5px; border-radius: 3px;
  color: var(--amber); border: 1px solid var(--border);
}
.cell-body ul { padding-left: 16px; margin: 4px 0; }
.cell-body li { margin: 3px 0; color: var(--text-2); }
.cell-body em { color: var(--text-3); font-style: italic; }

/* placement — grid-area assignments */
.cell.problem    { grid-column: 1; grid-row: 1 / span 2; }
.cell.data       { grid-column: 2; grid-row: 1; }
.cell.solution   { grid-column: 3; grid-row: 1; }
.cell.kpis       { grid-column: 4; grid-row: 1; }
.cell.actions    { grid-column: 5; grid-row: 1; }
.cell.hypothesis { grid-column: 2 / span 2; grid-row: 2; }
.cell.actors     { grid-column: 4 / span 2; grid-row: 2; }
.cell.values     { grid-column: 1 / span 2; grid-row: 3; }
.cell.risks      { grid-column: 3 / span 2; grid-row: 3; }
.cell.performance{ grid-column: 5; grid-row: 3; }

/* footer legend + budget */
.canvas-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; margin-top: 14px;
  background: var(--topbar-bg); border: 1px solid var(--border);
  border-radius: 12px;
  font-family: var(--mono); font-size: 11px;
}
.canvas-legend { display: flex; gap: 16px; align-items: center; }
.legend-item { display: flex; align-items: center; gap: 6px; color: var(--text-3); }
.legend-dot { width: 10px; height: 10px; border-radius: 2px; }
.legend-dot.business { background: var(--vision-business); }
.legend-dot.product  { background: var(--vision-product); }
.legend-dot.strategy { background: var(--vision-strategy); }
.canvas-budget {
  border: 1px solid var(--border); padding: 4px 12px; border-radius: 4px;
  color: var(--text-3);
}

/* pack picker (sticky top strip) */
.canvas-controls {
  display: flex; align-items: center; gap: 14px;
  padding: 8px 16px; margin-bottom: 14px;
  background: var(--topbar-bg); border: 1px solid var(--border); border-radius: 12px;
}
[data-baseweb="select"] > div {
  background: var(--panel-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  font-family: var(--mono) !important;
  font-size: 12px !important;
  color: var(--text) !important;
  min-height: 32px !important;
}
[data-baseweb="select"] div { color: var(--text) !important; }
.stSelectbox label {
  color: var(--text-3) !important;
  font-family: var(--mono) !important;
  font-size: 10px !important;
  text-transform: uppercase !important;
  letter-spacing: 1px !important;
}

/* responsive ─ collapse to single column on narrow */
@media (max-width: 1100px) {
  .canvas-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
  }
  .canvas-grid .cell { grid-column: 1 !important; grid-row: auto !important; }
  .canvas-header { grid-template-columns: 1fr; }
}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Cell rendering
# ─────────────────────────────────────────────────────────────────────────────

def md_to_html(md: str) -> str:
    """Minimal markdown → HTML for cell bodies. No external dep."""
    import re
    lines = md.strip().split("\n")
    html_lines = []
    in_ul = False
    for ln in lines:
        s = ln.rstrip()
        if not s:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append("")
            continue
        if s.startswith("- "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{_inline(s[2:])}</li>")
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<p>{_inline(s)}</p>")
    if in_ul:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def _inline(s: str) -> str:
    """Inline markdown: **bold**, *italic*, `code`, _italic_."""
    import re
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\b_([^_]+)_\b", r"<em>\1</em>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def render_cell(slot_class: str, title: str, vision: str, body_md: str) -> str:
    vision_label = {
        "business": "Business",
        "product":  "Product",
        "strategy": "Strategy",
    }[vision]
    return f"""
<div class="cell {slot_class} vision-{vision}">
  <div class="cell-head">
    <span class="cell-title">{title}</span>
    <span class="cell-vision">{vision_label}</span>
  </div>
  <div class="cell-body">{md_to_html(body_md)}</div>
</div>
"""


def render_canvas(pack: dict) -> str:
    d = canvas_data(pack)

    # vision categories per real_bank legend
    cells = (
        render_cell("problem",     "Problem",            "business", d["problem"])
        + render_cell("data",        "Data",               "product",  d["data"])
        + render_cell("solution",    "Solution",           "product",  d["solution"])
        + render_cell("kpis",        "KPIs",               "strategy", d["kpis"])
        + render_cell("actions",     "Actions",            "strategy", d["actions"])
        + render_cell("hypothesis",  "Hypothesis",         "product",  d["hypothesis"])
        + render_cell("actors",      "Actors",             "strategy", d["actors"])
        + render_cell("values",      "Values",             "business", d["values"])
        + render_cell("risks",       "Risks",              "business", d["risks"])
        + render_cell("performance", "Performance / Impact","strategy", d["performance"])
    )

    return f"""
<div class="canvas-topbar">
  <div>
    <span class="canvas-brand">PULSE</span>
    <span class="canvas-brand-sub">Decision-pack Product Canvas · MIL-styled · v0 dev preview</span>
  </div>
  <div class="canvas-meta">
    Following real_bank Decision Intelligence Demand &amp; Delivery Playbook · p.51
  </div>
</div>

<div class="canvas-header">
  <div class="canvas-hdr-cell">
    <span class="canvas-hdr-label">Product Name</span>
    <span class="canvas-hdr-value mono">{d['product_name']}</span>
  </div>
  <div class="canvas-hdr-cell">
    <span class="canvas-hdr-label">Owner</span>
    <span class="canvas-hdr-value">{d['owner']}</span>
  </div>
  <div class="canvas-hdr-cell">
    <span class="canvas-hdr-label">Domain</span>
    <span class="canvas-hdr-value amber">{d['domain']}</span>
  </div>
  <div class="canvas-hdr-cell">
    <span class="canvas-hdr-label">Date</span>
    <span class="canvas-hdr-value mono">{d['date']}</span>
  </div>
  <div class="canvas-hdr-cell">
    <span class="canvas-hdr-label">Lineage anchor</span>
    <span class="canvas-hdr-value mono">sha256:{d['lineage_short']}</span>
  </div>
</div>

<div class="canvas-grid">
  {cells}
</div>

<div class="canvas-footer">
  <div class="canvas-legend">
    <span class="legend-item"><span class="legend-dot business"></span>Business Vision</span>
    <span class="legend-item"><span class="legend-dot product"></span>Product Vision</span>
    <span class="legend-item"><span class="legend-dot strategy"></span>Vision of Strategy</span>
  </div>
  <div class="canvas-budget">Budget Allocated: not declared</div>
</div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit app
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Pulse — Product Canvas",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    packs = discover_packs()
    if not packs:
        st.error("NO PACKS FOUND under pulse/decision_packs/")
        st.stop()

    st.markdown('<div class="canvas-wrap">', unsafe_allow_html=True)

    # Pack picker
    pack_names = [p["meta"]["pack_name"] for p in packs]
    st.markdown('<div class="canvas-controls">', unsafe_allow_html=True)
    chosen = st.selectbox(
        "Select decision pack",
        pack_names,
        index=0,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    pack = next(p for p in packs if p["meta"]["pack_name"] == chosen)
    st.markdown(render_canvas(pack), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
else:
    main()
