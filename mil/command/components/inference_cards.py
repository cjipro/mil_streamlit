"""
inference_cards.py — MIL-13 Inference Cards component.

Renders structured finding cards from mil/outputs/mil_findings.json.
Replaces the placeholder "Active Inferences" block in mil/command/app.py.

Features:
- Loads all findings directly from mil_findings.json
- Filters: competitor, tier, designed ceiling
- Sorted by CAC score descending
- Each card shows: ID, competitor, summary, CAC bar, severity, chronicle anchor,
  blind spots, signal counts, keywords, ceiling indicator
- Designed Ceiling findings flagged with Phase 2 request badge

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIL_ROOT      = Path(__file__).parent.parent.parent
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"

# Competitor display names and colours (match dashboard palette)
COMP_META = {
    "barclays": {"label": "Barclays",  "colour": "#00AEEF"},
    "natwest":  {"label": "NatWest",   "colour": "#F5A623"},
    "lloyds":   {"label": "Lloyds",    "colour": "#00AFA0"},
    "monzo":    {"label": "Monzo",     "colour": "#7B5EA7"},
    "revolut":  {"label": "Revolut",   "colour": "#4A9BD4"},
    "hsbc":     {"label": "HSBC",      "colour": "#CC3300"},
}

TIER_COLOURS = {
    "P1": "#CC0000",
    "P2": "#F5A623",
    "P3": "#4A7A8F",
}

SEVERITY_COLOURS = {
    "P0": "#CC0000",
    "P1": "#F5A623",
    "P2": "#4A9BD4",
}

JOURNEY_LABELS = {
    "J_AUTH_01":    "Log In",
    "J_PAY_01":     "Make a Payment",
    "J_TRANSFER_01":"Transfer Money",
    "J_ACCOUNT_01": "View Account",
    "J_CARD_01":    "Card Management",
    "J_SERVICE_01": "General App Use",
    "J_ONBOARD_01": "Onboarding",
    "J_SAVINGS_01": "Savings",
    "J_INVEST_01":  "Investments",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data layer
# ─────────────────────────────────────────────────────────────────────────────

def load_findings(
    competitor: Optional[str] = None,
    tier: Optional[str] = None,
    ceiling_only: bool = False,
    limit: int = 15,
) -> list[dict]:
    """
    Load and filter findings from mil_findings.json.
    Returns up to `limit` findings sorted by CAC score descending.
    """
    if not FINDINGS_FILE.exists():
        logger.warning("[inference_cards] %s not found", FINDINGS_FILE)
        return []

    try:
        payload = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
        findings = payload.get("findings", [])
    except Exception as exc:
        logger.error("[inference_cards] failed to read findings: %s", exc)
        return []

    if competitor:
        findings = [f for f in findings if f.get("competitor") == competitor]
    if tier:
        findings = [f for f in findings if f.get("finding_tier") == tier]
    if ceiling_only:
        findings = [f for f in findings if f.get("designed_ceiling_reached")]

    findings.sort(key=lambda f: f.get("confidence_score", 0), reverse=True)
    return findings[:limit]


def findings_summary() -> dict:
    """Return high-level counts for the filter bar header."""
    if not FINDINGS_FILE.exists():
        return {}
    try:
        payload = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
        findings = payload.get("findings", [])
    except Exception:
        return {}

    return {
        "total":   len(findings),
        "ceiling": sum(1 for f in findings if f.get("designed_ceiling_reached")),
        "p1_tier": sum(1 for f in findings if f.get("finding_tier") == "P1"),
        "p2_tier": sum(1 for f in findings if f.get("finding_tier") == "P2"),
        "countersigned": sum(1 for f in findings if f.get("human_countersign_status") == "COUNTERSIGNED"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Card HTML builder (used by both Streamlit and static export)
# ─────────────────────────────────────────────────────────────────────────────

def _cac_bar_html(score: float) -> str:
    """Render a CAC confidence bar (0.0–1.0 → 0–100%)."""
    pct = min(int(score * 100), 100)
    colour = "#CC0000" if score >= 0.65 else ("#F5A623" if score >= 0.45 else "#4A9BD4")
    return f"""
    <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
      <div style="flex:1;height:3px;background:#003A5C;border-radius:2px;">
        <div style="width:{pct}%;height:3px;background:{colour};border-radius:2px;"></div>
      </div>
      <span style="font-family:'DM Mono',monospace;font-size:11px;color:{colour};min-width:36px;">{score:.3f}</span>
    </div>"""


def _finding_card_html(f: dict) -> str:
    """Build HTML for one inference card."""
    comp     = f.get("competitor", "unknown")
    comp_m   = COMP_META.get(comp, {"label": comp.title(), "colour": "#7AACBF"})
    tier     = f.get("finding_tier", "P3")
    sev      = f.get("signal_severity", "P2")
    cac      = f.get("confidence_score", 0.0)
    ceiling  = f.get("designed_ceiling_reached", False)
    summary  = f.get("finding_summary", "") or "No summary available."
    keywords = f.get("top_3_keywords", [])
    blind    = f.get("blind_spots", [])
    chr_id   = (f.get("chronicle_match") or {}).get("chronicle_id")
    counts   = f.get("signal_counts", {})
    jid      = f.get("journey_id", "")
    journey  = JOURNEY_LABELS.get(jid, jid)
    fid      = f.get("finding_id", "—")
    countersign = f.get("human_countersign_status", "PENDING")

    tier_col = TIER_COLOURS.get(tier, "#4A7A8F")
    sev_col  = SEVERITY_COLOURS.get(sev, "#4A9BD4")

    # Ceiling badge
    ceiling_badge = (
        '<span style="background:#330000;color:#CC0000;font-size:9px;'
        'padding:2px 6px;border-radius:3px;letter-spacing:0.5px;'
        'margin-left:6px;">⚑ CEILING</span>'
        if ceiling else ""
    )

    # Chronicle badge
    chr_badge = (
        f'<span style="background:#001E30;color:#00AFA0;font-size:9px;'
        f'padding:2px 6px;border-radius:3px;letter-spacing:0.5px;'
        f'margin-left:6px;">{chr_id}</span>'
        if chr_id else ""
    )

    # Countersign badge
    cs_colour = "#00AFA0" if countersign == "COUNTERSIGNED" else "#3A6A7F"
    cs_bg     = "#001818" if countersign == "COUNTERSIGNED" else "#001428"
    cs_badge  = (
        f'<span style="background:{cs_bg};color:{cs_colour};font-size:9px;'
        f'padding:2px 6px;border-radius:3px;letter-spacing:0.5px;">'
        f'{countersign}</span>'
    )

    # Keywords
    kw_html = " ".join(
        f'<span style="background:#002030;color:#7AACBF;font-size:9px;'
        f'padding:2px 5px;border-radius:3px;">{k}</span>'
        for k in keywords
    )

    # Top blind spot (first non-ceiling one, or ceiling text)
    blind_text = ""
    for b in blind:
        if b and "Designed Ceiling" not in b:
            blind_text = b
            break
    if not blind_text and blind:
        blind_text = blind[0]

    cac_bar = _cac_bar_html(cac)

    return f"""
