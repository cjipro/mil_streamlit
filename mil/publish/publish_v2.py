#!/usr/bin/env python3
"""
publish_v2.py — MIL Sonar Briefing V2

Extends the existing Sonar briefing (Box 1/2/3) with the components built
in Phase 1: Vane Trajectory Chart, Inference Cards, Clark Protocol status,
and Phase 2 Demand counter.

Published to: cjipro.com/briefing-v2   (briefing-v2/index.html on GitHub Pages)
V1 briefing at cjipro.com/briefing is NOT touched.

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""

import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
MIL_DIR    = SCRIPT_DIR.parent
REPO_ROOT  = MIL_DIR.parent
OUTPUT_DIR = SCRIPT_DIR / "output"

sys.path.insert(0, str(MIL_DIR))
sys.path.insert(0, str(REPO_ROOT))

from mil.publish.adapters import write_text_lf  # LF-only HTML writes

# ── Data layer imports ────────────────────────────────────────────────────────
from briefing_data import get_briefing_data
from mil.command.components.vane_chart import build_vane_data
from mil.command.components.inference_cards import load_findings, findings_summary
from mil.command.components.clark_protocol import (
    active_clark_summary,
)
from mil.command.components.exit_strategy import click_log_summary, load_ceiling_findings

# ── Constants ─────────────────────────────────────────────────────────────────
COMP_COLOURS = {
    "barclays": "#00AEEF", "natwest": "#F5A623", "lloyds": "#00AFA0",
    "monzo": "#7B5EA7", "revolut": "#4A9BD4", "hsbc": "#CC3300",
}
COMP_LABELS = {
    "barclays": "Barclays", "natwest": "NatWest", "lloyds": "Lloyds",
    "monzo": "Monzo", "revolut": "Revolut", "hsbc": "HSBC",
}
TIER_COLOURS  = {"P1": "#CC0000", "P2": "#F5A623", "P3": "#4A7A8F"}
CLARK_COLOURS = {"CLARK-3": "#CC0000", "CLARK-2": "#F5A623", "CLARK-1": "#00AFA0", "CLARK-0": "#3A6A7F"}
CLARK_LABELS  = {"CLARK-3": "ACT NOW", "CLARK-2": "ESCALATE", "CLARK-1": "WATCH", "CLARK-0": "NOMINAL"}
JOURNEY_LABELS = {
    "J_AUTH_01": "Log In", "J_PAY_01": "Make a Payment",
    "J_TRANSFER_01": "Transfer Money", "J_ACCOUNT_01": "View Account",
    "J_CARD_01": "Card Management", "J_SERVICE_01": "General App Use",
    "J_ONBOARD_01": "Onboarding", "J_SAVINGS_01": "Savings",
}


# ─────────────────────────────────────────────────────────────────────────────
# Section builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_vane_section() -> str:
    """Vane Trajectory Chart — embedded Plotly."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return '<div class="v2-section"><p style="color:#3A6A7F;font-size:12px;">plotly not installed — run: pip install plotly</p></div>'

    vane_data = build_vane_data(window_days=14)
    all_dates = sorted(next(iter(vane_data.values())).keys()) if vane_data else []
    if not all_dates:
        return ""

    x_labels = [datetime.strptime(d, "%Y-%m-%d").strftime("%b %d") for d in all_dates]
    fig = go.Figure()

    # Competitors (non-Barclays) — dotted
    for comp in ["natwest", "lloyds", "monzo", "revolut"]:
        series = vane_data.get(comp, {})
        y_vals = [series.get(d) for d in all_dates]
        fig.add_trace(go.Scatter(
            x=x_labels, y=y_vals, name=COMP_LABELS.get(comp, comp),
            mode="lines+markers",
            line=dict(color=COMP_COLOURS[comp], width=1.5, dash="dot"),
            marker=dict(size=4), connectgaps=False, opacity=0.75,
        ))

    # Barclays — thick + fill
    barcl = vane_data.get("barclays", {})
    y_b = [barcl.get(d) for d in all_dates]
    fig.add_trace(go.Scatter(
        x=x_labels, y=y_b, name="Barclays",
        mode="lines+markers",
        line=dict(color="#00AEEF", width=3),
        marker=dict(size=6, color="#00AEEF"),
        fill="tozeroy", fillcolor="rgba(0,174,239,0.05)",
        connectgaps=False,
    ))

    fig.add_hline(y=75, line_dash="dash", line_color="#003A5C", line_width=1,
                  annotation_text="75 floor", annotation_font_color="#4A7A8F",
                  annotation_font_size=10, annotation_position="right")

    fig.update_layout(
        paper_bgcolor="#001828", plot_bgcolor="#00273D",
        font=dict(family="DM Mono, monospace", color="#7AACBF", size=11),
        margin=dict(l=40, r=20, t=10, b=60), height=280,
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=10), nticks=7),
        yaxis=dict(range=[0, 105], showgrid=True, gridcolor="#003A5C", gridwidth=0.5,
                   zeroline=False, tickfont=dict(size=10), dtick=25),
        legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10),
                    bgcolor="rgba(0,0,0,0)", borderwidth=0),
        hovermode="x unified",
    )

    chart_div = pio.to_html(fig, full_html=False, include_plotlyjs=False,
                            config={"displayModeBar": False})

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">VANE TRAJECTORY</span>
    <span style="font-size:10px;color:#3A6A7F;">14-day daily sentiment &middot; App Store + Google Play</span>
  </div>
  <div class="topbar-box-body">
    {chart_div}
  </div>
