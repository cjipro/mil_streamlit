"""
exit_strategy.py — MIL-15 Exit Strategy Button component.

Designed Ceiling findings can't be confirmed with public data alone.
This component lets the analyst log "I need Phase 2 data for this finding"
— each click appends to mil/data/click_log.jsonl.

The click log is the demand evidence:
- Accumulates analyst-confirmed Phase 2 requests
- Shows which findings hit the ceiling most often
- Provides the business case for Phase 2 (internal telemetry integration)

Each log entry:
    {
        "ts":          "2026-04-05T07:45:00+00:00",
        "finding_id":  "MIL-F-20260405-057",
        "competitor":  "natwest",
        "cac_score":   0.720,
        "journey_id":  "J_AUTH_01",
        "finding_tier":"P1",
        "action":      "PHASE2_REQUEST"
    }

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIL_ROOT      = Path(__file__).parent.parent.parent
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"
CLICK_LOG     = MIL_ROOT / "data" / "click_log.jsonl"

COMP_LABELS = {
    "barclays": "Barclays",
    "natwest":  "NatWest",
    "lloyds":   "Lloyds",
    "monzo":    "Monzo",
    "revolut":  "Revolut",
    "hsbc":     "HSBC",
}

JOURNEY_LABELS = {
    "J_AUTH_01":     "Log In",
    "J_PAY_01":      "Make a Payment",
    "J_TRANSFER_01": "Transfer Money",
    "J_ACCOUNT_01":  "View Account",
    "J_CARD_01":     "Card Management",
    "J_SERVICE_01":  "General App Use",
    "J_ONBOARD_01":  "Onboarding",
    "J_SAVINGS_01":  "Savings",
    "J_INVEST_01":   "Investments",
}

TIER_COLOURS = {"P1": "#CC0000", "P2": "#F5A623", "P3": "#4A7A8F"}
COMP_COLOURS = {
    "barclays": "#00AEEF", "natwest": "#F5A623", "lloyds": "#00AFA0",
    "monzo": "#7B5EA7", "revolut": "#4A9BD4", "hsbc": "#CC3300",
}


# ─────────────────────────────────────────────────────────────────────────────
# Log I/O
# ─────────────────────────────────────────────────────────────────────────────

def log_phase2_request(
    finding_id: str,
    competitor: str,
    cac_score: float,
    journey_id: str,
    finding_tier: str,
) -> None:
    """Append one Phase 2 request to click_log.jsonl."""
    entry = {
        "ts":           datetime.now(timezone.utc).isoformat(),
        "finding_id":   finding_id,
        "competitor":   competitor,
        "cac_score":    round(cac_score, 4),
        "journey_id":   journey_id,
        "finding_tier": finding_tier,
        "action":       "PHASE2_REQUEST",
    }
    CLICK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLICK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    logger.info("[exit_strategy] Phase 2 request logged: %s (%s)", finding_id, competitor)


def load_click_log() -> list[dict]:
    """Load all click log entries. Returns [] if log doesn't exist yet."""
    if not CLICK_LOG.exists():
        return []
    entries = []
    with open(CLICK_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def click_log_summary() -> dict:
    """Aggregate demand stats from the click log."""
    entries = load_click_log()
    if not entries:
        return {"total": 0, "unique_findings": 0, "competitors": {}, "tiers": {}, "latest": None}

    from collections import Counter
    comp_counts = Counter(e["competitor"] for e in entries)
    tier_counts = Counter(e.get("finding_tier", "?") for e in entries)
    unique_findings = len({e["finding_id"] for e in entries})

    return {
        "total":           len(entries),
        "unique_findings": unique_findings,
        "competitors":     dict(comp_counts.most_common()),
        "tiers":           dict(tier_counts),
        "latest":          entries[-1]["ts"][:16].replace("T", " ") if entries else None,
    }


def already_requested(finding_id: str) -> bool:
    """True if this finding already has at least one Phase 2 request."""
    return any(e["finding_id"] == finding_id for e in load_click_log())


# ─────────────────────────────────────────────────────────────────────────────
# Load ceiling findings
# ─────────────────────────────────────────────────────────────────────────────

def load_ceiling_findings(limit: int = 20) -> list[dict]:
    """Return ceiling findings sorted by CAC desc."""
    if not FINDINGS_FILE.exists():
        return []
    try:
        payload = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
        findings = payload.get("findings", [])
    except Exception as exc:
        logger.error("[exit_strategy] failed to read findings: %s", exc)
        return []

    ceiling = [f for f in findings if f.get("designed_ceiling_reached")]
    ceiling.sort(key=lambda f: f.get("confidence_score", 0), reverse=True)
    return ceiling[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit render
# ─────────────────────────────────────────────────────────────────────────────

def render_exit_strategy_panel(limit: int = 20) -> None:
    """
    Render the Exit Strategy panel.

    Shows:
    1. Demand summary — total Phase 2 requests, unique findings, competitor breakdown
    2. Ceiling findings table — each row has a "Request Phase 2" button
       Button is disabled (greyed) if the finding has already been requested
    3. Click log — last 10 entries
    """
    try:
        import streamlit as st
    except ImportError:
        return

    ceiling_findings = load_ceiling_findings(limit=limit)
    summary = click_log_summary()

    # ── Header summary strip ─────────────────────────────────────────────────
    total    = summary.get("total", 0)
    unique   = summary.get("unique_findings", 0)
    latest   = summary.get("latest", "—")
    comp_str = "  ·  ".join(
        f"{COMP_LABELS.get(c, c)} ({n})"
        for c, n in summary.get("competitors", {}).items()
    ) or "None yet"

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        st.markdown(
            f'<div style="background:#001828;border:1px solid #003A5C;border-radius:8px;'
            f'padding:14px 16px;text-align:center;">'
            f'<div style="font-family:\'DM Mono\',monospace;font-size:28px;'
            f'font-weight:800;color:#00AEEF;">{total}</div>'
            f'<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
            f'letter-spacing:1px;margin-top:2px;">Phase 2 Requests</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f'<div style="background:#001828;border:1px solid #003A5C;border-radius:8px;'
            f'padding:14px 16px;text-align:center;">'
            f'<div style="font-family:\'DM Mono\',monospace;font-size:28px;'
            f'font-weight:800;color:#F5A623;">{unique}</div>'
            f'<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
            f'letter-spacing:1px;margin-top:2px;">Unique Findings</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown(
            f'<div style="background:#001828;border:1px solid #003A5C;border-radius:8px;'
            f'padding:14px 16px;">'
            f'<div style="font-size:10px;color:#3A6A7F;text-transform:uppercase;'
            f'letter-spacing:0.8px;margin-bottom:4px;">By Competitor</div>'
            f'<div style="font-size:11px;color:#7AACBF;">{comp_str}</div>'
            f'<div style="font-size:9px;color:#3A6A7F;margin-top:6px;">Last request: {latest}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    if not ceiling_findings:
        st.markdown(
            '<div style="font-size:11px;color:#3A6A7F;">No ceiling findings available.</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Ceiling findings rows ─────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
        'letter-spacing:0.8px;margin-bottom:8px;">'
        f'{len(ceiling_findings)} designed ceiling findings — click to request Phase 2 access'
        '</div>',
        unsafe_allow_html=True,
    )

    for f in ceiling_findings:
        fid      = f.get("finding_id", "—")
        comp     = f.get("competitor", "unknown")
        cac      = f.get("confidence_score", 0.0)
        tier     = f.get("finding_tier", "P3")
        jid      = f.get("journey_id", "")
        journey  = JOURNEY_LABELS.get(jid, jid)
        summary_text = (f.get("finding_summary") or "No summary.")[:80]
        comp_col = COMP_COLOURS.get(comp, "#7AACBF")
        tier_col = TIER_COLOURS.get(tier, "#4A7A8F")
        requested = already_requested(fid)

        row_left, row_right = st.columns([5, 1])
        with row_left:
            dot_colour = "#00AFA0" if requested else "#CC0000"
            st.markdown(
                f'<div style="background:#001828;border:1px solid #003A5C;'
                f'border-left:3px solid {tier_col};border-radius:6px;'
                f'padding:10px 14px;display:flex;align-items:center;gap:10px;">'
                f'<span style="width:7px;height:7px;border-radius:50%;'
                f'background:{dot_colour};display:inline-block;flex-shrink:0;"></span>'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:9px;'
                f'color:#3A6A7F;min-width:150px;">{fid}</span>'
                f'<span style="background:#001E30;color:{comp_col};font-size:9px;'
                f'padding:1px 6px;border-radius:3px;font-weight:600;">'
                f'{COMP_LABELS.get(comp, comp)}</span>'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:10px;'
                f'color:#F5A623;">{cac:.3f}</span>'
                f'<span style="font-size:10px;color:#7AACBF;flex:1;">{summary_text}</span>'
                f'<span style="font-size:9px;color:#3A6A7F;">{journey}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with row_right:
            if requested:
                st.markdown(
                    '<div style="background:#001818;border:1px solid #003A5C;'
                    'border-radius:6px;padding:10px 0;text-align:center;'
                    'font-size:9px;color:#00AFA0;letter-spacing:0.5px;">REQUESTED</div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button(
                    "Request P2",
                    key=f"p2_{fid}",
                    use_container_width=True,
                    type="primary",
                ):
                    log_phase2_request(
                        finding_id=fid,
                        competitor=comp,
                        cac_score=cac,
                        journey_id=jid,
                        finding_tier=tier,
                    )
                    st.rerun()

    # ── Recent click log ──────────────────────────────────────────────────────
    entries = load_click_log()
    if entries:
        st.markdown(
            '<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
            'letter-spacing:0.8px;margin-top:20px;margin-bottom:8px;">Recent Requests</div>',
            unsafe_allow_html=True,
        )
        for e in reversed(entries[-8:]):
            comp_col = COMP_COLOURS.get(e.get("competitor", ""), "#7AACBF")
            st.markdown(
                f'<div style="font-size:10px;color:#4A7A8F;padding:3px 0;'
                f'border-bottom:1px solid #002030;font-family:\'DM Mono\',monospace;">'
                f'<span style="color:#3A6A7F;">{e["ts"][:16].replace("T"," ")}</span>'
                f'&nbsp;&nbsp;{e["finding_id"]}'
                f'&nbsp;&nbsp;<span style="color:{comp_col};">'
                f'{COMP_LABELS.get(e["competitor"], e["competitor"])}</span>'
                f'&nbsp;&nbsp;CAC={e["cac_score"]:.3f}'
                f'&nbsp;&nbsp;<span style="color:#F5A623;">{e.get("finding_tier","?")}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ceiling = load_ceiling_findings(limit=5)
    print(f"Ceiling findings available: {len(load_ceiling_findings())}")
    print()
    summary = click_log_summary()
    print(f"Click log: {summary['total']} total requests | "
          f"{summary['unique_findings']} unique findings")
    print()
    print("Top ceiling findings (by CAC):")
    for f in ceiling:
        req = already_requested(f['finding_id'])
        print(f"  {f['finding_id']}  {f['competitor']:<10}  "
              f"CAC={f['confidence_score']:.3f}  "
              f"{'[REQUESTED]' if req else ''}")
