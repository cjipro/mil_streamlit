"""
research_trigger.py — MIL Auto-Research Trigger (PULSE-2H)

Fires on P0/P1 findings with weak CHRONICLE anchor (sim_hist_score < threshold).
Writes research tasks to mil/data/research_queue.jsonl for overnight batch.

Trigger conditions (any one is sufficient):
  1. signal_severity P0 or P1 AND sim_hist_score < SIM_THRESHOLD (0.40)
  2. is_unanchored = True (finding has no CHRONICLE match at all)

Output per queue entry:
  finding_id, competitor, journey_id, signal_severity, top_3_keywords,
  sim_hist_score, chronicle_id (if partial), research_prompt, status, triggered_at

research_prompt — generated from signal keywords + journey + competitor context.
  Tells a future research agent or human analyst exactly what to search for.

Status lifecycle:
  PENDING  → assigned overnight batch
  ACTIVE   → research agent working
  RESOLVED → analyst found a source, added CHR entry or dismissed
  STALE    → finding rolled off (P0→P1 downgrade or finding expired)

Wired into run_daily.py as Step 3b (after inference, before vault).

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
Article Zero: trigger fires conservatively — better to flag too many than miss one.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MIL_ROOT       = Path(__file__).parent.parent
FINDINGS_FILE  = MIL_ROOT / "outputs" / "mil_findings.json"
QUEUE_FILE     = MIL_ROOT / "data" / "research_queue.jsonl"

# sim_hist_score below this = weak CHRONICLE anchor → trigger
SIM_THRESHOLD  = 0.40

# Only trigger on P0 and P1
TRIGGER_SEVERITIES = {"P0", "P1"}

# Source suggestions per signal keyword family — helps build research_prompt
_SOURCE_HINTS = {
    "login":     ["DownDetector", "App Store reviews", "Reddit r/UKPersonalFinance", "Twitter/X"],
    "payment":   ["DownDetector", "App Store reviews", "Google Play reviews", "FT/City AM"],
    "app":       ["App Store reviews", "Google Play reviews", "DownDetector"],
    "transfer":  ["App Store reviews", "Google Play reviews", "FT/City AM"],
    "access":    ["DownDetector", "App Store reviews", "Twitter/X"],
    "error":     ["DownDetector", "App Store reviews", "Reddit r/UKPersonalFinance"],
    "crash":     ["App Store reviews", "Google Play reviews", "DownDetector"],
    "balance":   ["App Store reviews", "Google Play reviews"],
    "account":   ["App Store reviews", "DownDetector", "Reddit r/UKPersonalFinance"],
    "support":   ["App Store reviews", "Google Play reviews", "Trustpilot"],
}

_JOURNEY_LABELS = {
    "J_LOGIN_01":   "Log In to Account",
    "J_PAY_01":     "Make a Payment",
    "J_TRANSFER_01":"Transfer Money",
    "J_SERVICE_01": "Account / Service Access",
    "J_BALANCE_01": "Check Balance or Statement",
    "J_CARD_01":    "Manage Card",
    "J_SUPPORT_01": "Get Support",
    "J_OPEN_01":    "Open or Register Account",
    "J_LOAN_01":    "Apply for Loan or Overdraft",
}


def _source_hints_for(keywords: list[str]) -> list[str]:
    """Return deduplicated source hints relevant to the given keywords."""
    seen, hints = set(), []
    for kw in keywords:
        for hint in _SOURCE_HINTS.get(kw.lower(), []):
            if hint not in seen:
                hints.append(hint)
                seen.add(hint)
    return hints or ["App Store reviews", "Google Play reviews", "DownDetector"]


def _build_research_prompt(finding: dict) -> str:
    """
    Construct a plain-language research prompt for the finding.
    Points a future agent or analyst at what to search for.
    """
    competitor  = finding.get("competitor", "unknown").capitalize()
    journey_id  = finding.get("journey_id", "unknown")
    journey     = _JOURNEY_LABELS.get(journey_id, journey_id)
    severity    = finding.get("signal_severity", "?")
    keywords    = finding.get("top_3_keywords", [])
    chr_id      = (finding.get("chronicle_match") or {}).get("chronicle_id")
    sim_score   = (finding.get("chronicle_match") or {}).get("sim_hist_score", 0.0)
    sources     = _source_hints_for(keywords)

    kw_str  = ", ".join(f'"{k}"' for k in keywords) if keywords else "(no keywords)"
    src_str = " | ".join(sources)

    anchor_note = (
        f"Partial CHRONICLE anchor: {chr_id} (sim={sim_score:.2f} — below threshold {SIM_THRESHOLD})."
        if chr_id else "No CHRONICLE anchor found."
    )

    return (
        f"{severity} signal on {competitor} journey '{journey}'. "
        f"{anchor_note} "
        f"Keywords: {kw_str}. "
        f"Search: {src_str}. "
        f"Goal: find a verified public incident, outage notice, or pattern that explains "
        f"this cluster. If found, propose a new CHRONICLE entry (CHR-NNN) for Hussain review."
    )


def _should_trigger(finding: dict) -> bool:
    """Return True if this finding should enter the research queue."""
    severity = finding.get("signal_severity", "P2")
    if severity not in TRIGGER_SEVERITIES:
        return False

    if finding.get("is_unanchored"):
        return True

    sim_score = (finding.get("chronicle_match") or {}).get("sim_hist_score", 0.0)
    return sim_score < SIM_THRESHOLD


def _load_existing_queue() -> set[str]:
    """Return set of finding_ids already in the queue (any status)."""
    if not QUEUE_FILE.exists():
        return set()
    ids = set()
    with QUEUE_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    ids.add(entry.get("finding_id", ""))
                except json.JSONDecodeError:
                    pass
    return ids


def run(findings_file: Path = FINDINGS_FILE, queue_file: Path = QUEUE_FILE) -> dict:
    """
    Scan findings, write triggered entries to research_queue.jsonl.

    Returns summary dict:
      triggered  — new entries written this run
      skipped    — already in queue
      ignored    — P2 or strong CHRONICLE anchor
    """
    if not findings_file.exists():
        logger.warning("Findings file not found: %s — skipping research trigger", findings_file)
        return {"triggered": 0, "skipped": 0, "ignored": 0}

    data = json.loads(findings_file.read_text(encoding="utf-8"))
    findings    = data.get("findings", [])
    unanchored  = data.get("unanchored_signals", [])
    all_findings = findings + unanchored

    if not all_findings:
        logger.info("No findings to evaluate for research trigger.")
        return {"triggered": 0, "skipped": 0, "ignored": 0}

    existing_ids = _load_existing_queue()
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    triggered = skipped = ignored = 0
    now = datetime.now(timezone.utc).isoformat()

    with queue_file.open("a", encoding="utf-8") as out:
        for finding in all_findings:
            fid = finding.get("finding_id", "")

            if not _should_trigger(finding):
                ignored += 1
                continue

            if fid in existing_ids:
                skipped += 1
                logger.debug("Already queued: %s", fid)
                continue

            entry = {
                "finding_id":      fid,
                "competitor":      finding.get("competitor", ""),
                "journey_id":      finding.get("journey_id", ""),
                "signal_severity": finding.get("signal_severity", ""),
                "top_3_keywords":  finding.get("top_3_keywords", []),
                "sim_hist_score":  (finding.get("chronicle_match") or {}).get("sim_hist_score", 0.0),
                "chronicle_id":    (finding.get("chronicle_match") or {}).get("chronicle_id"),
                "is_unanchored":   finding.get("is_unanchored", False),
                "cac_score":       finding.get("confidence_score", 0.0),
                "research_prompt": _build_research_prompt(finding),
                "status":          "PENDING",
                "triggered_at":    now,
                "resolved_at":     None,
                "resolution_note": None,
            }

            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            existing_ids.add(fid)
            triggered += 1
            logger.info(
                "RESEARCH_TRIGGER: %s — %s %s sim=%.2f%s",
                fid,
                finding.get("signal_severity"),
                finding.get("competitor", ""),
                (finding.get("chronicle_match") or {}).get("sim_hist_score", 0.0),
                " [UNANCHORED]" if finding.get("is_unanchored") else "",
            )

    logger.info(
        "Research trigger complete — triggered=%d skipped=%d ignored=%d",
        triggered, skipped, ignored,
    )
    return {"triggered": triggered, "skipped": skipped, "ignored": ignored}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    result = run()
    print(f"\nResearch queue update:")
    print(f"  Triggered: {result['triggered']} new entries")
    print(f"  Skipped:   {result['skipped']} already queued")
    print(f"  Ignored:   {result['ignored']} (P2 or strong anchor)")
    print(f"  Queue:     {QUEUE_FILE}")