</div>"""


def _build_inference_section() -> str:
    """Top 10 Barclays inference cards by CAC score."""
    summary = findings_summary()
    findings = load_findings(competitor="barclays", limit=10)
    if not findings:
        return ""

    cards_html = ""
    for f in findings:
        comp     = f.get("competitor", "unknown")
        tier     = f.get("finding_tier", "P3")
        sev      = f.get("signal_severity", "P2")
        cac      = f.get("confidence_score", 0.0)
        ceiling  = f.get("designed_ceiling_reached", False)
        summary_text = (f.get("finding_summary") or "No summary.")[:120]
        keywords = f.get("top_3_keywords", [])
        chr_id   = (f.get("chronicle_match") or {}).get("chronicle_id", "")
        counts   = f.get("signal_counts", {})
        jid      = f.get("journey_id", "")
        journey  = JOURNEY_LABELS.get(jid, jid)
        fid      = f.get("finding_id", "—")

        comp_col  = COMP_COLOURS.get(comp, "#7AACBF")
        tier_col  = TIER_COLOURS.get(tier, "#4A7A8F")
        cac_pct   = min(int(cac * 100), 100)
        cac_col   = "#CC0000" if cac >= 0.65 else ("#F5A623" if cac >= 0.45 else "#4A9BD4")

        kw_html = "".join(
            f'<span class="kw-pill">{k}</span>' for k in keywords
        )
        ceiling_badge = '<span class="badge-ceiling">⚑ CEILING</span>' if ceiling else ""
        chr_badge = f'<span class="badge-chr">{chr_id}</span>' if chr_id else ""

        cards_html += f"""
<div class="inf-card" style="border-left-color:{tier_col};">
  <div class="inf-header">
    <span class="inf-id">{fid}</span>
    <span class="inf-comp" style="color:{comp_col};">{COMP_LABELS.get(comp, comp)}</span>
    <span class="inf-tier" style="color:{tier_col};">{tier}</span>
    <span class="inf-sev">SIG {sev}</span>
    {ceiling_badge}{chr_badge}
  </div>
  <div class="inf-summary">{summary_text}</div>
  <div class="cac-label">CAC CONFIDENCE</div>
  <div class="cac-track">
    <div class="cac-fill" style="width:{cac_pct}%;background:{cac_col};"></div>
    <span class="cac-val" style="color:{cac_col};">{cac:.3f}</span>
  </div>
  <div class="inf-meta">
    <span class="inf-meta-item"><span class="meta-label">Journey</span>{journey or "—"}</span>
    <span class="inf-meta-item"><span class="meta-label">Signals</span>
      <span style="color:#CC0000;">P0:{counts.get('P0',0)}</span>
      <span style="color:#F5A623;margin-left:4px;">P1:{counts.get('P1',0)}</span>
      <span style="color:#4A9BD4;margin-left:4px;">P2:{counts.get('P2',0)}</span>
    </span>
    <span class="inf-kw">{kw_html}</span>
  </div>
