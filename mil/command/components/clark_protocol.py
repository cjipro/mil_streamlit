"""
clark_protocol.py — MIL-14 Clark Protocol: P1 escalation + auto-downgrade.

The Clark Protocol is MIL's escalation ladder. When a finding crosses defined
thresholds it is assigned a Clark tier and logged to clark_log.jsonl.
Human is notified at CLARK-2 and above. CLARK-3 demands immediate review.

Clark Tiers:
    CLARK-0   No escalation — P3 tier or insufficient signal
    CLARK-1   Watch         — P2 tier, CAC >= 0.55, chronicle anchor confirmed
    CLARK-2   Escalate      — P1 tier, CAC >= 0.45
    CLARK-3   Act Now       — P1 tier, CAC >= 0.65, chronicle anchor + ceiling

Auto-downgrade:
    CLARK-2/3 findings older than 48h with no new supporting signals are
    downgraded one tier (CLARK-3 → CLARK-2, CLARK-2 → CLARK-1).
    Logged as CLARK_DOWNGRADE event. job_p1_downgrade in scheduler triggers this.

clark_log.jsonl schema:
    {
        "ts":          "2026-04-05T07:00:00+00:00",
        "event":       "CLARK_ESCALATION" | "CLARK_DOWNGRADE",
        "finding_id":  "MIL-F-...",
        "competitor":  "natwest",
        "clark_tier":  "CLARK-3",
        "cac_score":   0.720,
        "finding_tier":"P1",
        "reason":      "P1 tier + CAC 0.720 + CHR-001 + ceiling",
        "synthesis":   "(CLARK-3 only) Opus-generated escalation note: what/why/evidence/action"
    }

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIL_ROOT      = Path(__file__).parent.parent.parent
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"
CLARK_LOG     = MIL_ROOT / "data" / "clark_log.jsonl"

COMP_LABELS = {
    "barclays": "Barclays", "natwest": "NatWest", "lloyds": "Lloyds",
    "monzo": "Monzo", "revolut": "Revolut", "hsbc": "HSBC",
}
COMP_COLOURS = {
    "barclays": "#00AEEF", "natwest": "#F5A623", "lloyds": "#00AFA0",
    "monzo": "#7B5EA7", "revolut": "#4A9BD4", "hsbc": "#CC3300",
}
CLARK_COLOURS = {
    "CLARK-3": "#CC0000",
    "CLARK-2": "#F5A623",
    "CLARK-1": "#00AFA0",
    "CLARK-0": "#3A6A7F",
}
CLARK_LABELS = {
    "CLARK-3": "ACT NOW",
    "CLARK-2": "ESCALATE",
    "CLARK-1": "WATCH",
    "CLARK-0": "NOMINAL",
}

# Thresholds — not tuned before Day 30
CLARK3_CAC_THRESHOLD  = 0.65
CLARK2_CAC_THRESHOLD  = 0.45
CLARK1_CAC_THRESHOLD  = 0.55
DOWNGRADE_HOURS       = 48

# P0 override: bypass CAC threshold when raw signal severity is extreme.
# P0 ≥ this count + Designed Ceiling + Chronicle anchor → CLARK-3 regardless of CAC.
# Rationale: Vol_sig dilution against large source pools can suppress CAC below CLARK-3
# even when the cluster is entirely blocking-severity (P0) signals.
CLARK3_P0_OVERRIDE    = 5


# ─────────────────────────────────────────────────────────────────────────────
# Tier evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_clark_tier(finding: dict) -> tuple[str, str]:
    """
    Evaluate the Clark tier for a finding.

    Returns:
        (tier, reason) — e.g. ("CLARK-3", "P1 + CAC 0.720 + CHR-001 + ceiling")
    """
    cac      = finding.get("confidence_score", 0.0)
    ftier    = finding.get("finding_tier", "P3")
    ceiling  = finding.get("designed_ceiling_reached", False)
    chr_match = finding.get("chronicle_match") or {}
    chr_id   = chr_match.get("chronicle_id")
    has_chr  = bool(chr_id and chr_match.get("inference_approved", True))

    # CLARK-3 (P0 override): raw blocking signals bypass CAC dilution
    # P0 ≥ 5 + Designed Ceiling + Chronicle anchor → ACT NOW regardless of CAC score
    p0_count = finding.get("signal_counts", {}).get("P0", 0)
    if p0_count >= CLARK3_P0_OVERRIDE and ceiling and has_chr:
        reason = (
            f"P0 override: {p0_count} blocking signals >= {CLARK3_P0_OVERRIDE} "
            f"+ ceiling + {chr_id}"
        )
        return "CLARK-3", reason

    # CLARK-3: P1 tier + high CAC + chronicle + ceiling
    if ftier == "P1" and cac >= CLARK3_CAC_THRESHOLD and has_chr and ceiling:
        reason = f"P1 tier + CAC {cac:.3f} >= {CLARK3_CAC_THRESHOLD} + {chr_id} + ceiling"
        return "CLARK-3", reason

    # CLARK-2: P1 tier + threshold CAC
    if ftier == "P1" and cac >= CLARK2_CAC_THRESHOLD:
        reason = f"P1 tier + CAC {cac:.3f} >= {CLARK2_CAC_THRESHOLD}"
        return "CLARK-2", reason

    # CLARK-1: P2 tier + high CAC + chronicle anchor
    if ftier == "P2" and cac >= CLARK1_CAC_THRESHOLD and has_chr:
        reason = f"P2 tier + CAC {cac:.3f} >= {CLARK1_CAC_THRESHOLD} + {chr_id}"
        return "CLARK-1", reason

    return "CLARK-0", "below escalation threshold"


# ─────────────────────────────────────────────────────────────────────────────
# Log I/O
# ─────────────────────────────────────────────────────────────────────────────

def _append_log(entry: dict) -> None:
    CLARK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLARK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_clark_log() -> list[dict]:
    if not CLARK_LOG.exists():
        return []
    entries = []
    with open(CLARK_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def _already_logged(finding_id: str, tier: str) -> bool:
    """True if this finding+tier combo is already in the log."""
    return any(
        e["finding_id"] == finding_id and e["clark_tier"] == tier
        for e in load_clark_log()
        if e.get("event") == "CLARK_ESCALATION"
    )


def _opus_synthesis(finding: dict, reason: str) -> str:
    """
    Call Opus to generate a structured CLARK-3 escalation note.
    Returns prose string (empty on failure). ARCH-003 Tier 1.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        import anthropic

        # get_model via relative import path (works when called from MIL context)
        try:
            sys.path.insert(0, str(MIL_ROOT))
            from config.get_model import get_model
        except ImportError:
            from mil.config.get_model import get_model

        cfg    = get_model("clark_escalation_synthesis")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return ""

        client = anthropic.Anthropic(api_key=api_key)
        fid       = finding.get("finding_id", "?")
        comp      = COMP_LABELS.get(finding.get("competitor", ""), finding.get("competitor", "?"))
        cac       = finding.get("confidence_score", 0.0)
        summary   = (finding.get("finding_summary") or "")[:300]
        keywords  = finding.get("top_3_keywords", [])
        chr_id    = (finding.get("chronicle_match") or {}).get("chronicle_id", "none")
        journey   = finding.get("journey_id", "?")
        counts    = finding.get("signal_counts", {})
        ceil_flag = finding.get("designed_ceiling_reached", False)

        prompt = f"""You are MIL's escalation intelligence system. A CLARK-3 (ACT NOW) finding has triggered.

Write a structured escalation note — exactly 4 short sentences covering:
1. WHAT: the specific customer-facing failure and which competitor
2. WHY NOW: what crossed the CLARK-3 threshold (Chronicle anchor, ceiling, CAC score)
3. EVIDENCE: the volume and severity of signals observed
4. RECOMMENDED ACTION: one specific action for the product director to take in the next 24h

CLARK-3 FINDING:
- ID: {fid}
- Competitor: {comp}
- CAC score: {cac:.3f}
- Reason: {reason}
- Chronicle anchor: {chr_id}
- Designed ceiling reached: {ceil_flag}
- Signal counts: P0={counts.get('P0',0)}, P1={counts.get('P1',0)}, P2={counts.get('P2',0)}
- Top keywords: {', '.join(keywords)}
- Journey: {journey}
- Summary: {summary}

4 sentences only. Start with the competitor name."""

        msg = client.messages.create(
            model=cfg["model"],
            max_tokens=cfg.get("max_tokens", 1024),
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.warning("[clark] Opus synthesis failed (non-fatal): %s", exc)
        return ""


def log_escalation(finding: dict, tier: str, reason: str) -> None:
    synthesis_note = ""
    if tier == "CLARK-3":
        synthesis_note = _opus_synthesis(finding, reason)

    entry = {
        "ts":           datetime.now(timezone.utc).isoformat(),
        "event":        "CLARK_ESCALATION",
        "finding_id":   finding.get("finding_id", "?"),
        "competitor":   finding.get("competitor", "?"),
        "clark_tier":   tier,
        "cac_score":    round(finding.get("confidence_score", 0.0), 4),
        "finding_tier": finding.get("finding_tier", "?"),
        "reason":       reason,
    }
    if synthesis_note:
        entry["synthesis"] = synthesis_note

    _append_log(entry)
    logger.info("[clark] ESCALATION %s -> %s (%s)", entry["finding_id"], tier, reason)
    if synthesis_note:
        logger.info("[clark] CLARK-3 Opus synthesis generated for %s", entry["finding_id"])


def log_downgrade(finding_id: str, from_tier: str, to_tier: str, reason: str) -> None:
    entry = {
        "ts":         datetime.now(timezone.utc).isoformat(),
        "event":      "CLARK_DOWNGRADE",
        "finding_id": finding_id,
        "clark_tier": to_tier,
        "from_tier":  from_tier,
        "reason":     reason,
    }
    _append_log(entry)
    logger.info("[clark] DOWNGRADE %s: %s → %s", finding_id, from_tier, to_tier)


# ─────────────────────────────────────────────────────────────────────────────
# Scan + escalate (called by scheduler job)
# ─────────────────────────────────────────────────────────────────────────────

def scan_and_escalate() -> dict:
    """
    Scan all findings, evaluate Clark tier, log new escalations (deduplicated).
    Returns summary: {tier: count_of_new_escalations}.
    """
    if not FINDINGS_FILE.exists():
        logger.warning("[clark] findings file not found")
        return {}

    try:
        data     = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
        findings = data.get("findings", [])
    except Exception as exc:
        logger.error("[clark] failed to read findings: %s", exc)
        return {}

    new_counts: dict[str, int] = {}
    for finding in findings:
        tier, reason = evaluate_clark_tier(finding)
        if tier == "CLARK-0":
            continue
        fid = finding.get("finding_id", "?")
        if _already_logged(fid, tier):
            continue
        log_escalation(finding, tier, reason)
        new_counts[tier] = new_counts.get(tier, 0) + 1

    total_new = sum(new_counts.values())
    if total_new:
        logger.info("[clark] %d new escalations: %s", total_new, new_counts)
    else:
        logger.info("[clark] no new escalations")

    return new_counts


def scan_and_downgrade() -> int:
    """
    Auto-downgrade CLARK-2/3 escalations older than 48h.
    CLARK-3 → CLARK-2, CLARK-2 → CLARK-1.
    Returns count of downgraded entries.
    """
    entries   = load_clark_log()
    now       = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=DOWNGRADE_HOURS)
    downgraded = 0

    escalations = [
        e for e in entries
        if e.get("event") == "CLARK_ESCALATION"
        and e.get("clark_tier") in ("CLARK-2", "CLARK-3")
    ]

    for e in escalations:
        try:
            ts = datetime.fromisoformat(e["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue

        if ts >= threshold:
            continue  # still fresh

        fid       = e["finding_id"]
        from_tier = e["clark_tier"]
        to_tier   = "CLARK-2" if from_tier == "CLARK-3" else "CLARK-1"

        # Only downgrade once per finding per cycle
        already_downgraded = any(
            d["finding_id"] == fid and d.get("event") == "CLARK_DOWNGRADE"
            and d.get("from_tier") == from_tier
            for d in entries
        )
        if already_downgraded:
            continue

        log_downgrade(fid, from_tier, to_tier, f"{DOWNGRADE_HOURS}h elapsed — no new signals")
        downgraded += 1

    return downgraded


# ─────────────────────────────────────────────────────────────────────────────
# Summary helpers
# ─────────────────────────────────────────────────────────────────────────────

def active_clark_summary() -> dict:
    """
    Return the current highest Clark tier per finding (post-downgrade).
    Used by briefing_data.py and the Clark panel.
    """
    entries   = load_clark_log()
    per_finding: dict[str, dict] = {}

    for e in entries:
        fid = e.get("finding_id", "?")
        if fid not in per_finding:
            per_finding[fid] = e
        else:
            # Keep the most recent event
            try:
                existing_ts = datetime.fromisoformat(per_finding[fid]["ts"])
                this_ts     = datetime.fromisoformat(e["ts"])
                if this_ts > existing_ts:
                    per_finding[fid] = e
            except (ValueError, KeyError):
                pass

    active = {
        fid: e for fid, e in per_finding.items()
        if e.get("clark_tier", "CLARK-0") not in ("CLARK-0",)
    }
    by_tier = {}
    for e in active.values():
        t = e.get("clark_tier", "CLARK-0")
        by_tier[t] = by_tier.get(t, 0) + 1

    top_tier = "CLARK-0"
    for t in ("CLARK-3", "CLARK-2", "CLARK-1"):
        if by_tier.get(t, 0) > 0:
            top_tier = t
            break

    return {
        "top_tier":      top_tier,
        "by_tier":       by_tier,
        "active_count":  len(active),
        "active":        list(active.values()),
    }


def get_clark_tier_for_finding(finding_id: str) -> str:
    """Return current Clark tier for one finding. CLARK-0 if not escalated."""
    summary = active_clark_summary()
    for e in summary.get("active", []):
        if e.get("finding_id") == finding_id:
            return e.get("clark_tier", "CLARK-0")
    return "CLARK-0"


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit render
# ─────────────────────────────────────────────────────────────────────────────

def render_clark_panel() -> None:
    """Render the Clark Protocol panel in the active Streamlit context."""
    try:
        import streamlit as st
    except ImportError:
        return

    summary = active_clark_summary()
    top     = summary.get("top_tier", "CLARK-0")
    by_tier = summary.get("by_tier", {})
    active  = summary.get("active", [])
    log     = load_clark_log()

    top_colour = CLARK_COLOURS.get(top, "#3A6A7F")
    top_label  = CLARK_LABELS.get(top, "NOMINAL")

    # ── Status strip ─────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    for col, tier in zip([c1, c2, c3, c4], ["CLARK-3", "CLARK-2", "CLARK-1", "CLARK-0"]):
        count  = by_tier.get(tier, 0)
        colour = CLARK_COLOURS[tier]
        label  = CLARK_LABELS[tier]
        with col:
            st.markdown(
                f'<div style="background:#001828;border:1px solid #003A5C;'
                f'border-top:3px solid {colour};border-radius:8px;'
                f'padding:12px 14px;text-align:center;">'
                f'<div style="font-family:\'DM Mono\',monospace;font-size:24px;'
                f'font-weight:800;color:{colour};">{count}</div>'
                f'<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
                f'letter-spacing:1px;margin-top:2px;">{tier}</div>'
                f'<div style="font-size:8px;color:#4A7A8F;margin-top:1px;">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    if not active:
        st.markdown(
            f'<div style="font-size:11px;color:#3A6A7F;">'
            f'No active Clark escalations. Run the scanner or trigger the scheduler job.'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        # ── Active escalation rows ────────────────────────────────────────────
        st.markdown(
            f'<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
            f'letter-spacing:0.8px;margin-bottom:8px;">'
            f'{len(active)} active escalations — sorted by tier</div>',
            unsafe_allow_html=True,
        )
        tier_order = {"CLARK-3": 0, "CLARK-2": 1, "CLARK-1": 2, "CLARK-0": 3}
        for e in sorted(active, key=lambda x: tier_order.get(x.get("clark_tier", "CLARK-0"), 3)):
            fid      = e.get("finding_id", "—")
            comp     = e.get("competitor", "unknown")
            ctier    = e.get("clark_tier", "CLARK-0")
            cac      = e.get("cac_score", 0.0)
            reason   = e.get("reason", "")
            ts       = e.get("ts", "")[:16].replace("T", " ")
            colour   = CLARK_COLOURS.get(ctier, "#3A6A7F")
            comp_col = COMP_COLOURS.get(comp, "#7AACBF")
            label    = CLARK_LABELS.get(ctier, "?")

            st.markdown(
                f'<div style="background:#001828;border:1px solid #003A5C;'
                f'border-left:3px solid {colour};border-radius:6px;'
                f'padding:10px 14px;margin-bottom:6px;'
                f'display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
                f'<span style="background:#001428;color:{colour};font-size:9px;'
                f'padding:2px 7px;border-radius:3px;font-weight:700;'
                f'letter-spacing:0.5px;min-width:68px;text-align:center;">'
                f'{ctier} {label}</span>'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:9px;'
                f'color:#3A6A7F;min-width:155px;">{fid}</span>'
                f'<span style="background:#001E30;color:{comp_col};font-size:9px;'
                f'padding:1px 6px;border-radius:3px;font-weight:600;">'
                f'{COMP_LABELS.get(comp, comp)}</span>'
                f'<span style="font-family:\'DM Mono\',monospace;font-size:10px;'
                f'color:#F5A623;">CAC {cac:.3f}</span>'
                f'<span style="font-size:10px;color:#4A7A8F;flex:1;">{reason}</span>'
                f'<span style="font-size:9px;color:#3A6A7F;">{ts}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Scan button ───────────────────────────────────────────────────────────
    if st.button("Run Clark Scan Now", key="clark_scan_btn", use_container_width=False):
        new = scan_and_escalate()
        dg  = scan_and_downgrade()
        total_new = sum(new.values())
        if total_new or dg:
            st.success(f"{total_new} new escalations | {dg} downgraded")
        else:
            st.info("No new escalations. All findings at or below threshold.")
        st.rerun()

    # ── Recent log ───────────────────────────────────────────────────────────
    if log:
        st.markdown(
            '<div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;'
            'letter-spacing:0.8px;margin-top:18px;margin-bottom:6px;">Clark Log</div>',
            unsafe_allow_html=True,
        )
        for e in reversed(log[-10:]):
            event    = e.get("event", "?")
            ctier    = e.get("clark_tier", "?")
            colour   = CLARK_COLOURS.get(ctier, "#3A6A7F")
            ts       = e.get("ts", "")[:16].replace("T", " ")
            fid      = e.get("finding_id", "—")
            comp     = COMP_LABELS.get(e.get("competitor", ""), e.get("competitor", ""))
            comp_col = COMP_COLOURS.get(e.get("competitor", ""), "#7AACBF")
            cac      = e.get("cac_score", "")
            cac_str  = f"CAC={cac:.3f}" if isinstance(cac, float) else ""
            from_t   = f'{e.get("from_tier","")} → ' if e.get("from_tier") else ""
            st.markdown(
                f'<div style="font-size:10px;color:#4A7A8F;padding:3px 0;'
                f'border-bottom:1px solid #002030;font-family:\'DM Mono\',monospace;">'
                f'<span style="color:#3A6A7F;">{ts}</span>&nbsp;&nbsp;'
                f'<span style="color:{colour};">{from_t}{ctier}</span>&nbsp;&nbsp;'
                f'{fid}&nbsp;&nbsp;'
                f'<span style="color:{comp_col};">{comp}</span>&nbsp;&nbsp;'
                f'{cac_str}&nbsp;&nbsp;'
                f'<span style="color:#4A9BD4;">{event}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Clark Protocol — scan_and_escalate()\n")
    new = scan_and_escalate()
    dg  = scan_and_downgrade()
    print(f"\nNew escalations: {sum(new.values())} {new}")
    print(f"Downgraded:      {dg}")
    print()
    s = active_clark_summary()
    print(f"Active summary — top tier: {s['top_tier']} | active: {s['active_count']}")
    print(f"By tier: {s['by_tier']}")
    print()
    for e in s["active"]:
        print(f"  {e['clark_tier']}  {e['finding_id']}  {e['competitor']}  "
              f"CAC={e.get('cac_score', '?')}  {e.get('reason', '')}")