<div style="background:#001828;border:1px solid #003A5C;border-left:3px solid {tier_col};
            border-radius:8px;padding:14px 16px;margin-bottom:10px;">
  <!-- Header row -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
      <span style="font-family:'DM Mono',monospace;font-size:10px;color:#3A6A7F;">{fid}</span>
      <span style="background:#001E30;color:{comp_m['colour']};font-size:10px;
                   padding:2px 7px;border-radius:3px;font-weight:600;">
        {comp_m['label']}
      </span>
      <span style="background:#001E30;color:{tier_col};font-size:9px;
                   padding:2px 6px;border-radius:3px;letter-spacing:0.5px;">{tier}</span>
      <span style="background:#001E30;color:{sev_col};font-size:9px;
                   padding:2px 6px;border-radius:3px;letter-spacing:0.5px;">SIG {sev}</span>
      {ceiling_badge}{chr_badge}
    </div>
    {cs_badge}
  </div>

  <!-- Summary -->
  <div style="font-size:12px;color:#E8F4FA;line-height:1.5;margin-bottom:8px;">
    {summary}
  </div>

  <!-- CAC bar -->
  <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:2px;">
    CAC Confidence
  </div>
  {cac_bar}

  <!-- Meta row -->
  <div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap;">
    <div>
      <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;">Journey</div>
      <div style="font-size:11px;color:#7AACBF;">{journey or "—"}</div>
    </div>
    <div>
      <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;">Signals</div>
      <div style="font-family:'DM Mono',monospace;font-size:11px;color:#E8F4FA;">
        <span style="color:#CC0000;">P0:{counts.get('P0',0)}</span>
        <span style="color:#F5A623;margin-left:4px;">P1:{counts.get('P1',0)}</span>
        <span style="color:#4A9BD4;margin-left:4px;">P2:{counts.get('P2',0)}</span>
      </div>
    </div>
    {'<div><div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;">Blind Spot</div><div style="font-size:10px;color:#4A7A8F;font-style:italic;max-width:380px;">' + blind_text[:120] + ('…' if len(blind_text) > 120 else '') + '</div></div>' if blind_text else ''}
  </div>

  <!-- Keywords -->
  {'<div style="margin-top:8px;">' + kw_html + '</div>' if kw_html else ''}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit render function