</div>"""

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">INTELLIGENCE FINDINGS</span>
    <span style="font-size:10px;color:#3A6A7F;">
      Barclays &nbsp;&middot;&nbsp;
      {len(findings)} findings &nbsp;&middot;&nbsp;
      <span style="color:#CC0000;">{sum(1 for f in findings if f.get('designed_ceiling_reached'))} ceiling</span>
    </span>
  </div>
  <div class="topbar-box-body">
    {cards_html}
  </div>
</div>"""


def _build_clark_section() -> str:
    """Clark Protocol escalation status."""
    summary = active_clark_summary()
    active  = [e for e in summary.get("active", []) if e.get("competitor") == "barclays"]
    by_tier = {}
    for e in active:
        t = e.get("clark_tier", "CLARK-0")
        by_tier[t] = by_tier.get(t, 0) + 1
    top = "CLARK-0"
    for t in ["CLARK-3", "CLARK-2", "CLARK-1"]:
        if by_tier.get(t, 0) > 0:
            top = t
            break

    tier_strip = ""
    for tier in ["CLARK-3", "CLARK-2", "CLARK-1", "CLARK-0"]:
        count  = by_tier.get(tier, 0)
        colour = CLARK_COLOURS[tier]
        label  = CLARK_LABELS[tier]
        tier_strip += f"""
<div class="clark-tile" style="border-top-color:{colour};">
  <div class="clark-count" style="color:{colour};">{count}</div>
  <div class="clark-tier">{tier}</div>
  <div class="clark-label">{label}</div>
</div>"""

    rows_html = ""
    tier_order = {"CLARK-3": 0, "CLARK-2": 1, "CLARK-1": 2}
    for e in sorted(active, key=lambda x: tier_order.get(x.get("clark_tier", "CLARK-0"), 3)):
        fid     = e.get("finding_id", "—")
        comp    = e.get("competitor", "?")
        ctier   = e.get("clark_tier", "CLARK-0")
        cac     = e.get("cac_score", 0.0)
        reason  = e.get("reason", "")[:80]
        ts      = e.get("ts", "")[:16].replace("T", " ")
        colour  = CLARK_COLOURS.get(ctier, "#3A6A7F")
        label   = CLARK_LABELS.get(ctier, "?")
        comp_col = COMP_COLOURS.get(comp, "#7AACBF")
        rows_html += f"""
<div class="clark-row" style="border-left-color:{colour};">
  <span class="clark-badge" style="background:rgba(0,0,0,0.3);color:{colour};">{ctier} {label}</span>
  <span class="clark-fid">{fid}</span>
  <span class="clark-comp" style="color:{comp_col};">{COMP_LABELS.get(comp, comp)}</span>
  <span class="clark-cac">CAC {cac:.3f}</span>
  <span class="clark-reason">{reason}</span>
  <span class="clark-ts">{ts}</span>
</div>"""

    top_colour = CLARK_COLOURS.get(top, "#3A6A7F")
    top_label  = CLARK_LABELS.get(top, "NOMINAL")

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">CLARK PROTOCOL</span>
    <span style="font-size:10px;color:#3A6A7F;">Barclays &nbsp;&middot;&nbsp;</span>
    <span style="font-size:10px;color:{top_colour};font-weight:700;">{top} &mdash; {top_label}</span>
  </div>
  <div class="topbar-box-body">
    <div class="clark-strip">{tier_strip}</div>
    {'<div class="clark-rows">' + rows_html + '</div>' if active else '<div class="clark-empty">No active escalations.</div>'}
  </div>
