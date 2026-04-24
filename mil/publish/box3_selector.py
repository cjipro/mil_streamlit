"""
Box 3 issue selection and preamble rendering.

Picks the single issue that leads the Intelligence Brief, using a strict
lexicographic 6-key tiebreaker:

  1. Clark tier          CLARK-3 > CLARK-2 > CLARK-1 > CLARK-0
  2. Trend direction     REGRESSION > WATCH > STABLE > IMPROVING  (slope on gap_pp)
  3. Severity class      P0 > P1 > P2
  4. Days sustained      higher wins
  5. Severity-weighted gap_pp   higher wins
  6. Issue name          alphabetical (deterministic floor)

Key #1 (Clark tier) already composites severity/persistence/gap. The remaining
keys disambiguate when multiple issues sit at the same Clark tier.

Also exposes `build_preamble_html()` — the self-justifying 2-sentence block
that explains *why this issue* before THE SITUATION prose. Both V3 (f-string)
and V4 (Jinja) render the same HTML by calling this helper.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

MIL_DIR          = Path(__file__).resolve().parent.parent
PERSISTENCE_LOG  = MIL_DIR / "data" / "issue_persistence_log.jsonl"
FINDINGS_JSON    = MIL_DIR / "outputs" / "mil_findings.json"

CLARK_TIER_RANK  = {"CLARK-3": 3, "CLARK-2": 2, "CLARK-1": 1, "CLARK-0": 0}
TREND_RANK       = {"REGRESSION": 3, "WATCH": 2, "STABLE": 1, "IMPROVING": 0}
SEVERITY_RANK    = {"P0": 3, "P1": 2, "P2": 1}
SEVERITY_WEIGHTS = {"P0": 3.0, "P1": 2.0, "P2": 1.0}

TREND_WINDOW_DAYS = 7

CLARK_CALL_MAP = {
    "CLARK-3": "Escalate to product engineering today — this is not a watch brief.",
    "CLARK-2": "Escalate to product leadership this week; formal brief required.",
    "CLARK-1": "On the watch list. Daily monitoring. Escalate if P0 volume rises in 72 hours.",
    "CLARK-0": "Nominal. No escalation required.",
}

# Compact action-specificity — audience · cadence · artefact. Renders on the
# subordinate line of the Clark tier badge so action ownership is visible at a
# glance without a standalone "The Call" prose block.
CLARK_ACTION_DETAILS = {
    "CLARK-3": "engineering &middot; today &middot; action brief",
    "CLARK-2": "product leadership &middot; this week &middot; formal brief",
    "CLARK-1": "watch list &middot; daily &middot; escalate on P0 surge within 72h",
    "CLARK-0": "nominal &middot; no escalation required",
}


def _load_persistence_log() -> list[dict]:
    if not PERSISTENCE_LOG.exists():
        return []
    entries = []
    for line in PERSISTENCE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _load_findings() -> list[dict]:
    if not FINDINGS_JSON.exists():
        return []
    try:
        data = json.loads(FINDINGS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return data.get("findings", []) or []
    return data or []


def compute_issue_trend(issue_type: str,
                        today: str | None = None,
                        entries: list[dict] | None = None,
                        window_days: int = TREND_WINDOW_DAYS) -> str:
    """
    Classify a per-issue trend on gap_pp over the last `window_days`.

    Returns one of REGRESSION / WATCH / STABLE / IMPROVING.
    Falls back to STABLE when history is too thin to measure slope.
    """
    entries = entries if entries is not None else _load_persistence_log()
    today_str = today or date.today().isoformat()
    cutoff = (date.fromisoformat(today_str) - timedelta(days=window_days)).isoformat()

    history = [e for e in entries
               if e.get("issue_type") == issue_type and e.get("date", "") >= cutoff]
    history.sort(key=lambda e: e["date"])
    if len(history) < 2:
        return "STABLE"

    gap_start = float(history[0].get("gap_pp", 0.0))
    gap_end   = float(history[-1].get("gap_pp", 0.0))
    span_days = max(
        (date.fromisoformat(history[-1]["date"]) - date.fromisoformat(history[0]["date"])).days,
        1,
    )
    slope = (gap_end - gap_start) / span_days

    if slope >= 0.30:
        return "REGRESSION"
    if slope >= 0.05:
        return "WATCH"
    if slope <= -0.30:
        return "IMPROVING"
    return "STABLE"


def clark_tier_by_issue(clark_summary: dict,
                        findings: list[dict] | None = None) -> dict[str, str]:
    """
    Map Barclays issue_type -> highest active Clark tier.

    Joins clark_summary['active'] (by finding_id) against findings.json
    (dominant_issue_type per finding). Only Barclays findings are considered.
    """
    findings = findings if findings is not None else _load_findings()
    fid_to_issue = {
        f.get("finding_id"): (f.get("dominant_issue_type") or "")
        for f in findings
        if f.get("competitor") == "barclays"
    }

    tier_by_issue: dict[str, str] = {}
    for e in clark_summary.get("active", []):
        if e.get("competitor") != "barclays":
            continue
        issue = fid_to_issue.get(e.get("finding_id"), "")
        if not issue:
            continue
        tier = e.get("clark_tier", "CLARK-0")
        existing = tier_by_issue.get(issue, "CLARK-0")
        if CLARK_TIER_RANK.get(tier, 0) > CLARK_TIER_RANK.get(existing, 0):
            tier_by_issue[issue] = tier
    return tier_by_issue


def select_box3_issue(over_indexed: list[dict],
                      clark_summary: dict | None = None,
                      persistence_entries: list[dict] | None = None,
                      findings: list[dict] | None = None,
                      today: str | None = None) -> dict | None:
    """
    Apply the 6-key tiebreaker and return the single selected issue.

    Returns a dict that extends the over_indexed entry with two new fields:
      - clark_tier : str  (CLARK-0 if no active escalation)
      - trend      : str  (REGRESSION / WATCH / STABLE / IMPROVING)

    Returns None if `over_indexed` is empty.
    """
    if not over_indexed:
        return None

    if clark_summary is None:
        try:
            from mil.command.components.clark_protocol import active_clark_summary
            clark_summary = active_clark_summary()
        except Exception:
            clark_summary = {"active": []}

    tier_map = clark_tier_by_issue(clark_summary, findings=findings)
    entries = persistence_entries if persistence_entries is not None else _load_persistence_log()

    scored: list[tuple] = []
    for issue in over_indexed:
        name     = issue.get("issue_type", "")
        severity = issue.get("dominant_severity", "P2")
        days     = int(issue.get("days_active", 0) or 0)
        gap      = float(issue.get("gap_pp", 0.0) or 0.0)

        clark   = tier_map.get(name, "CLARK-0")
        trend   = compute_issue_trend(name, today=today, entries=entries)
        sev_gap = gap * SEVERITY_WEIGHTS.get(severity, 1.0)

        # All keys ascending; negate the "higher wins" ones so smaller tuple
        # lexicographic value = higher selection priority. Name ascending is
        # natural (alphabetical) so we leave it as-is.
        sort_key = (
            -CLARK_TIER_RANK.get(clark, 0),
            -TREND_RANK.get(trend, 1),
            -SEVERITY_RANK.get(severity, 1),
            -days,
            -sev_gap,
            name,
        )
        scored.append((sort_key, {**issue, "clark_tier": clark, "trend": trend}))

    scored.sort(key=lambda t: t[0])
    return scored[0][1]


def write_priority_artifact(selected: dict | None, path=None) -> None:
    """Persist the selected Box 3 issue as JSON for downstream consumers.

    Currently read by MIL-49 briefing_email.py to decide whether to fire
    the daily PDB email. Prior implementation parsed HTML and broke after
    the 2026-04-21 Box 3 overhaul. This decouples email firing from HTML
    structure: if select_box3_issue picks an issue, the email sees it; if
    it returns None (silent day), the artifact is `null` and the email
    silent-day guard triggers.

    Atomic write via tempfile + os.replace to avoid email reading a
    half-written file if the pipeline is interrupted mid-publish.
    """
    import json, os
    from pathlib import Path
    if path is None:
        path = Path(__file__).parent.parent / "data" / "box3_priority.json"
    else:
        path = Path(path)
    payload = None
    if selected:
        payload = {
            "issue_type":        selected.get("issue_type"),
            "dominant_severity": selected.get("dominant_severity"),
            "days_active":       selected.get("days_active"),
            "gap_pp":            selected.get("gap_pp"),
            "barclays_rate":     selected.get("barclays_rate"),
            "peer_avg_rate":     selected.get("peer_avg_rate"),
            "clark_tier":        selected.get("clark_tier"),
            "trend":             selected.get("trend"),
            "category":          selected.get("category"),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(payload, indent=2, ensure_ascii=False) if payload else "null"
    from mil.publish.adapters import write_text_lf
    write_text_lf(tmp, body)
    os.replace(tmp, path)


def _trend_phrase(trend: str, sev: str, days: int) -> str:
    if trend == "REGRESSION":
        return f"regressing {days}d" if days > 1 else "regressing"
    if trend == "WATCH":
        return f"sustained {days}d" if days > 1 else "active and drifting up"
    if trend == "IMPROVING":
        return "improving trajectory" + (f" over {days}d" if days > 2 else "")
    # STABLE — severity already appears immediately before this phrase in the
    # preamble, so we skip repeating it and lean on sustain duration instead.
    if days > 2:
        return f"sustained {days}d without inflection"
    return "stable"


def _justification_line(selected: dict, vol_7: int) -> str:
    sev   = selected.get("dominant_severity", "P1")
    gap   = float(selected.get("gap_pp", 0.0) or 0.0)
    days  = int(selected.get("days_active", 0) or 0)
    b_rt  = float(selected.get("barclays_rate", 0.0) or 0.0)
    p_rt  = float(selected.get("peer_avg_rate", 0.0) or 0.0)

    if vol_7 <= 10 and sev in ("P0", "P1"):
        return f"Volume is low by design: {sev} failures are rare until they aren't."
    if gap >= 5.0:
        return (f"Peers average {p_rt:.1f}%; Barclays is at {b_rt:.1f}% — "
                f"a {gap:+.1f}pp gap.")
    if days >= 10:
        return (f"Sustained {days}d of over-indexed signal reads structural, "
                f"not transient.")
    return (f"Peers average {p_rt:.1f}%; Barclays is at {b_rt:.1f}% — "
            f"a {gap:+.1f}pp gap.")


def build_preamble_html(selected: dict | None, vol_stats: dict | None) -> str:
    """
    Render the 2-sentence self-justifying preamble for Box 3.

    Returns an empty string when there's no selected issue (Box 3 falls back
    to the nominal template in that case — no preamble needed).
    """
    if not selected:
        return ""

    issue  = selected.get("issue_type", "")
    sev    = selected.get("dominant_severity", "P1")
    trend  = selected.get("trend", "STABLE")
    days   = int(selected.get("days_active", 0) or 0)

    vol_7   = int((vol_stats or {}).get("count_7d") or 0)
    total_7 = int((vol_stats or {}).get("total_7d") or 0)

    trend_ph = _trend_phrase(trend, sev, days)
    if vol_7 > 0 and total_7 > vol_7:
        vol_ph = f"cited in {vol_7} of {total_7} Barclays reviews"
    elif vol_7 > 0:
        vol_ph = f"cited in {vol_7} Barclays reviews"
    else:
        vol_ph = "signal active in the benchmark corpus"

    justification = _justification_line(selected, vol_7)

    return f"""
<div style="padding:10px 12px;background:#04131D;border:1px solid #003A5C;
            border-left:3px solid #F5A623;border-radius:3px;margin-bottom:14px;
            font-size:12px;color:#E8F4FA;line-height:1.55;">
  <div><strong style="color:#FFD580;">{issue}</strong> is this week's priority — {sev} severity, {trend_ph}, {vol_ph}.</div>
  <div style="color:#7AACBF;font-size:11px;margin-top:4px;">{justification}</div>
</div>"""