# ─────────────────────────────────────────────────────────────────────────────

def render_inference_cards(
    competitor: Optional[str] = None,
    tier: Optional[str] = None,
    ceiling_only: bool = False,
    limit: int = 15,
) -> None:
    """
    Render inference cards with filter controls into the active Streamlit context.
    Replaces the placeholder 'Active Inferences' block in app.py.
    """
    try:
        import streamlit as st
    except ImportError:
        return

    summary = findings_summary()

    # ── Filter bar ────────────────────────────────────────────────────────────
    with st.container():
        fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
        with fc1:
            comp_opts = ["All"] + sorted(COMP_META.keys())
            comp_sel = st.selectbox(
                "Competitor", comp_opts, key="inf_comp_filter", label_visibility="collapsed"
            )
            competitor = None if comp_sel == "All" else comp_sel

        with fc2:
            tier_opts = ["All tiers", "P1", "P2", "P3"]
            tier_sel = st.selectbox(
                "Tier", tier_opts, key="inf_tier_filter", label_visibility="collapsed"
            )
            tier = None if tier_sel == "All tiers" else tier_sel

        with fc3:
            ceiling_toggle = st.checkbox(
                "Ceiling only", key="inf_ceiling_filter", value=False
            )

        with fc4:
            st.markdown(
                f'<div style="font-size:10px;color:#3A6A7F;line-height:1.4;padding-top:4px;">'
                f'{summary.get("total", 0)} findings &nbsp;|&nbsp; '
                f'<span style="color:#CC0000;">{summary.get("ceiling", 0)} ceiling</span> &nbsp;|&nbsp; '
                f'<span style="color:#00AFA0;">{summary.get("countersigned", 0)} countersigned</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Cards ─────────────────────────────────────────────────────────────────
    findings = load_findings(
        competitor=competitor,
        tier=tier,
        ceiling_only=ceiling_toggle,
        limit=limit,
    )

    if not findings:
        st.markdown(
            '<div style="font-size:11px;color:#3A6A7F;padding:12px 0;">No findings match the current filter.</div>',
            unsafe_allow_html=True,
        )
        return

    for f in findings:
        st.markdown(_finding_card_html(f), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    summary = findings_summary()
    print(f"Findings: {summary.get('total')} total | "
          f"{summary.get('ceiling')} ceiling | "
          f"{summary.get('p1_tier')} P1-tier | "
          f"{summary.get('countersigned')} countersigned")
    print()
    top = load_findings(limit=5)
    for f in top:
        print(f"  {f['finding_id']}  {f['competitor']:<10}  "
              f"CAC={f['confidence_score']:.3f}  "
              f"tier={f['finding_tier']}  "
              f"ceiling={'Y' if f.get('designed_ceiling_reached') else 'N'}  "
              f"| {f.get('finding_summary', '')[:60]}")