</div>"""


def _build_phase2_section() -> str:
    """Phase 2 demand counter from Exit Strategy click log."""
    summary  = click_log_summary()
    ceiling  = load_ceiling_findings(limit=8)
    total    = summary.get("total", 0)
    unique   = summary.get("unique_findings", 0)
    latest   = summary.get("latest", "—")
    by_comp  = summary.get("competitors", {})

    comp_pills = "".join(
        f'<span style="background:#001E30;color:{COMP_COLOURS.get(c,"#7AACBF")};'
        f'font-size:10px;padding:2px 8px;border-radius:3px;margin-right:6px;">'
        f'{COMP_LABELS.get(c,c)} ({n})</span>'
        for c, n in by_comp.items()
    ) or '<span style="color:#3A6A7F;font-size:11px;">No requests logged yet</span>'

    ceiling_rows = ""
    for f in ceiling:
        fid  = f.get("finding_id", "—")
        comp = f.get("competitor", "?")
        cac  = f.get("confidence_score", 0.0)
        tier = f.get("finding_tier", "P3")
        summ = (f.get("finding_summary") or "")[:80]
        tier_col = TIER_COLOURS.get(tier, "#4A7A8F")
        comp_col = COMP_COLOURS.get(comp, "#7AACBF")
        ceiling_rows += f"""
<div style="background:#001828;border:1px solid #003A5C;border-left:3px solid {tier_col};
            border-radius:5px;padding:8px 12px;margin-bottom:6px;
            display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
  <span style="font-family:'DM Mono',monospace;font-size:9px;color:#3A6A7F;min-width:155px;">{fid}</span>
  <span style="color:{comp_col};font-size:10px;font-weight:600;">{COMP_LABELS.get(comp,comp)}</span>
  <span style="font-family:'DM Mono',monospace;font-size:10px;color:#F5A623;">CAC {cac:.3f}</span>
  <span style="font-size:10px;color:#7AACBF;flex:1;">{summ}</span>
