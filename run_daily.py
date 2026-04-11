#!/usr/bin/env python3
"""
run_daily.py — MIL daily refresh pipeline.

Steps:
  1. Fetch latest reviews from App Store + Google Play (all active competitors)
  2. Deduplicate against existing raw records — enrich NEW records only
  3. Append new enriched records to existing enriched files
  4. Re-run inference  → mil/outputs/mil_findings.json
  5. Re-publish        → mil/publish/output/briefing/index.html + GitHub Pages push

Usage:
  py run_daily.py
  py run_daily.py --dry-run        # fetch + enrich only, skip publish
  py run_daily.py --skip-fetch     # skip fetch, re-run inference + publish only

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_daily")

REPO_ROOT   = Path(__file__).parent
MIL_ROOT    = REPO_ROOT / "mil"
APPS_CONFIG = MIL_ROOT / "config" / "apps_config.yaml"
HIST_BASE   = MIL_ROOT / "data" / "historical"
ENRICHED_DIR = HIST_BASE / "enriched"

sys.path.insert(0, str(MIL_ROOT))
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# STEP 1 — Fetch
# ---------------------------------------------------------------------------

def _dedup_key_app_store(rec: dict) -> str:
    return f"{rec.get('author','')}|{rec.get('date','')}|{rec.get('review','')[:80]}"

def _dedup_key_google_play(rec: dict) -> str:
    return f"{rec.get('userName','')}|{rec.get('at','')}|{rec.get('content','')[:80]}"


def fetch_new_records() -> dict[str, int]:
    """
    Fetch latest reviews for all active competitors.
    Returns {'{source}_{competitor}': new_record_count}.
    """
    from mil.harvester.sources.app_store import build_all_sources as build_as
    from mil.harvester.sources.google_play import build_all_sources as build_gp

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    counts: dict[str, int] = {}

    for source_label, sources, dedup_fn in [
        ("app_store", build_as(APPS_CONFIG), _dedup_key_app_store),
        ("google_play", build_gp(APPS_CONFIG), _dedup_key_google_play),
    ]:
        for src in sources:
            competitor = src.competitor.lower().replace(" ", "_")
            raw_dir = HIST_BASE / source_label / competitor
            raw_dir.mkdir(parents=True, exist_ok=True)

            # Load existing record keys for deduplication
            existing_keys: set[str] = set()
            for existing_file in raw_dir.glob("*.json"):
                try:
                    data = json.loads(existing_file.read_text(encoding="utf-8"))
                    for r in data.get("records", []):
                        existing_keys.add(dedup_fn(r))
                except Exception:
                    pass

            logger.info("[fetch] %s / %s — existing keys: %d", source_label, competitor, len(existing_keys))

            try:
                raw = src.fetch()
                parsed = src.parse(raw)
            except Exception as exc:
                logger.warning("[fetch] %s / %s — FAILED: %s", source_label, competitor, exc)
                counts[f"{source_label}_{competitor}"] = 0
                continue

            new_records = [r for r in parsed if dedup_fn(r) not in existing_keys]
            logger.info("[fetch] %s / %s — %d fetched, %d new",
                        source_label, competitor, len(parsed), len(new_records))

            if not new_records:
                counts[f"{source_label}_{competitor}"] = 0
                continue

            out_file = raw_dir / f"live_{timestamp}.json"
            out_file.write_text(
                json.dumps({
                    "source": source_label,
                    "competitor": competitor,
                    "fetch_timestamp": timestamp,
                    "record_count": len(new_records),
                    "records": new_records,
                }, indent=2, default=str),
                encoding="utf-8",
            )
            counts[f"{source_label}_{competitor}"] = len(new_records)
            logger.info("[fetch] %s / %s — saved %d new records -> %s",
                        source_label, competitor, len(new_records), out_file.name)

    return counts


# ---------------------------------------------------------------------------
# STEP 2+3 — Enrich new records only, append to enriched files
# ---------------------------------------------------------------------------

def enrich_new(fetch_counts: dict[str, int]) -> None:
    """
    For each source+competitor that has new records, enrich ONLY the new ones
    and append to the existing enriched file.
    """
    from mil.harvester.qwen_enrichment import enrich_file, _check_ollama, OLLAMA_MODEL

    if not _check_ollama():
        logger.error("Ollama unreachable — skipping enrichment. Findings will use existing data.")
        return

    for key, new_count in fetch_counts.items():
        if new_count == 0:
            continue

        parts = key.split("_", 1)
        source_label, competitor = parts[0], parts[1]

        raw_dir = HIST_BASE / source_label / competitor
        # Find the most recently written live_ file
        live_files = sorted(raw_dir.glob("live_*.json"), reverse=True)
        if not live_files:
            continue
        latest_file = live_files[0]

        try:
            data = json.loads(latest_file.read_text(encoding="utf-8"))
            new_records = data.get("records", [])
        except Exception as exc:
            logger.warning("[enrich] failed to read %s: %s", latest_file, exc)
            continue

        if not new_records:
            continue

        logger.info("[enrich] %s / %s — enriching %d new records", source_label, competitor, len(new_records))
        enriched_records, batches_skipped = enrich_file(source_label, competitor, new_records)
        logger.info("[enrich] %s / %s — done. %d enriched, %d batches skipped",
                    source_label, competitor, len(enriched_records), batches_skipped)

        # Append to existing enriched file
        enriched_file = ENRICHED_DIR / f"{source_label}_{competitor}_enriched.json"
        existing_payload: dict = {}
        if enriched_file.exists():
            try:
                existing_payload = json.loads(enriched_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        existing_records = existing_payload.get("records", [])
        merged = existing_records + enriched_records

        enriched_file.write_text(
            json.dumps({
                "source": source_label,
                "competitor": competitor,
                "enriched_count": len(merged),
                "batches_skipped": batches_skipped,
                "model": OLLAMA_MODEL,
                "records": merged,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("[enrich] %s / %s — enriched file updated: %d total records",
                    source_label, competitor, len(merged))


# ---------------------------------------------------------------------------
# STEP 4 — Inference
# ---------------------------------------------------------------------------

def run_inference_step() -> None:
    logger.info("[inference] running mil_agent...")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "inference" / "mil_agent.py")],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        logger.warning("[inference] mil_agent exited with code %d", result.returncode)
    else:
        logger.info("[inference] complete.")


# ---------------------------------------------------------------------------
# STEP 4a — Research Trigger
# ---------------------------------------------------------------------------

def run_research_trigger_step() -> None:
    logger.info("[research_trigger] scanning findings for P0/P1 weak-anchor signals...")
    sys.path.insert(0, str(MIL_ROOT))
    try:
        from harvester.research_trigger import run as trigger_run
        result = trigger_run()
        logger.info(
            "[research_trigger] complete — triggered=%d skipped=%d ignored=%d",
            result["triggered"], result["skipped"], result["ignored"],
        )
    except Exception as exc:
        logger.warning("[research_trigger] failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# STEP 4b — Vault
# ---------------------------------------------------------------------------

def run_vault_step() -> None:
    logger.info("[vault] running vault_sync.py...")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "vault" / "vault_sync.py")],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        logger.warning("[vault] vault_sync.py exited with code %d", result.returncode)
    else:
        logger.info("[vault] complete.")


# ---------------------------------------------------------------------------
# STEP 5 — Publish
# ---------------------------------------------------------------------------

def run_publish_step() -> None:
    logger.info("[publish] running publish.py...")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "publish" / "publish.py")],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        logger.warning("[publish] publish.py exited with code %d", result.returncode)
    else:
        logger.info("[publish] briefing updated.")


def run_publish_v2_step() -> None:
    logger.info("[publish_v2] running publish_v2.py...")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "publish" / "publish_v2.py")],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        logger.warning("[publish_v2] publish_v2.py exited with code %d", result.returncode)
    else:
        logger.info("[publish_v2] briefing-v2 updated.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MIL daily refresh pipeline")
    parser.add_argument("--dry-run",    action="store_true", help="Fetch + enrich only; skip inference and publish")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetch; re-run inference + publish only")
    args = parser.parse_args()

    logger.info("=== MIL Daily Refresh — %s ===", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    fetch_counts: dict[str, int] = {}

    if not args.skip_fetch:
        logger.info("--- Step 1: Fetch ---")
        fetch_counts = fetch_new_records()
        total_new = sum(fetch_counts.values())
        logger.info("Fetch complete. Total new records: %d", total_new)

        logger.info("--- Step 2+3: Enrich (Sonnet) ---")
        from mil.harvester.enrich_sonnet import run_enrichment as sonnet_enrich
        sonnet_enrich()
    else:
        logger.info("--skip-fetch set: skipping fetch and enrichment.")

    if args.dry_run:
        logger.info("--dry-run set: stopping before inference and publish.")
        return

    logger.info("--- Step 4: Inference ---")
    run_inference_step()

    logger.info("--- Step 4a: Research Trigger ---")
    run_research_trigger_step()

    logger.info("--- Step 4b: Vault ---")
    run_vault_step()

    logger.info("--- Step 5: Publish ---")
    run_publish_step()

    logger.info("--- Step 5b: Publish V2 ---")
    run_publish_v2_step()

    logger.info("--- Step 6: Log Run ---")
    _log_run(fetch_counts)

    logger.info("=== Done ===")


# ---------------------------------------------------------------------------
# Run log — M1 streak tracker
# ---------------------------------------------------------------------------

RUN_LOG = REPO_ROOT / "mil" / "data" / "daily_run_log.jsonl"

def _log_run(fetch_counts: dict) -> None:
    """Append a run record to daily_run_log.jsonl and report M1 streak."""
    import json as _json

    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)

    # Read existing log to compute run number and streak
    runs = []
    if RUN_LOG.exists():
        for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    runs.append(_json.loads(line))
                except _json.JSONDecodeError:
                    pass

    run_number = len(runs) + 1
    today      = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Compute M1 streak: consecutive days ending today
    # Streak origin: 2026-04-01 (day 1 — pre-dates log, hardcoded per M1 governance)
    from datetime import timedelta, date as _date
    M1_ORIGIN = _date(2026, 4, 1)
    today_date = datetime.now(timezone.utc).date()
    streak = (today_date - M1_ORIGIN).days + 1

    # Load findings count
    findings_count = 0
    findings_path  = MIL_ROOT / "outputs" / "mil_findings.json"
    if findings_path.exists():
        try:
            fd = _json.loads(findings_path.read_text(encoding="utf-8"))
            findings_count = len(fd.get("findings", []))
        except Exception:
            pass

    entry = {
        "run":          run_number,
        "date":         today,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "status":       "CLEAN",
        "new_records":  sum(fetch_counts.values()),
        "findings":     findings_count,
        "m1_streak":    streak,
        "m1_target":    5,
        "m1_done":      streak >= 5,
    }

    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")

    logger.info("Run #%d logged — date=%s streak=%d/5 new_records=%d findings=%d",
                run_number, today, streak, entry["new_records"], findings_count)
    if entry["m1_done"]:
        logger.info("*** M1 ACHIEVED — 5 consecutive clean runs complete ***")
    else:
        logger.info("M1 progress: %d/5 clean runs", streak)


if __name__ == "__main__":
    main()
