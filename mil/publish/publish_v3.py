#!/usr/bin/env python3
"""
publish_v3.py — MIL Sonar Briefing V3

Intelligence layer: churn risk score, analyst commentary (Sonnet), competitive
benchmarks (technical + service), inference findings, Clark Protocol.

Published to: cjipro.com/briefing-v3   (briefing-v3/index.html on GitHub Pages)
V1 (cjipro.com/briefing) and V2 (cjipro.com/briefing-v2) are NOT touched.

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
MIL_DIR    = SCRIPT_DIR.parent
REPO_ROOT  = MIL_DIR.parent
OUTPUT_DIR = SCRIPT_DIR / "output"

sys.path.insert(0, str(MIL_DIR))
sys.path.insert(0, str(REPO_ROOT))

from mil.publish.adapters import write_text_lf  # LF-only HTML writes

from mil.command.components.clark_protocol import active_clark_summary
from mil.command.components.inference_cards import load_findings
from mil.publish.box3_selector import (
    CLARK_ACTION_DETAILS,
    build_preamble_html,
    select_box3_issue,
)

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

# V3 CSS
V3_STYLES = """<style>
/* ── V3 wrapper ─────────────────────────────────────────────── */
.v3-divider { border: none; border-top: 2px solid #003A5C; margin: 32px 0 0; }
.v3-outer   { max-width: 960px; margin: 0 auto; padding: 24px 16px 40px; }
.v3-label   { font-size: 10px; color: #3A6A7F; text-transform: uppercase;
              letter-spacing: 1px; margin-bottom: 24px; }
/* ── Churn risk score ───────────────────────────────────────── */
.churn-header { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.churn-score-block { text-align: center; min-width: 110px; }
.churn-score-num { font-family: 'DM Mono', monospace; font-size: 48px; font-weight: 800;
                   line-height: 1; }
.churn-score-lbl { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
                   letter-spacing: 1px; margin-top: 4px; }
.churn-trend-block { display: flex; flex-direction: column; gap: 6px; }
.churn-trend-badge { display: inline-block; padding: 4px 10px; border-radius: 4px;
                     font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.churn-meta { font-size: 11px; color: #4A7A8F; margin-top: 4px; }
.churn-over-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.churn-issue-pill { font-size: 10px; padding: 3px 8px; border-radius: 4px;
                    border: 1px solid #CC3333; color: #CC3333; background: #1A0810; }
.churn-issue-pill.strength { border-color: #00AFA0; color: #00AFA0; background: #00100E; }
/* ── Commentary boxes ───────────────────────────────────────── */
.commentary-grid { display: flex; flex-direction: column; gap: 14px; }
.commentary-card { background: #001828; border: 1px solid #003A5C;
                   border-radius: 8px; padding: 16px 20px; }
.commentary-card.risk   { border-left: 4px solid #CC3333; }
.commentary-card.strength { border-left: 4px solid #00AFA0; }
.commentary-card-header { display: flex; align-items: center; gap: 10px;
                          margin-bottom: 10px; flex-wrap: wrap; }
.commentary-issue { font-size: 13px; font-weight: 700; color: #E8F4FA; }
.commentary-badge { font-size: 9px; padding: 2px 7px; border-radius: 3px;
                    font-weight: 700; letter-spacing: 0.5px; }
.commentary-badge.risk     { background: #2A0808; color: #CC3333; border: 1px solid #CC3333; }
.commentary-badge.strength { background: #001810; color: #00AFA0; border: 1px solid #00AFA0; }
.commentary-badge.sev-p0 { background: #2A0808; color: #CC0000; }
.commentary-badge.sev-p1 { background: #2A1200; color: #F5A623; }
.commentary-badge.sev-p2 { background: #001828; color: #4A9BD4; }
.commentary-stats { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
.commentary-stat { font-size: 10px; color: #3A6A7F; }
.commentary-stat span { font-family: 'DM Mono', monospace; color: #7AACBF; }
.commentary-prose { font-size: 12px; color: #C5DDE8; line-height: 1.65;
                    margin-bottom: 10px; }
.commentary-quote { font-size: 11px; color: #4A7A8F; font-style: italic;
                    border-left: 2px solid #003A5C; padding-left: 10px;
                    margin-top: 8px; }
.commentary-chr { font-size: 10px; color: #3A6A7F; margin-top: 6px; }
/* ── Benchmark tables ───────────────────────────────────────── */
.bench-table { width: 100%; border-collapse: separate; border-spacing: 0 4px; }
.bench-row-head { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
                  letter-spacing: 0.5px; padding: 4px 8px 8px; }
.bench-issue-row { background: #001828; border-radius: 5px; }
.bench-issue-name { font-size: 11px; color: #C5DDE8; padding: 10px 8px 10px 12px;
                    min-width: 170px; }
.bench-bar-cell { padding: 6px 8px; min-width: 120px; }
.bench-bar-wrap { display: flex; align-items: center; gap: 6px; }
.bench-bar-bg { flex: 1; background: #002030; border-radius: 3px;
                height: 8px; max-width: 100px; }
.bench-bar-fill { height: 8px; border-radius: 3px; }
.bench-bar-pct { font-family: 'DM Mono', monospace; font-size: 10px;
                 color: #7AACBF; min-width: 32px; }
.bench-gap-cell { font-family: 'DM Mono', monospace; font-size: 11px;
                  padding: 10px 8px; text-align: right; min-width: 60px; }
.bench-days-cell { font-size: 10px; color: #3A6A7F; padding: 10px 8px; min-width: 70px; }
.bench-gap-positive { color: #CC3333; }
.bench-gap-negative { color: #00AFA0; }
.bench-gap-neutral  { color: #4A7A8F; }
/* ── Intelligence findings ──────────────────────────────────── */
.inf-card { background: #001828; border: 1px solid #003A5C;
            border-left: 3px solid #4A7A8F; border-radius: 5px;
            padding: 10px 14px; margin-bottom: 8px; }
.inf-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
              margin-bottom: 6px; }
.inf-id   { font-family: 'DM Mono', monospace; font-size: 9px; color: #3A6A7F; }
.inf-comp { font-size: 10px; font-weight: 600; }
.inf-tier { font-size: 9px; font-weight: 700; }
.inf-sev  { font-size: 9px; color: #7AACBF; }
.badge-ceiling { font-size: 8px; background: #2A1200; color: #F5A623;
                 border: 1px solid #F5A623; padding: 1px 5px; border-radius: 3px; }
.badge-chr  { font-size: 8px; background: #001828; color: #4A9BD4;
              border: 1px solid #4A9BD4; padding: 1px 5px; border-radius: 3px; }
.inf-summary { font-size: 11px; color: #C5DDE8; margin-bottom: 6px; }
.cac-label { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
             letter-spacing: 0.5px; margin-bottom: 3px; }
.cac-track { display: flex; align-items: center; gap: 8px; height: 10px;
             background: #002030; border-radius: 4px; max-width: 200px; margin-bottom: 6px; }
.cac-fill  { height: 10px; border-radius: 4px; }
.cac-val   { font-family: 'DM Mono', monospace; font-size: 11px; min-width: 36px; }
.inf-meta  { display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; }
.inf-meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 9px; color: #3A6A7F; text-transform: uppercase; letter-spacing: 0.5px; }
.inf-kw    { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.kw-pill   { background: #002030; color: #7AACBF; font-size: 9px;
             padding: 2px 5px; border-radius: 3px; }
/* ── Clark Protocol ─────────────────────────────────────────── */
.clark-strip { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.clark-tile  { flex: 1; min-width: 100px; background: #001828;
               border: 1px solid #003A5C; border-top: 3px solid #3A6A7F;
               border-radius: 8px; padding: 12px; text-align: center; }
.clark-count { font-family: 'DM Mono', monospace; font-size: 24px; font-weight: 800; }
.clark-tier  { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
               letter-spacing: 1px; margin-top: 2px; }
.clark-label { font-size: 8px; color: #4A7A8F; }
.clark-row   { background: #001828; border: 1px solid #003A5C;
               border-left: 3px solid #4A7A8F; border-radius: 5px;
               padding: 8px 12px; margin-bottom: 6px;
               display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.clark-badge { font-size: 9px; padding: 2px 7px; border-radius: 3px;
               font-weight: 700; letter-spacing: 0.5px; min-width: 90px; text-align: center; }
.clark-fid   { font-family: 'DM Mono', monospace; font-size: 9px; color: #3A6A7F; min-width: 155px; }
.clark-comp  { font-size: 10px; font-weight: 600; }
.clark-cac   { font-family: 'DM Mono', monospace; font-size: 10px; color: #F5A623; }
.clark-reason { font-size: 10px; color: #4A7A8F; flex: 1; }
.clark-ts    { font-size: 9px; color: #3A6A7F; }
</style>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Churn Risk Score
# ─────────────────────────────────────────────────────────────────────────────

def _build_churn_risk_section(benchmark_result: dict) -> str:
    score   = benchmark_result.get("churn_risk_score", 0.0)
    trend   = benchmark_result.get("churn_risk_trend", "INSUFFICIENT_DATA")
    over    = benchmark_result.get("over_indexed", [])
    under   = benchmark_result.get("under_indexed", [])

    # Score colour
    if score >= 80:
        score_col = "#CC0000"
    elif score >= 40:
        score_col = "#F5A623"
    else:
        score_col = "#00AFA0"

    # Trend badge
    trend_colours = {
        "WORSENING":          ("background:#2A0808;color:#CC0000;border:1px solid #CC0000;", "WORSENING"),
        "STABLE":             ("background:#002030;color:#7AACBF;border:1px solid #3A6A7F;", "STABLE"),
        "IMPROVING":          ("background:#001810;color:#00AFA0;border:1px solid #00AFA0;", "IMPROVING"),
        "INSUFFICIENT_DATA":  ("background:#002030;color:#4A7A8F;border:1px solid #003A5C;", "INSUFFICIENT DATA"),
    }
    trend_style, trend_label = trend_colours.get(trend, trend_colours["INSUFFICIENT_DATA"])

    # Over-indexed pills
    over_pills = "".join(
        f'<span class="churn-issue-pill">{e["issue_type"]} +{e["gap_pp"]:.1f}pp</span>'
        for e in over[:5]
    )
    # Under-indexed pills (strength)
    under_pills = "".join(
        f'<span class="churn-issue-pill strength">{e["issue_type"]} {e["gap_pp"]:.1f}pp</span>'
        for e in under[:3]
    )

    over_section = f"""
<div style="margin-top:12px;">
  <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">
    Risk Signals — Barclays over-indexed vs peers
  </div>
  <div class="churn-over-list">{over_pills or '<span style="color:#3A6A7F;font-size:10px;">None</span>'}</div>
</div>""" if over else ""

    under_section = f"""
<div style="margin-top:10px;">
  <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">
    Competitive Strengths — Barclays under-indexed vs peers
  </div>
  <div class="churn-over-list">{under_pills}</div>
</div>""" if under else ""

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">CHURN RISK SCORE</span>
    <span style="font-size:10px;color:#3A6A7F;">Barclays vs 5 peers &middot; complaint-normalised &middot; all enriched records</span>
  </div>
  <div class="topbar-box-body">
    <div class="churn-header">
      <div class="churn-score-block">
        <div class="churn-score-num" style="color:{score_col};">{score:.1f}</div>
        <div class="churn-score-lbl">Churn Risk Score</div>
      </div>
      <div class="churn-trend-block">
        <span class="churn-trend-badge" style="{trend_style}">{trend_label}</span>
        <div class="churn-meta">
          {len(over)} issue type{'s' if len(over) != 1 else ''} over-indexed &nbsp;&middot;&nbsp;
          {len(under)} under-indexed
        </div>
      </div>
    </div>
    {over_section}
    {under_section}
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Analyst Commentary
# ─────────────────────────────────────────────────────────────────────────────

def _build_commentary_section(boxes: list[dict]) -> str:
    if not boxes:
        return ""

    cards_html = ""
    for box in boxes:
        btype    = box["type"]          # "risk" or "strength"
        issue    = box["issue_type"]
        cat      = box["category"]
        b_rate   = box["barclays_rate"]
        p_rate   = box["peer_avg_rate"]
        gap      = box["gap_pp"]
        sev      = box["dominant_severity"]
        days     = box["days_active"]
        prose    = box["prose"]
        quotes   = box["top_quotes"]
        chr_ctx  = box["chr_resonance"]
        first    = box.get("first_seen", "")

        sev_cls  = f"sev-{sev.lower()}"
        gap_str  = f"+{gap:.1f}pp" if gap > 0 else f"{gap:.1f}pp"
        gap_col  = "#CC3333" if gap > 0 else "#00AFA0"

        type_badge = (
            '<span class="commentary-badge risk">RISK</span>'
            if btype == "risk" else
            '<span class="commentary-badge strength">STRENGTH</span>'
        )
        sev_badge = f'<span class="commentary-badge {sev_cls}">{sev}</span>'
        cat_label = cat.upper()
        cached_badge = (
            '<span style="font-size:9px;padding:2px 6px;border-radius:3px;'
            'background:#1A1200;color:#F5A623;border:1px solid #F5A623;font-weight:700;">'
            '&#9888; CACHED</span>'
            if box.get("cached") else ""
        )

        stats_html = f"""
<div class="commentary-stats">
  <div class="commentary-stat">Barclays rate <span>{b_rate:.1f}%</span></div>
  <div class="commentary-stat">Peer avg <span>{p_rate:.1f}%</span></div>
  <div class="commentary-stat">Gap <span style="color:{gap_col};">{gap_str}</span></div>
  {'<div class="commentary-stat">Active <span>' + str(days) + ' days</span></div>' if days > 0 else ''}
  {'<div class="commentary-stat">Since <span>' + first + '</span></div>' if first else ''}
</div>"""

        quotes_html = ""
        for q in quotes[:1]:
            quotes_html = f'<div class="commentary-quote">&ldquo;{q}&rdquo;</div>'

        chr_html = ""
        if chr_ctx and btype == "risk":
            chr_html = f'<div class="commentary-chr">Chronicle context: {chr_ctx[:120]}...</div>'

        cards_html += f"""
<div class="commentary-card {btype}">
  <div class="commentary-card-header">
    <span class="commentary-issue">{issue}</span>
    {type_badge}
    {sev_badge}
    <span style="font-size:9px;color:#3A6A7F;">{cat_label}</span>
    {cached_badge}
  </div>
  {stats_html}
  <div class="commentary-prose">{prose}</div>
  {quotes_html}
  {chr_html}
</div>"""

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">ANALYST COMMENTARY</span>
    <span style="font-size:10px;color:#3A6A7F;">
      Sonnet inference per issue type &nbsp;&middot;&nbsp;
      {sum(1 for b in boxes if b['type'] == 'risk')} risk &nbsp;&middot;&nbsp;
      {sum(1 for b in boxes if b['type'] == 'strength')} strength
    </span>
  </div>
  <div class="topbar-box-body">
    <div class="commentary-grid">
      {cards_html}
    </div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 + 4 — Competitive Benchmark (Technical + Service)
# ─────────────────────────────────────────────────────────────────────────────

def _bench_row(issue: str, barcl_rate: float, peer_avg: float, over_indexed: bool,
               dominant_sev: str, days_active: int, is_last: bool = False) -> str:
    gap    = barcl_rate - peer_avg
    gap_str = f"+{gap:.1f}pp" if gap > 0 else f"{gap:.1f}pp"
    gap_cls = "bench-gap-positive" if gap > 2 else ("bench-gap-negative" if gap < -2 else "bench-gap-neutral")

    # Bar widths (peer avg = 50% of max width = baseline reference)
    max_val = max(barcl_rate, peer_avg, 1.0)
    b_pct   = int((barcl_rate / max_val) * 100)
    p_pct   = int((peer_avg / max_val) * 100)

    b_col = "#CC3333" if over_indexed else "#00AEEF"
    p_col = "#3A6A7F"

    sev_col = {"P0": "#CC0000", "P1": "#F5A623", "P2": "#4A9BD4"}.get(dominant_sev, "#4A9BD4")
    sev_dot = f'<span style="color:{sev_col};font-size:8px;margin-right:2px;">&#9679;</span>'

    days_html = f'<div class="bench-days-cell">{days_active}d active</div>' if days_active > 0 else '<div class="bench-days-cell"></div>'

    return f"""
<tr class="bench-issue-row">
  <td class="bench-issue-name">{sev_dot}{issue}</td>
  <td class="bench-bar-cell">
    <div style="margin-bottom:3px;">
      <div style="font-size:8px;color:#3A6A7F;margin-bottom:2px;">Barclays</div>
      <div class="bench-bar-wrap">
        <div class="bench-bar-bg">
          <div class="bench-bar-fill" style="width:{b_pct}%;background:{b_col};"></div>
        </div>
        <span class="bench-bar-pct" style="color:{b_col};">{barcl_rate:.1f}%</span>
      </div>
    </div>
    <div>
      <div style="font-size:8px;color:#3A6A7F;margin-bottom:2px;">Peer avg</div>
      <div class="bench-bar-wrap">
        <div class="bench-bar-bg">
          <div class="bench-bar-fill" style="width:{p_pct}%;background:{p_col};"></div>
        </div>
        <span class="bench-bar-pct">{peer_avg:.1f}%</span>
      </div>
    </div>
  </td>
  <td class="bench-gap-cell {gap_cls}">{gap_str}</td>
  {days_html}
</tr>"""


def _build_benchmark_section(category: str, category_label: str,
                              benchmark: dict, persistence_map: dict) -> str:
    """Build a benchmark table for one category (technical or service)."""
    barcl_rates = benchmark.get("competitors", {}).get("barclays", {}).get(category, {})
    peer_avg    = benchmark.get("peer_avg", {}).get(category, {})

    if not barcl_rates:
        return ""

    rows_html = ""
    for issue in sorted(barcl_rates.keys()):
        b_rate = barcl_rates.get(issue, 0.0)
        p_rate = peer_avg.get(issue, 0.0)
        gap    = b_rate - p_rate

        # Pull persistence data if available
        persist = persistence_map.get(issue, {})
        over    = persist.get("over_indexed", gap > 0)
        sev     = persist.get("dominant_severity", "P2")
        days    = persist.get("days_active", 0)

        rows_html += _bench_row(issue, b_rate, p_rate, over, sev, days)

    # Competitor comparison row
    comp_pills = ""
    for comp in ["natwest", "lloyds", "hsbc", "monzo", "revolut"]:
        rates = benchmark.get("competitors", {}).get(comp, {}).get(category, {})
        avg   = sum(rates.values()) / max(len(rates), 1)
        col   = COMP_COLOURS.get(comp, "#7AACBF")
        comp_pills += f'<span style="font-size:10px;color:{col};margin-right:10px;">{COMP_LABELS[comp]}: {avg:.1f}%</span>'

    icon = "&#9888;" if category == "technical" else "&#9998;"
    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">{icon} {category_label.upper()} BENCHMARK</span>
    <span style="font-size:10px;color:#3A6A7F;">Barclays complaint rate vs 5-bank peer average &middot; % of complaint records</span>
  </div>
  <div class="topbar-box-body">
    <div style="margin-bottom:12px;font-size:10px;color:#3A6A7F;">
      Peer avg rates: {comp_pills}
    </div>
    <table class="bench-table">
      <thead>
        <tr>
          <th class="bench-row-head">Issue Type</th>
          <th class="bench-row-head">Rate Comparison</th>
          <th class="bench-row-head" style="text-align:right;">Gap</th>
          <th class="bench-row-head">Persistence</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Intelligence Findings
# ─────────────────────────────────────────────────────────────────────────────

def _build_findings_section() -> str:
    findings = load_findings(competitor="barclays", limit=8)
    if not findings:
        return ""

    cards_html = ""
    for f in findings:
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

        tier_col = TIER_COLOURS.get(tier, "#4A7A8F")
        cac_pct  = min(int(cac * 100), 100)
        cac_col  = "#CC0000" if cac >= 0.65 else ("#F5A623" if cac >= 0.45 else "#4A9BD4")

        kw_html = "".join(f'<span class="kw-pill">{k}</span>' for k in keywords)
        ceiling_badge = '<span class="badge-ceiling">&#9873; CEILING</span>' if ceiling else ""
        chr_badge = f'<span class="badge-chr">{chr_id}</span>' if chr_id else ""

        cards_html += f"""
<div class="inf-card" style="border-left-color:{tier_col};">
  <div class="inf-header">
    <span class="inf-id">{fid}</span>
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
      Barclays &nbsp;&middot;&nbsp; top {len(findings)} by CAC score &nbsp;&middot;&nbsp;
      <span style="color:#CC0000;">{sum(1 for f in findings if f.get('designed_ceiling_reached'))} ceiling</span>
    </span>
  </div>
  <div class="topbar-box-body">{cards_html}</div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Clark Protocol
# ─────────────────────────────────────────────────────────────────────────────

def _build_clark_section() -> str:
    summary = active_clark_summary()
    active  = [e for e in summary.get("active", []) if e.get("competitor") == "barclays"]
    by_tier = {}
    for e in active:
        t = e.get("clark_tier", "CLARK-0")
        by_tier[t] = by_tier.get(t, 0) + 1

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
        fid    = e.get("finding_id", "—")
        ctier  = e.get("clark_tier", "CLARK-0")
        cac    = e.get("cac_score", 0.0)
        reason = e.get("reason", "")[:80]
        ts     = e.get("ts", "")[:16].replace("T", " ")
        colour = CLARK_COLOURS.get(ctier, "#3A6A7F")
        label  = CLARK_LABELS.get(ctier, "?")
        rows_html += f"""
<div class="clark-row" style="border-left-color:{colour};">
  <span class="clark-badge" style="background:{colour}22;color:{colour};border:1px solid {colour};">{ctier} — {label}</span>
  <span class="clark-fid">{fid}</span>
  <span class="clark-cac">CAC {cac:.3f}</span>
  <span class="clark-reason">{reason}</span>
  <span class="clark-ts">{ts}</span>
</div>"""

    if not active:
        rows_html = '<div style="font-size:11px;color:#3A6A7F;padding:8px 0;">No active Barclays escalations.</div>'

    return f"""
<div class="topbar-box">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">CLARK PROTOCOL</span>
    <span style="font-size:10px;color:#3A6A7F;">Barclays escalation status</span>
  </div>
  <div class="topbar-box-body">
    <div class="clark-strip">{tier_strip}</div>
    <div>{rows_html}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Box 3 replacement — V3 swaps Barclays Alert with Intelligence Summary
# ─────────────────────────────────────────────────────────────────────────────

def _replace_box3(html: str) -> str:
    """
    Replace V1's exec-alert-panel (Box 3) with a placeholder.
    The placeholder is later substituted with the V3 exec summary box.
    """
    marker = '<!-- Right: Barclays Alert panel'
    start_comment = html.find(marker)
    if start_comment == -1:
        cls_marker = 'class="topbar-box exec-alert-panel"'
        cls_idx = html.find(cls_marker)
        if cls_idx == -1:
            return html
        start_comment = html.rfind('<div', 0, cls_idx)

    first_div = html.find('<div', start_comment)
    if first_div == -1:
        return html

    depth = 0
    i = first_div
    end_idx = first_div
    while i < len(html):
        if html[i:i+4] == '<div':
            depth += 1
            i += 4
        elif html[i:i+6] == '</div>':
            depth -= 1
            if depth == 0:
                end_idx = i + 6
                break
            i += 6
        else:
            i += 1

    return html[:start_comment] + '<!-- V3-BOX3 -->' + html[end_idx:]


def _compute_issue_volume_stats(issue_type: str) -> dict | None:
    """
    Return 7-day review volume + WoW delta for a given issue_type in Barclays
    public reviews (App Store + Google Play). Also returns the total 7-day
    Barclays review volume (the denominator) so the strip can say "9 of 72".

    Returns {count_7d, count_prior, total_7d, wow_delta_pct} or None if no
    matching records. wow_delta_pct is None when the prior week had zero
    reviews (can't compute ratio).
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    enriched_dir = MIL_DIR / "data" / "historical" / "enriched"
    records: list[dict] = []
    for fname in ("app_store_barclays_enriched.json", "google_play_barclays_enriched.json"):
        path = enriched_dir / fname
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records.extend(data.get("records", []))
        except Exception:
            continue
    if not records:
        return None

    now       = _dt.now(_tz.utc)
    cutoff_7  = now - _td(days=7)
    cutoff_14 = now - _td(days=14)

    count_7 = 0
    count_prior = 0
    total_7 = 0
    for r in records:
        date_str = r.get("date") or r.get("at") or r.get("review_date")
        if not date_str:
            continue
        try:
            dt = _dt.fromisoformat(str(date_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
        except (ValueError, TypeError):
            continue
        in_7 = dt >= cutoff_7
        in_prior = (not in_7) and dt >= cutoff_14
        if in_7:
            total_7 += 1
        if r.get("issue_type") != issue_type:
            continue
        if in_7:
            count_7 += 1
        elif in_prior:
            count_prior += 1

    if count_7 + count_prior == 0:
        return None

    wow_delta = None
    if count_prior > 0:
        wow_delta = (count_7 - count_prior) / count_prior * 100.0

    return {
        "count_7d":      count_7,
        "count_prior":   count_prior,
        "total_7d":      total_7,
        "wow_delta_pct": wow_delta,
    }


def _build_volume_strip(over_entry: dict) -> str:
    """
    Render the KPI tile row below the preamble: movement / peer gap / persistence.
    Each tile = big monospace number + uppercase label + context-micro.
    flex-wrap stacks tiles below ~440px container width. Followed by the
    surface-signal calibration caveat so the exec frames absolute volume
    against likely true customer impact.
    """
    stats = _compute_issue_volume_stats(over_entry["issue_type"])
    if not stats or stats["count_7d"] == 0:
        return ""

    c7         = stats["count_7d"]
    delta      = stats["wow_delta_pct"]
    days       = over_entry.get("days_active", 0) or 0
    gap        = float(over_entry.get("gap_pp", 0.0) or 0.0)
    b_rate     = float(over_entry.get("barclays_rate", 0.0) or 0.0)
    p_rate     = float(over_entry.get("peer_avg_rate", 0.0) or 0.0)
    first_seen = over_entry.get("first_seen") or ""

    # Tile 1 — WoW volume (teal if falling, red/amber if rising).
    if delta is None:
        wow_num, wow_colour, wow_label = "—", "#3A6A7F", "no prior week"
    elif delta >= 30:
        wow_num, wow_colour, wow_label = f"&uarr; {delta:.0f}%", "#CC0000", "WoW volume"
    elif delta > 0:
        wow_num, wow_colour, wow_label = f"&uarr; {delta:.0f}%", "#F5A623", "WoW volume"
    elif delta < 0:
        wow_num, wow_colour, wow_label = f"&darr; {abs(delta):.0f}%", "#00AFA0", "WoW volume"
    else:
        wow_num, wow_colour, wow_label = "flat", "#7AACBF", "WoW volume"
    wow_ctx = f"{c7} review this week" if c7 == 1 else f"{c7} reviews this week"

    # Tile 2 — peer gap (red when positive, teal when negative; amber narrow-miss).
    if gap > 2:
        gap_colour = "#CC0000"
    elif gap > 0:
        gap_colour = "#F5A623"
    elif gap < -2:
        gap_colour = "#00AFA0"
    else:
        gap_colour = "#7AACBF"
    gap_num = f"+{gap:.1f}pp" if gap > 0 else f"{gap:.1f}pp"
    gap_ctx = f"{b_rate:.1f}% vs {p_rate:.1f}%"

    # Tile 3 — persistence (amber at 7d+, red at 14d+).
    if days >= 14:
        pers_colour = "#CC0000"
    elif days >= 7:
        pers_colour = "#F5A623"
    else:
        pers_colour = "#7AACBF"
    pers_num = f"{days}d" if days > 0 else "new"
    pers_ctx = f"since {first_seen}" if first_seen else "first day active"

    tile_base  = ("flex:1 1 140px;min-width:140px;padding:12px 14px;"
                  "background:#001828;border:1px solid #003A5C;border-radius:4px;")
    num_style  = ("font-family:'DM Mono',monospace;font-size:24px;font-weight:700;"
                  "line-height:1;margin-bottom:6px;letter-spacing:0.5px;")
    lbl_style  = ("font-size:9px;color:#7AACBF;text-transform:uppercase;"
                  "letter-spacing:1.2px;margin-bottom:4px;font-weight:600;")
    ctx_style  = ("font-size:10px;color:#4A7A8F;font-family:'DM Mono',monospace;")

    return f"""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
  <div style="{tile_base}">
    <div style="{num_style}color:{wow_colour};">{wow_num}</div>
    <div style="{lbl_style}">{wow_label}</div>
    <div style="{ctx_style}">{wow_ctx}</div>
  </div>
  <div style="{tile_base}">
    <div style="{num_style}color:{gap_colour};">{gap_num}</div>
    <div style="{lbl_style}">vs peer avg</div>
    <div style="{ctx_style}">{gap_ctx}</div>
  </div>
  <div style="{tile_base}">
    <div style="{num_style}color:{pers_colour};">{pers_num}</div>
    <div style="{lbl_style}">sustained</div>
    <div style="{ctx_style}">{pers_ctx}</div>
  </div>
</div>
<div style="font-size:9px;color:#3A6A7F;font-style:italic;margin-bottom:14px;">
  Public reviews are surface signal. True customer impact is typically orders of magnitude larger.
</div>"""


def _build_exec_summary_box(benchmark_result: dict, boxes: list[dict]) -> str:
    """
    V3 Box 3 — Executive Intelligence Brief.

    Selects a single lead issue via the 6-key tiebreaker in box3_selector
    (Clark tier → trend → severity → days → severity-weighted gap → name).
    Same issue drives the preamble, volume stat strip, THE SITUATION, PEER
    COMPARISON, and THE CALL so the brief tells one story end to end.
    """
    over  = benchmark_result.get("over_indexed", [])
    under = benchmark_result.get("under_indexed", [])

    # ── Pick the single lead issue (6-key tiebreaker) ────────────────────────
    try:
        clark_summary = active_clark_summary()
    except Exception:
        clark_summary = {"active": []}
    selected = select_box3_issue(over, clark_summary=clark_summary)
    # Persist the selected issue for MIL-49 briefing_email — decoupled from HTML.
    try:
        from mil.publish.box3_selector import write_priority_artifact
        write_priority_artifact(selected)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("box3 priority artifact write failed: %s", exc)

    # ── Paragraph 1: THE SITUATION ────────────────────────────────────────────
    # Prefer the Sonnet commentary box whose issue matches the selected lead.
    # Fall back to the first risk box (legacy behaviour), then deterministic prose.
    risk_boxes = [b for b in boxes if b.get("type") == "risk" and b.get("prose")]
    matched_box = None
    if selected:
        matched_box = next(
            (b for b in risk_boxes if b.get("issue_type") == selected["issue_type"]),
            None,
        )
    top_box = matched_box or (risk_boxes[0] if risk_boxes else None)
    top_quote = ""

    if top_box:
        situation = top_box["prose"]
        top_quote = (top_box.get("top_quotes") or [""])[0]
    elif selected:
        issue_name = selected["issue_type"]
        sev        = selected.get("dominant_severity", "P1")
        days       = selected.get("days_active", 0)
        days_str   = f" for {days} consecutive days" if days > 1 else ""
        situation  = (
            f"Barclays is showing elevated {issue_name} signals{days_str}. "
            f"The dominant severity is {sev}. "
            f"This is the leading complaint category in the current review corpus."
        )
    else:
        situation = "No significant over-indexed signals detected in the current review corpus."

    # ── Paragraph 2: THE PEER ────────────────────────────────────────────────
    # Deterministic from benchmark gap data — no Chronicle involved.
    # Ranks Barclays within the 6-bank cohort on the *selected* lead issue.
    if selected:
        issue_name = selected["issue_type"]
        b_rate     = selected.get("barclays_rate", 0.0)

        benchmark_raw = benchmark_result.get("benchmark", {})
        cat = selected.get("category", "technical")
        peer_rates: dict[str, float] = {}
        for comp in ["natwest", "lloyds", "hsbc", "monzo", "revolut"]:
            comp_data = benchmark_raw.get("competitors", {}).get(comp, {})
            rate = comp_data.get(cat, {}).get(issue_name)
            if rate is not None:
                peer_rates[COMP_LABELS.get(comp, comp)] = rate

        if peer_rates:
            all_rates = {**peer_rates, COMP_LABELS.get("barclays", "Barclays"): b_rate}
            ranked = sorted(all_rates.items(), key=lambda kv: kv[1])
            pos = next(
                (i + 1 for i, (name, _) in enumerate(ranked)
                 if name == COMP_LABELS.get("barclays", "Barclays")),
                len(ranked),
            )
            if 10 <= pos % 100 <= 20:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(pos % 10, "th")
            ordinal = f"{pos}{suffix}"

            best_peer, best_rate = ranked[0]
            peer_prose = (
                f"Barclays ranks {ordinal} of {len(ranked)} on {issue_name}. "
                f"Best in the cohort is {best_peer} at {best_rate:.1f}%."
            )
        else:
            peer_prose = f"Benchmark data unavailable for {issue_name}."

        if under:
            strength = under[0]
            peer_prose += (
                f" On {strength['issue_type']}, Barclays leads the cohort — "
                f"{abs(strength['gap_pp']):.1f}pp below average."
            )
    else:
        peer_prose = "Barclays complaint rates are broadly in line with the 5-bank peer cohort. No material over-indexed issues detected."

    # ── Paragraph 3: THE CALL ────────────────────────────────────────────────
    # Use the selected issue's own Clark tier so the brief stays coherent.
    # Fall back to the highest-tier Barclays escalation when the selected
    # issue isn't itself escalated.
    top_tier = selected.get("clark_tier", "CLARK-0") if selected else "CLARK-0"
    if top_tier == "CLARK-0":
        try:
            active_clark = [e for e in clark_summary.get("active", [])
                            if e.get("competitor") == "barclays"]
            for t in ["CLARK-3", "CLARK-2", "CLARK-1"]:
                if any(e.get("clark_tier") == t for e in active_clark):
                    top_tier = t
                    break
        except Exception:
            pass

    clark_col      = CLARK_COLOURS[top_tier]
    action_details = CLARK_ACTION_DETAILS[top_tier]
    clark_label    = CLARK_LABELS[top_tier]

    # ── Assemble prose box ────────────────────────────────────────────────────
    quote_html = ""
    if top_quote and len(top_quote) > 20:
        quote_html = f"""
<div style="font-size:11px;color:#4A7A8F;font-style:italic;
            border-left:2px solid #003A5C;padding-left:10px;
            margin:10px 0 14px;">&ldquo;{top_quote[:220]}&rdquo;</div>"""

    def _section(label: str, prose: str, colour: str = "#3A6A7F", first: bool = False) -> str:
        border = "" if first else "border-top:1px solid #003A5C;padding-top:14px;"
        return f"""
<div style="margin-bottom:14px;{border}">
  <div style="font-size:9px;color:{colour};text-transform:uppercase;
              letter-spacing:1px;margin-bottom:5px;">{label}</div>
  <div style="font-size:12px;color:#C5DDE8;line-height:1.65;">{prose}</div>
</div>"""

    volume_strip_html = _build_volume_strip(selected) if selected else ""

    vol_stats = _compute_issue_volume_stats(selected["issue_type"]) if selected else None
    preamble_html = build_preamble_html(selected, vol_stats)

    return f"""
<div class="topbar-box exec-alert-panel">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title" style="color:#7AACBF;">INTELLIGENCE BRIEF</span>
    <span style="font-size:10px;color:#3A6A7F;">Barclays &middot; latest reviews + peer signals &middot; detail below</span>
  </div>
  <div class="topbar-box-body">
    {preamble_html}
    {volume_strip_html}
    {_section("The Situation", situation, first=True)}
    {quote_html}
    {_section("Peer Comparison", peer_prose)}
    <div style="margin-top:14px;border-top:1px solid #003A5C;padding-top:14px;">
      <span style="display:inline-block;padding:8px 14px;border-radius:4px;
                   background:{clark_col}22;border:1px solid {clark_col};">
        <span style="display:block;font-size:11px;font-weight:700;letter-spacing:1px;color:{clark_col};">
          {top_tier} &mdash; {clark_label}
        </span>
        <span style="display:block;font-size:10px;color:#7AACBF;margin-top:4px;
                     font-family:'DM Mono',monospace;letter-spacing:0.3px;">
          {action_details}
        </span>
      </span>
    </div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Assemble V3 HTML
# ─────────────────────────────────────────────────────────────────────────────

def generate_v3_html(v1_html: str) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Load benchmark data
    sys.path.insert(0, str(MIL_DIR / "data"))
    try:
        from benchmark_engine import run as benchmark_run
        benchmark_result = benchmark_run(mode="daily")
    except Exception as exc:
        print(f"  [WARNING] benchmark_engine failed: {exc}")
        benchmark_result = {}

    # Build persistence map {issue_type: entry} for today
    persistence_map: dict[str, dict] = {}
    persistence_log = MIL_DIR / "data" / "issue_persistence_log.jsonl"
    if persistence_log.exists():
        import json as _json
        all_entries = []
        for line in persistence_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    all_entries.append(_json.loads(line))
                except Exception:
                    pass
        if all_entries:
            latest_date = max(e["date"] for e in all_entries)
            persistence_map = {e["issue_type"]: e for e in all_entries if e["date"] == latest_date}

    # Load commentary
    boxes = []
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from commentary_engine import generate_commentary
        boxes = generate_commentary()
        # Persist commentary to log for analytics DB
        _commentary_log = MIL_DIR / "data" / "commentary_log.jsonl"
        _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(_commentary_log, "a", encoding="utf-8") as _f:
            for _box in boxes:
                _f.write(json.dumps({"date": _today, **_box}) + "\n")
    except Exception as exc:
        print(f"  [WARNING] commentary_engine failed: {exc}")

    benchmark = benchmark_result.get("benchmark", {})

    # Replace V1 Box 3 with V3 exec summary (in-grid, same column slot)
    exec_summary_html = _build_exec_summary_box(benchmark_result, boxes)
    v1_html = _replace_box3(v1_html)
    v1_html = v1_html.replace('<!-- V3-BOX3 -->', exec_summary_html)

    # Build intelligence sections (below the fold)
    churn_html    = _build_churn_risk_section(benchmark_result)
    comment_html  = _build_commentary_section(boxes)
    tech_html     = _build_benchmark_section("technical", "Technical Issues", benchmark, persistence_map)
    svc_html      = _build_benchmark_section("service", "Service Issues", benchmark, persistence_map)
    findings_html = _build_findings_section()
    clark_html    = _build_clark_section()

    v3_block = f"""
{V3_STYLES}
<hr class="v3-divider">
<div class="v3-outer">
  <div class="v3-label">
    Sonar V3 &nbsp;&middot;&nbsp; Intelligence Layer &nbsp;&middot;&nbsp; {now_utc}
  </div>
  {churn_html}
  {comment_html}
  {tech_html}
  {svc_html}
  {findings_html}
  {clark_html}
</div>
"""

    if "</body>" in v1_html:
        return v1_html.replace("</body>", v3_block + "\n</body>")
    return v1_html + v3_block


# ─────────────────────────────────────────────────────────────────────────────
# GitHub Pages push (briefing-v3/index.html)
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


def publish_v3(html_content: str) -> tuple[bool, str]:
    """Push briefing-v3/index.html to GitHub Pages."""
    env      = _load_env()
    token    = env.get("GITHUB_TOKEN", "")
    repo_url = env.get("PUBLISH_REPO", "")

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

    commit_msg = f"publish: Sonar V3 briefing {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp       = Path(tmpdir)
        clone_dir = tmp / "pages_repo"

        print("  Cloning repo ...")
        r = subprocess.run(
            ["git", "clone", "--depth=1", auth_url, str(clone_dir)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return False, f"git clone failed: {r.stderr.replace(token,'***').strip()}"

        v3_dir = clone_dir / "briefing-v3"
        v3_dir.mkdir(exist_ok=True)
        dest = v3_dir / "index.html"
        write_text_lf(dest, html_content)
        print(f"  Written to {dest}")

        for cmd in [
            ["git", "-C", str(clone_dir), "config", "user.email", "sonar-publish@cjipro.com"],
            ["git", "-C", str(clone_dir), "config", "user.name",  "Sonar Publisher"],
        ]:
            subprocess.run(cmd, capture_output=True)

        r = subprocess.run(
            ["git", "-C", str(clone_dir), "add", "briefing-v3/index.html"],
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

        print("  Pushing to main ...")
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
    print("\n-- Sonar Briefing V3 Publisher --")

    v1_path = OUTPUT_DIR / "index.html"
    if not v1_path.exists():
        print("  ERROR: V1 briefing not found at mil/publish/output/index.html")
        print("  Run publish.py first (or run_daily.py)")
        sys.exit(1)
    v1_html = v1_path.read_text(encoding="utf-8")
    print(f"  V1 source: {v1_path} ({len(v1_html)//1024}KB)")

    print("\n[1/3] Building V3 sections ...")
    v3_html = generate_v3_html(v1_html)
    print(f"  V3 size: {len(v3_html)//1024}KB")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_v3 = OUTPUT_DIR / "index_v3.html"
    write_text_lf(local_v3, v3_html)
    print(f"  Local copy: {local_v3}")

    print("\n[2/3] Publishing to GitHub Pages ...")
    ok, msg = publish_v3(v3_html)
    print(f"  {'OK' if ok else 'FAIL'}: {msg}")

    print("\n[3/3] Report")
    print("-" * 56)
    print(f"  V1 (unchanged):  https://cjipro.com/briefing")
    print(f"  V2 (unchanged):  https://cjipro.com/briefing-v2")
    print(f"  V3 (new):        https://cjipro.com/briefing-v3")
    print(f"  GitHub push:     {'SUCCESS' if ok else 'FAIL'}")
    print(f"  Local V3:        {local_v3}")
    print("-" * 56)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