</div>"""

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">PHASE 2 DEMAND</span>
    <span style="font-size:10px;color:#3A6A7F;">{len(ceiling)} ceiling findings &middot; internal telemetry required</span>
  </div>
  <div class="topbar-box-body">
    <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
      <div class="p2-stat">
        <div class="p2-num" style="color:#00AEEF;">{total}</div>
        <div class="p2-lbl">Phase 2 Requests</div>
      </div>
      <div class="p2-stat">
        <div class="p2-num" style="color:#F5A623;">{unique}</div>
        <div class="p2-lbl">Unique Findings</div>
      </div>
      <div class="p2-stat" style="flex:1;">
        <div style="font-size:10px;color:#3A6A7F;margin-bottom:4px;">BY COMPETITOR</div>
        {comp_pills}
        <div style="font-size:9px;color:#3A6A7F;margin-top:6px;">Last request: {latest}</div>
      </div>
    </div>
    {ceiling_rows}
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Page assembly
# ─────────────────────────────────────────────────────────────────────────────

def generate_v2_html(v1_html: str) -> str:
    """
    Inject V2 sections into the existing V1 HTML just before </body>.
    V1 page structure is preserved intact.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    vane_html    = _build_vane_section()
    inf_html     = _build_inference_section()
    clark_html   = _build_clark_section()
    p2_html      = _build_phase2_section()

    v2_styles = """
<style>
/* ── V2 additions — matches topbar layout pattern ── */
.v2-outer {
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.v2-divider {
  border: none; border-top: 1px solid #003A5C;
  margin: 0;
}
.v2-label {
  font-family: 'DM Mono', monospace;
  font-size: 10px; color: #3A6A7F;
  text-transform: uppercase; letter-spacing: 1.5px;
  padding: 8px 0 4px;
}
.v2-label span { color: #00AEEF; }
@media (max-width: 768px) {
  .v2-outer { padding: 12px 16px; gap: 12px; }
}
/* Inference cards */
.inf-card {
  background: #001828; border: 1px solid #003A5C;
  border-left: 3px solid #4A7A8F;
  border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;
}
.inf-header { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.inf-id { font-family: 'DM Mono', monospace; font-size: 9px; color: #3A6A7F; }
.inf-comp { font-size: 10px; font-weight: 600; padding: 1px 6px;
            background: #001E30; border-radius: 3px; }
.inf-tier, .inf-sev { font-size: 9px; padding: 2px 6px;
                       background: #001E30; border-radius: 3px; color: #4A7A8F; }
.badge-ceiling { font-size: 9px; padding: 2px 6px; border-radius: 3px;
                 background: #330000; color: #CC0000; margin-left: 4px; }
.badge-chr { font-size: 9px; padding: 2px 6px; border-radius: 3px;
             background: #001E30; color: #00AFA0; margin-left: 4px; }
.inf-summary { font-size: 12px; color: #E8F4FA; line-height: 1.5; margin-bottom: 8px; }
.cac-label { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
             letter-spacing: 0.8px; margin-bottom: 2px; }
.cac-track { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cac-track > div { flex: 1; height: 3px; background: #003A5C; border-radius: 2px; position: relative; }
.cac-fill { height: 3px; border-radius: 2px; }
.cac-val { font-family: 'DM Mono', monospace; font-size: 11px; min-width: 36px; }
.inf-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; }
.inf-meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 9px; color: #3A6A7F; text-transform: uppercase; letter-spacing: 0.5px; }
.inf-kw { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.kw-pill { background: #002030; color: #7AACBF; font-size: 9px;
           padding: 2px 5px; border-radius: 3px; }
/* Clark */
.clark-strip { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.clark-tile { flex: 1; min-width: 100px; background: #001828;
              border: 1px solid #003A5C; border-top: 3px solid #3A6A7F;
              border-radius: 8px; padding: 12px; text-align: center; }
.clark-count { font-family: 'DM Mono', monospace; font-size: 24px; font-weight: 800; }
.clark-tier { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
              letter-spacing: 1px; margin-top: 2px; }
.clark-label { font-size: 8px; color: #4A7A8F; }
.clark-rows { }
.clark-row {
  background: #001828; border: 1px solid #003A5C;
  border-left: 3px solid #4A7A8F; border-radius: 5px;
  padding: 8px 12px; margin-bottom: 6px;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.clark-badge { font-size: 9px; padding: 2px 7px; border-radius: 3px;
               font-weight: 700; letter-spacing: 0.5px; min-width: 90px;
               text-align: center; }
.clark-fid { font-family: 'DM Mono', monospace; font-size: 9px; color: #3A6A7F; min-width: 155px; }
.clark-comp { font-size: 10px; font-weight: 600; }
.clark-cac { font-family: 'DM Mono', monospace; font-size: 10px; color: #F5A623; }
.clark-reason { font-size: 10px; color: #4A7A8F; flex: 1; }
.clark-ts { font-size: 9px; color: #3A6A7F; }
.clark-empty { font-size: 11px; color: #3A6A7F; padding: 8px 0; }
/* Phase 2 */
.p2-stat { background: #001828; border: 1px solid #003A5C;
           border-radius: 8px; padding: 14px 18px; text-align: center;
           min-width: 120px; }
.p2-num { font-family: 'DM Mono', monospace; font-size: 28px; font-weight: 800; }
.p2-lbl { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
          letter-spacing: 1px; margin-top: 2px; }
</style>"""

    v2_block = f"""
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
{v2_styles}
<hr class="v2-divider">
<div class="v2-outer">
  <div class="v2-label">
    Sonar Intelligence Layer &nbsp;&middot;&nbsp;
    <span>Phase 1</span> &nbsp;&middot;&nbsp;
    {now_utc}
  </div>
  {vane_html}
  {inf_html}
  {clark_html}
  {p2_html}
</div>
"""

    # Inject before </body>
    if "</body>" in v1_html:
        return v1_html.replace("</body>", v2_block + "\n</body>")
    return v1_html + v2_block


