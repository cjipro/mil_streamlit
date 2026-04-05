"""
scheduler.py — MIL APScheduler (PULSE-2I)

Runs background jobs that keep the pipeline live between manual runs.

Schedule:
  06:00 UTC  Morning Briefing     — full run_daily pipeline (fetch → enrich → infer → vault → publish)
  11:00 UTC  P1 Auto-Downgrade    — ages P1 findings older than 48h to P2 if no new signals
  Every 6h   Rating Velocity      — re-runs rating_velocity_monitor against latest enriched files
  23:00 UTC  Research Queue Batch — processes PENDING entries in research_queue.jsonl (overnight)

Non-fatal design: each job catches its own exceptions and logs — scheduler never stops on job failure.

Usage:
  py mil/scheduler.py                 # run continuously (blocking)
  py mil/scheduler.py --once <job>    # run one job immediately and exit
      jobs: morning_briefing | p1_downgrade | rating_velocity | research_batch

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("mil.scheduler")

MIL_ROOT      = Path(__file__).parent
REPO_ROOT     = MIL_ROOT.parent
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"
QUEUE_FILE    = MIL_ROOT / "data" / "research_queue.jsonl"
CLICK_LOG     = MIL_ROOT / "data" / "click_log.jsonl"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(MIL_ROOT))


# ---------------------------------------------------------------------------
# Job: Morning Briefing — full daily pipeline
# ---------------------------------------------------------------------------

def job_morning_briefing():
    """Full run_daily pipeline: fetch → enrich → infer → trigger → vault → publish."""
    logger.info("[morning_briefing] starting full pipeline run")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "run_daily.py")],
            cwd=str(REPO_ROOT),
            capture_output=False,
            timeout=600,
        )
        if result.returncode != 0:
            logger.warning("[morning_briefing] run_daily.py exited %d", result.returncode)
        else:
            logger.info("[morning_briefing] complete")
    except Exception as exc:
        logger.error("[morning_briefing] FAILED: %s", exc)


# ---------------------------------------------------------------------------
# Job: P1 Auto-Downgrade — age P1 findings older than 48h to P2
# ---------------------------------------------------------------------------

def job_p1_downgrade():
    """
    Scan findings for P1 entries with no new supporting signals in 48h.
    Downgrades signal_severity P1 → P2 and logs the downgrade.
    """
    logger.info("[p1_downgrade] scanning for stale P1 findings")
    if not FINDINGS_FILE.exists():
        logger.warning("[p1_downgrade] findings file not found — skipping")
        return

    try:
        data      = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
        findings  = data.get("findings", [])
        now       = datetime.now(timezone.utc)
        threshold = now - timedelta(hours=48)
        downgraded = 0

        for finding in findings:
            if finding.get("signal_severity") != "P1":
                continue
            gen_str = finding.get("generated_at", "")
            try:
                gen_at = datetime.fromisoformat(gen_str)
                if gen_at.tzinfo is None:
                    gen_at = gen_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if gen_at < threshold:
                finding["signal_severity"]   = "P2"
                finding["downgraded_at"]      = now.isoformat()
                finding["downgrade_reason"]   = "P1_AUTO_DOWNGRADE_48H — no new supporting signals"
                downgraded += 1
                logger.info(
                    "[p1_downgrade] %s → P2 (age: %s)",
                    finding.get("finding_id", "?"),
                    gen_at.strftime("%Y-%m-%d %H:%M UTC"),
                )

        if downgraded:
            data["findings"] = findings
            FINDINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("[p1_downgrade] %d P1 findings downgraded to P2", downgraded)
        else:
            logger.info("[p1_downgrade] no stale P1 findings — nothing to downgrade")

    except Exception as exc:
        logger.error("[p1_downgrade] FAILED: %s", exc)


# ---------------------------------------------------------------------------
# Job: Clark Escalation — scan findings, log new escalations + downgrade stale
# ---------------------------------------------------------------------------

def job_clark_escalation():
    """
    Clark Protocol scan: evaluate all findings, log new CLARK-1/2/3 escalations.
    Then auto-downgrade CLARK-2/3 older than 48h by one tier.
    Runs after morning_briefing so fresh inference is available.
    """
    logger.info("[clark_escalation] scanning findings")
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from mil.command.components.clark_protocol import scan_and_escalate, scan_and_downgrade
        new    = scan_and_escalate()
        dg     = scan_and_downgrade()
        total  = sum(new.values())
        logger.info("[clark_escalation] %d new escalations %s | %d downgraded", total, new, dg)
    except Exception as exc:
        logger.error("[clark_escalation] FAILED: %s", exc)


# ---------------------------------------------------------------------------
# Job: Rating Velocity — re-scan latest enriched files
# ---------------------------------------------------------------------------

def job_rating_velocity():
    """Re-run rating_velocity_monitor against all enriched files."""
    logger.info("[rating_velocity] running velocity scan")
    try:
        from harvester.rating_velocity_monitor import RatingVelocityMonitor
        enriched_dir = MIL_ROOT / "data" / "historical" / "enriched"
        enriched_files = list(enriched_dir.glob("*_enriched.json"))

        if not enriched_files:
            logger.warning("[rating_velocity] no enriched files found")
            return

        monitor   = RatingVelocityMonitor()
        alerts    = []
        for path in enriched_files:
            try:
                records = json.loads(path.read_text(encoding="utf-8"))
                result  = monitor.scan(records, source_label=path.stem)
                if result.get("alerts"):
                    alerts.extend(result["alerts"])
                    logger.warning(
                        "[rating_velocity] %s — %d alerts: %s",
                        path.stem,
                        len(result["alerts"]),
                        [a.get("alert_type") for a in result["alerts"]],
                    )
            except Exception as exc:
                logger.warning("[rating_velocity] %s failed: %s", path.stem, exc)

        logger.info("[rating_velocity] complete — %d total alerts across %d files", len(alerts), len(enriched_files))

    except Exception as exc:
        logger.error("[rating_velocity] FAILED: %s", exc)


# ---------------------------------------------------------------------------
# Job: Research Queue Batch — process PENDING research tasks overnight
# ---------------------------------------------------------------------------

def job_research_batch():
    """
    Process PENDING entries in research_queue.jsonl.
    Current behaviour: logs each pending entry with its research_prompt.
    Future: wire to web search agent or Sonnet research loop.
    """
    logger.info("[research_batch] processing PENDING research queue entries")
    if not QUEUE_FILE.exists():
        logger.info("[research_batch] queue file not found — nothing to do")
        return

    try:
        pending = []
        lines   = QUEUE_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("status") == "PENDING":
                    pending.append(entry)
            except json.JSONDecodeError:
                pass

        if not pending:
            logger.info("[research_batch] no PENDING entries — queue clear")
            return

        logger.info("[research_batch] %d PENDING entries:", len(pending))
        for entry in pending:
            logger.info(
                "  [%s] %s %s — %s",
                entry.get("finding_id", "?"),
                entry.get("signal_severity", "?"),
                entry.get("competitor", "?"),
                entry.get("research_prompt", "")[:120],
            )

        logger.info(
            "[research_batch] complete — %d items logged for human/agent research",
            len(pending),
        )

    except Exception as exc:
        logger.error("[research_batch] FAILED: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

JOBS = {
    "morning_briefing":  job_morning_briefing,
    "p1_downgrade":      job_p1_downgrade,
    "clark_escalation":  job_clark_escalation,
    "rating_velocity":   job_rating_velocity,
    "research_batch":    job_research_batch,
}


def build_scheduler():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        raise ImportError("apscheduler not installed. Run: pip install apscheduler")

    scheduler = BlockingScheduler(timezone="UTC")

    # Morning Briefing — 06:00 UTC daily
    scheduler.add_job(
        job_morning_briefing,
        CronTrigger(hour=6, minute=0),
        id="morning_briefing",
        name="Morning Briefing — full pipeline",
        misfire_grace_time=300,
    )

    # P1 Auto-Downgrade — 11:00 UTC daily
    scheduler.add_job(
        job_p1_downgrade,
        CronTrigger(hour=11, minute=0),
        id="p1_downgrade",
        name="P1 Auto-Downgrade 48h",
        misfire_grace_time=300,
    )

    # Clark Escalation — 06:30 UTC daily (30 min after morning briefing)
    scheduler.add_job(
        job_clark_escalation,
        CronTrigger(hour=6, minute=30),
        id="clark_escalation",
        name="Clark Protocol — escalation scan",
        misfire_grace_time=300,
    )

    # Rating Velocity — every 6 hours
    scheduler.add_job(
        job_rating_velocity,
        CronTrigger(hour="0,6,12,18", minute=15),
        id="rating_velocity",
        name="Rating Velocity Monitor",
        misfire_grace_time=120,
    )

    # Research Queue Batch — 23:00 UTC daily
    scheduler.add_job(
        job_research_batch,
        CronTrigger(hour=23, minute=0),
        id="research_batch",
        name="Research Queue Batch — overnight",
        misfire_grace_time=600,
    )

    return scheduler


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(description="MIL Scheduler")
    parser.add_argument(
        "--once",
        metavar="JOB",
        choices=list(JOBS.keys()),
        help=f"Run one job immediately and exit. Choices: {', '.join(JOBS.keys())}",
    )
    args = parser.parse_args()

    if args.once:
        logger.info("Running job '%s' once and exiting", args.once)
        JOBS[args.once]()
        logger.info("Done.")
        return

    scheduler = build_scheduler()

    logger.info("=" * 60)
    logger.info("MIL Scheduler starting")
    logger.info("  06:00 UTC  morning_briefing   — full pipeline")
    logger.info("  06:30 UTC  clark_escalation  — Clark Protocol scan")
    logger.info("  11:00 UTC  p1_downgrade      — age P1 -> P2 after 48h")
    logger.info("  0/6/12/18h rating_velocity   — velocity scan")
    logger.info("  23:00 UTC  research_batch    — overnight queue log")
    logger.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