# ─────────────────────────────────────────────────────────────────────────────
# GitHub Pages push (briefing-v2/index.html)
# ─────────────────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k not in env})
    return env


def publish_v2(html_content: str) -> tuple[bool, str]:
    """Push briefing-v2/index.html to GitHub Pages."""
    env       = _load_env()
    token     = env.get("GITHUB_TOKEN", "")
    repo_url  = env.get("PUBLISH_REPO", "")

    if not token:
        return False, "GITHUB_TOKEN not set"
    if not repo_url:
        return False, "PUBLISH_REPO not set"

    if repo_url.startswith("https://"):
        auth_url = repo_url.replace("https://", f"https://{token}@")
    else:
        slug = repo_url.rstrip("/")
        if not slug.endswith(".git"):
            slug += ".git"
        auth_url = f"https://{token}@github.com/{slug}"

    commit_msg = f"publish: Sonar V2 briefing {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp        = Path(tmpdir)
        clone_dir  = tmp / "pages_repo"

        print("  Cloning repo …")
        r = subprocess.run(
            ["git", "clone", "--depth=1", auth_url, str(clone_dir)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return False, f"git clone failed: {r.stderr.replace(token,'***').strip()}"

        v2_dir = clone_dir / "briefing-v2"
        v2_dir.mkdir(exist_ok=True)
        dest = v2_dir / "index.html"
        write_text_lf(dest, html_content)
        print(f"  Written to {dest}")

        for cmd in [
            ["git", "-C", str(clone_dir), "config", "user.email", "sonar-publish@cjipro.com"],
            ["git", "-C", str(clone_dir), "config", "user.name",  "Sonar Publisher"],
        ]:
            subprocess.run(cmd, capture_output=True)

        r = subprocess.run(
            ["git", "-C", str(clone_dir), "add", "briefing-v2/index.html"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return False, f"git add failed: {r.stderr.strip()}"

        r = subprocess.run(
            ["git", "-C", str(clone_dir), "commit", "-m", commit_msg],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            s = r.stderr.strip() + r.stdout.strip()
            if "nothing to commit" in s:
                return True, "Nothing to commit — already up to date"
            return False, f"git commit failed: {s}"

        print("  Pushing to main …")
        r = subprocess.run(
            ["git", "-C", str(clone_dir), "push", "origin", "main"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return False, f"git push failed: {r.stderr.replace(token,'***').strip()}"

    return True, commit_msg


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n-- Sonar Briefing V2 Publisher --")

    # 1. Get V1 HTML (from local output — already generated by publish.py)
    v1_path = OUTPUT_DIR / "index.html"
    if not v1_path.exists():
        print("  ERROR: V1 briefing not found at mil/publish/output/index.html")
        print("  Run: py run_daily.py --skip-fetch   first")
        sys.exit(1)
    v1_html = v1_path.read_text(encoding="utf-8")
    print(f"  V1 source: {v1_path} ({len(v1_html)//1024}KB)")

    # 2. Generate V2
    print("\n[1/3] Building V2 sections …")
    v2_html = generate_v2_html(v1_html)
    print(f"  V2 size: {len(v2_html)//1024}KB")

    # 3. Save local copy
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_v2 = OUTPUT_DIR / "index_v2.html"
    write_text_lf(local_v2, v2_html)
    print(f"  Local copy: {local_v2}")

    # 4. Publish
    print("\n[2/3] Publishing to GitHub Pages …")
    ok, msg = publish_v2(v2_html)
    print(f"  {'OK' if ok else 'FAIL'}: {msg}")

    print("\n[3/3] Report")
    print("-" * 56)
    print(f"  V1 (unchanged):  https://cjipro.com/briefing")
    print(f"  V2 (new):        https://cjipro.com/briefing-v2")
    print(f"  GitHub push:     {'SUCCESS' if ok else 'FAIL'}")
    print(f"  Local V2:        {local_v2}")
    print("-" * 56)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
