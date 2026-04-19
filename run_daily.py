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
                except Exception as exc:
                    logger.warning("[fetch] could not read existing file for dedup: %s", exc)

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


def run_publish_v3_step() -> None:
    logger.info("[publish_v3] running publish_v3.py...")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "publish" / "publish_v3.py")],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        logger.warning("[publish_v3] publish_v3.py exited with code %d", result.returncode)
    else:
        logger.info("[publish_v3] briefing-v3 updated.")


# ---------------------------------------------------------------------------
# Run Summary
# ---------------------------------------------------------------------------

_STEP_FIXES = {
    "fetch":            "Check internet. App Store / Google Play may be rate-limiting.",
    "enrichment":       "Is Ollama running? `ollama serve`. Check model pulled: `ollama list`.",
    "inference":        "Check mil_agent.py logs above. Chronicle loader needs ≥15 entries.",
    "research_trigger": "Non-fatal. Inspect harvester/research_trigger.py manually.",
    "vault":            "Start HDFS: `docker-compose up -d`. Check mil-namenode on port 9871.",
    "clark":            "Non-fatal. Inspect clark_protocol.py. Briefing will still publish.",
    "benchmark":        "Check benchmark_engine.py. May need `--backfill` if run log is empty.",
    "analytics":        "Check build_analytics_db.py. DuckDB may have a lock conflict.",
    "publish_v1":       "Check publish.py. GitHub Pages push may have failed — check git remote.",
    "publish_v2":       "Requires index.html from V1 publish. Run V1 first, then retry.",
    "publish_v3":       "Check publish_v3.py + commentary_engine.py (Sonnet API or Ollama down?).",
}

_CRITICAL_STEPS = {"inference", "publish_v1", "publish_v2", "publish_v3"}


def _egress_today_summary() -> dict:
    """Read data_egress_log.jsonl and return cost/token totals for today's UTC date."""
    log_path = MIL_ROOT / "data" / "data_egress_log.jsonl"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    totals: dict = {"calls": 0, "success": 0, "failed": 0,
                    "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                    "by_task": {}}
    if not log_path.exists():
        return totals
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not e.get("timestamp", "").startswith(today):
            continue
        totals["calls"] += 1
        if e.get("success"):
            totals["success"] += 1
        else:
            totals["failed"] += 1
        totals["input_tokens"]  += e.get("input_tokens", 0)
        totals["output_tokens"] += e.get("output_tokens", 0)
        totals["cost_usd"]      += e.get("cost_usd", 0.0)
        task = e.get("task", "unknown")
        t = totals["by_task"].setdefault(task, {"calls": 0, "cost_usd": 0.0})
        t["calls"]    += 1
        t["cost_usd"] += e.get("cost_usd", 0.0)
    totals["cost_usd"] = round(totals["cost_usd"], 4)
    return totals


def _count_enrichment_failures() -> tuple[int, int]:
    """Return (total_records, failed_count) across all enriched files."""
    total, failed = 0, 0
    for path in ENRICHED_DIR.glob("*_enriched.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records = data.get("records", [])
            total  += len(records)
            failed += sum(1 for r in records if r.get("severity_class") == "ENRICHMENT_FAILED")
        except Exception:
            pass
    return total, failed


def _print_run_summary(
    steps: list[tuple[str, str, str]],   # (step_label, status, metric)
    fetch_counts: dict,
    benchmark_result: dict,
    failed_steps: list[str],
    enrich_model: str,
    run_number: int,
) -> None:
    """Print a clear end-of-run report to stdout."""
    W = 70
    STATUS_ICON = {"DONE": "✓", "SKIP": "-", "FAIL": "✗"}
    STATUS_PAD  = {"DONE": "", "SKIP": "", "FAIL": ""}

    lines = []
    lines.append("=" * W)
    lines.append(f"  MIL DAILY RUN #{run_number} — SUMMARY")
    lines.append(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * W)

    # ── Pipeline steps ──────────────────────────────────────────────────
    lines.append("")
    lines.append("  PIPELINE STEPS")
    lines.append("  " + "-" * (W - 2))
    for label, status, metric in steps:
        icon = STATUS_ICON.get(status, "?")
        lines.append(f"  [{icon}] {label:<28}  {metric}")
    lines.append("")

    # ── Model performance ────────────────────────────────────────────────
    total_records, failed_enriched = _count_enrichment_failures()
    new_records = sum(fetch_counts.values())
    fail_pct = (failed_enriched / total_records * 100) if total_records else 0

    lines.append("  MODEL PERFORMANCE")
    lines.append("  " + "-" * (W - 2))
    lines.append(f"  Enrichment model : {enrich_model}")
    lines.append(f"  Corpus total     : {total_records:,} records")
    lines.append(f"  New this run     : {new_records}")
    lines.append(f"  ENRICHMENT_FAILED: {failed_enriched} ({fail_pct:.1f}%)")
    if fail_pct > 5:
        lines.append(f"  !! Failure rate above 5% — check Ollama / model output format")
    lines.append("")

    # ── Data Egress (MIL-37) ─────────────────────────────────────────────
    eg = _egress_today_summary()
    lines.append("  DATA EGRESS (today)")
    lines.append("  " + "-" * (W - 2))
    lines.append(f"  API calls        : {eg['calls']} ({eg['success']} ok, {eg['failed']} failed)")
    lines.append(f"  Tokens in/out    : {eg['input_tokens']:,} / {eg['output_tokens']:,}")
    lines.append(f"  Est. cost today  : ${eg['cost_usd']:.4f}")
    if eg["by_task"]:
        top = sorted(eg["by_task"].items(), key=lambda x: x[1]["cost_usd"], reverse=True)[:4]
        for task_name, td in top:
            lines.append(f"  {task_name:<18}  {td['calls']} calls  ${td['cost_usd']:.4f}")
    lines.append("")

    # ── Intelligence ─────────────────────────────────────────────────────
    findings_path = MIL_ROOT / "outputs" / "mil_findings.json"
    if findings_path.exists():
        try:
            fd = json.loads(findings_path.read_text(encoding="utf-8"))
            all_f = fd.get("findings", [])
            p0 = sum(1 for f in all_f if f.get("dominant_severity") == "P0")
            p1 = sum(1 for f in all_f if f.get("dominant_severity") == "P1")
            anchored = sum(1 for f in all_f if f.get("chronicle_id") and not f.get("chronicle_id", "").startswith("UNK"))
            ceiling  = sum(1 for f in all_f if f.get("designed_ceiling"))
            tier_order = {"CLARK-3": 3, "CLARK-2": 2, "CLARK-1": 1, "CLARK-0": 0}
            clark_max = max((f.get("clark_tier", "CLARK-0") for f in all_f), key=lambda t: tier_order.get(t, 0), default="CLARK-0")
            lines.append("  INTELLIGENCE")
            lines.append("  " + "-" * (W - 2))
            lines.append(f"  Findings         : {len(all_f)} total | {p0} P0 | {p1} P1")
            lines.append(f"  Anchored         : {anchored}/{len(all_f)} ({anchored/len(all_f)*100:.0f}%)" if all_f else "  Anchored         : 0/0")
            lines.append(f"  Designed Ceiling : {ceiling}")
            lines.append(f"  Clark max tier   : {clark_max}")
        except Exception:
            lines.append("  INTELLIGENCE      — could not read mil_findings.json")
        lines.append("")

    bm = benchmark_result or {}
    if bm:
        churn = bm.get("churn_risk_score")
        trend = bm.get("churn_risk_trend", "?")
        over  = bm.get("over_indexed", [])
        lines.append("  CHURN SIGNAL")
        lines.append("  " + "-" * (W - 2))
        lines.append(f"  Churn risk score : {churn:.1f}/100  trend={trend}" if churn is not None else "  Churn risk score : unavailable")
        if over:
            lines.append(f"  Over-indexed     : {', '.join(str(o) for o in over[:4])}")
        lines.append("")

    # ── Failures + fixes ─────────────────────────────────────────────────
    if failed_steps:
        lines.append("  FAILURES")
        lines.append("  " + "-" * (W - 2))
        for step in failed_steps:
            critical = " [CRITICAL]" if step in _CRITICAL_STEPS else " [non-fatal]"
            lines.append(f"  ✗  {step}{critical}")
            fix = _STEP_FIXES.get(step)
            if fix:
                lines.append(f"     Fix: {fix}")
        lines.append("")

    # ── Overall status ────────────────────────────────────────────────────
    if _CRITICAL_STEPS & set(failed_steps):
        overall = "FAILED  — critical step(s) did not complete"
    elif failed_steps:
        overall = "PARTIAL — pipeline ran with non-fatal failures"
    else:
        overall = "CLEAN   — all steps completed"

    lines.append("=" * W)
    lines.append(f"  OVERALL STATUS: {overall}")
    lines.append("=" * W)

    print("\n" + "\n".join(lines) + "\n", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _hdfs_preflight() -> bool:
    """Quick TCP check on HDFS NameNode port 9871 before attempting vault."""
    import socket
    try:
        with socket.create_connection(("localhost", 9871), timeout=3):
            return True
    except OSError:
        logger.warning("[vault] HDFS NameNode not reachable on port 9871 — is mil-namenode running?")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="MIL daily refresh pipeline")
    parser.add_argument("--dry-run",    action="store_true", help="Fetch + enrich only; skip inference and publish")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetch; re-run inference + publish only")
    args = parser.parse_args()

    logger.info("=== MIL Daily Refresh — %s ===", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    fetch_counts: dict[str, int] = {}
    failed_steps: list[str] = []
    _steps: list[tuple[str, str, str]] = []   # (label, status, metric)

    # Resolve enrichment model name for summary display
    try:
        from mil.config.get_model import get_model as _gm
        _enrich_model = _gm("enrichment")["model"]
    except Exception:
        _enrich_model = "unknown"

    if not args.skip_fetch:
        logger.info("--- Step 1: Fetch ---")
        fetch_counts = fetch_new_records()
        total_new = sum(fetch_counts.values())
        logger.info("Fetch complete. Total new records: %d", total_new)
        _steps.append(("1  Fetch", "DONE", f"{total_new} new records"))

        logger.info("--- Step 2+3: Enrich ---")
        try:
            from mil.harvester.enrich_sonnet import run_enrichment as sonnet_enrich
            _enrich_summary = sonnet_enrich()
            _enriched_count = sum(v.get("records_enriched", 0) for v in (_enrich_summary or {}).values())
            _steps.append(("2  Enrich", "DONE", f"{_enriched_count} records enriched via {_enrich_model}"))
        except Exception as exc:
            logger.warning("[enrich] failed: %s", exc)
            failed_steps.append("enrichment")
            _steps.append(("2  Enrich", "FAIL", str(exc)[:60]))
    else:
        logger.info("--skip-fetch set: skipping fetch and enrichment.")
        _steps.append(("1  Fetch",  "SKIP", "--skip-fetch flag"))
        _steps.append(("2  Enrich", "SKIP", "--skip-fetch flag"))

    if args.dry_run:
        logger.info("--dry-run set: stopping before inference and publish.")
        _steps.append(("3  Inference", "SKIP", "--dry-run flag"))
        return

    logger.info("--- Step 4: Inference ---")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "inference" / "mil_agent.py")],
        cwd=str(REPO_ROOT), stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        logger.warning("[inference] mil_agent exited with code %d\n%s",
                       result.returncode, result.stderr.decode(errors="replace"))
        failed_steps.append("inference")
        _steps.append(("4  Inference", "FAIL", f"exit code {result.returncode}"))
    else:
        logger.info("[inference] complete.")
        _steps.append(("4  Inference", "DONE", "mil_findings.json updated"))

    logger.info("--- Step 4a: Research Trigger ---")
    try:
        from harvester.research_trigger import run as trigger_run
        r = trigger_run()
        logger.info("[research_trigger] complete — triggered=%d skipped=%d ignored=%d",
                    r["triggered"], r["skipped"], r["ignored"])
        _steps.append(("4a Research Trigger", "DONE", f"triggered={r['triggered']} skipped={r['skipped']}"))
    except Exception as exc:
        logger.warning("[research_trigger] failed (non-fatal): %s", exc)
        failed_steps.append("research_trigger")
        _steps.append(("4a Research Trigger", "FAIL", str(exc)[:60]))

    logger.info("--- Step 4b: Vault ---")
    _hdfs_ok = _hdfs_preflight()
    if _hdfs_ok:
        result = subprocess.run(
            [sys.executable, str(MIL_ROOT / "vault" / "vault_sync.py")],
            cwd=str(REPO_ROOT), stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            logger.warning("[vault] vault_sync.py exited with code %d\n%s",
                           result.returncode, result.stderr.decode(errors="replace"))
            failed_steps.append("vault")
            _steps.append(("4b Vault", "FAIL", f"exit code {result.returncode}"))
        else:
            logger.info("[vault] complete.")
            _steps.append(("4b Vault", "DONE", "HDFS sync complete"))
    else:
        logger.warning("[vault] skipped — HDFS preflight failed")
        failed_steps.append("vault")
        _steps.append(("4b Vault", "FAIL", "HDFS NameNode unreachable (port 9871)"))

    logger.info("--- Step 4c: Clark Escalation ---")
    try:
        from mil.command.components.clark_protocol import scan_and_escalate, scan_and_downgrade
        new_esc = scan_and_escalate()
        new_dg  = scan_and_downgrade()
        logger.info("[clark] %d new escalations | %d downgraded", len(new_esc), new_dg)
        _steps.append(("4c Clark Escalation", "DONE", f"{len(new_esc)} escalated | {new_dg} downgraded"))
    except Exception as exc:
        logger.warning("[clark] escalation failed: %s", exc)
        failed_steps.append("clark")
        _steps.append(("4c Clark Escalation", "FAIL", str(exc)[:60]))

    logger.info("--- Step 4d: Benchmark + Persistence ---")
    _benchmark_result: dict = {}
    try:
        sys.path.insert(0, str(MIL_ROOT / "data"))
        from benchmark_engine import run as benchmark_run
        _benchmark_result = benchmark_run(mode="daily")
        _churn = _benchmark_result.get("churn_risk_score", 0)
        _trend = _benchmark_result.get("churn_risk_trend", "?")
        logger.info("[benchmark] churn_risk_score=%.2f trend=%s over_indexed=%d",
                    _churn, _trend, len(_benchmark_result.get("over_indexed", [])))
        _steps.append(("4d Benchmark", "DONE", f"churn={_churn:.1f} trend={_trend}"))
    except Exception as exc:
        logger.warning("[benchmark] failed (non-fatal): %s", exc)
        failed_steps.append("benchmark")
        _steps.append(("4d Benchmark", "FAIL", str(exc)[:60]))

    logger.info("--- Step 4e: Analytics DB ---")
    try:
        import importlib.util, pathlib
        _spec = importlib.util.spec_from_file_location(
            "build_analytics_db",
            pathlib.Path(__file__).parent / "mil" / "analytics" / "build_analytics_db.py",
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _mod.main()
        logger.info("[analytics] mil_analytics.db rebuilt.")
        _steps.append(("4e Analytics DB", "DONE", "mil_analytics.db rebuilt"))
    except Exception as exc:
        logger.warning("[analytics] failed (non-fatal): %s", exc)
        failed_steps.append("analytics")
        _steps.append(("4e Analytics DB", "FAIL", str(exc)[:60]))

    logger.info("--- Step 5: Publish ---")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "publish" / "publish.py")],
        cwd=str(REPO_ROOT), stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        logger.warning("[publish] publish.py exited with code %d\n%s",
                       result.returncode, result.stderr.decode(errors="replace"))
        failed_steps.append("publish_v1")
        _steps.append(("5  Publish V1", "FAIL", f"exit code {result.returncode}"))
    else:
        logger.info("[publish] briefing updated.")
        _steps.append(("5  Publish V1", "DONE", "cjipro.com/briefing updated"))

    logger.info("--- Step 5b: Publish V2 ---")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "publish" / "publish_v2.py")],
        cwd=str(REPO_ROOT), stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        logger.warning("[publish_v2] publish_v2.py exited with code %d\n%s",
                       result.returncode, result.stderr.decode(errors="replace"))
        failed_steps.append("publish_v2")
        _steps.append(("5b Publish V2", "FAIL", f"exit code {result.returncode}"))
    else:
        logger.info("[publish_v2] briefing-v2 updated.")
        _steps.append(("5b Publish V2", "DONE", "cjipro.com/briefing-v2 updated"))

    logger.info("--- Step 5c: Publish V3 ---")
    result = subprocess.run(
        [sys.executable, str(MIL_ROOT / "publish" / "publish_v3.py")],
        cwd=str(REPO_ROOT), stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        logger.warning("[publish_v3] publish_v3.py exited with code %d\n%s",
                       result.returncode, result.stderr.decode(errors="replace"))
        failed_steps.append("publish_v3")
        _steps.append(("5c Publish V3", "FAIL", f"exit code {result.returncode}"))
    else:
        logger.info("[publish_v3] briefing-v3 updated.")
        _steps.append(("5c Publish V3", "DONE", "cjipro.com/briefing-v3 updated"))

    logger.info("--- Step 6: Log Run ---")
    _run_entry = _log_run(fetch_counts, _benchmark_result, failed_steps)
    _steps.append(("6  Log Run", "DONE", f"Run #{_run_entry.get('run', '?')} | streak={_run_entry.get('m1_streak', '?')}/5"))

    _print_run_summary(_steps, fetch_counts, _benchmark_result, failed_steps, _enrich_model, _run_entry.get("run", 0))

    # MIL-38: send run-completion notification
    try:
        from mil.notify.notifier import notify_run_complete
        _eg      = _egress_today_summary()
        _bm      = _benchmark_result or {}
        _status  = ("FAILED" if (_CRITICAL_STEPS & set(failed_steps)) else
                    ("PARTIAL" if failed_steps else "CLEAN"))
        notify_run_complete(
            run_number   = _run_entry.get("run", 0),
            status       = _status,
            failed_steps = failed_steps,
            churn_score  = _bm.get("churn_risk_score"),
            churn_trend  = _bm.get("churn_risk_trend", "?"),
            clark_max    = _run_entry.get("clark_tier_max", "CLARK-0"),
            cost_usd     = _eg.get("cost_usd", 0.0),
            new_records  = sum(fetch_counts.values()),
        )
    except Exception as exc:
        logger.warning("[notify] run-complete notification failed (non-fatal): %s", exc)

    logger.info("=== Done ===")


# ---------------------------------------------------------------------------
# Run log — M1 streak tracker
# ---------------------------------------------------------------------------

RUN_LOG = REPO_ROOT / "mil" / "data" / "daily_run_log.jsonl"

def _log_run(fetch_counts: dict, benchmark_result: dict | None = None, failed_steps: list | None = None) -> dict:
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

    # Load findings + severity breakdown + CHR distribution + max Clark tier
    findings_count = 0
    p0_count = 0
    p1_count = 0
    chr_top3: list[str] = []
    clark_tier_max = "CLARK-0"
    findings_path  = MIL_ROOT / "outputs" / "mil_findings.json"
    if findings_path.exists():
        try:
            from collections import Counter as _Counter
            fd = _json.loads(findings_path.read_text(encoding="utf-8"))
            all_findings = fd.get("findings", [])
            findings_count = len(all_findings)
            p0_count = sum(1 for f in all_findings if f.get("dominant_severity") == "P0")
            p1_count = sum(1 for f in all_findings if f.get("dominant_severity") == "P1")
            chr_dist = _Counter(f.get("chronicle_id", "UNANCHORED") for f in all_findings)
            chr_top3 = [cid for cid, _ in chr_dist.most_common(3)]
            clark_tiers = [f.get("clark_tier", "CLARK-0") for f in all_findings]
            tier_order = {"CLARK-3": 3, "CLARK-2": 2, "CLARK-1": 1, "CLARK-0": 0}
            clark_tier_max = max(clark_tiers, key=lambda t: tier_order.get(t, 0), default="CLARK-0")
        except Exception as exc:
            logger.warning("[log_run] could not parse findings for health fields: %s", exc)

    bm = benchmark_result or {}
    _failed = failed_steps or []
    _critical = {"inference", "publish_v1", "publish_v2", "publish_v3"}
    if _critical & set(_failed):
        _status = "FAILED"
    elif _failed:
        _status = "PARTIAL"
    else:
        _status = "CLEAN"

    entry = {
        "run":                  run_number,
        "date":                 today,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
        "status":               _status,
        "failed_steps":         _failed,
        "new_records":          sum(fetch_counts.values()),
        "findings":             findings_count,
        "p0_count":             p0_count,
        "p1_count":             p1_count,
        "chr_anchor_top3":      chr_top3,
        "clark_tier_max":       clark_tier_max,
        "m1_streak":            streak,
        "m1_target":            5,
        "m1_done":              streak >= 5,
        "churn_risk_score":     bm.get("churn_risk_score"),
        "churn_risk_trend":     bm.get("churn_risk_trend"),
    }

    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")

    logger.info("Run #%d logged — date=%s streak=%d/5 new_records=%d findings=%d churn=%.1f(%s)",
                run_number, today, streak, entry["new_records"], findings_count,
                entry["churn_risk_score"] or 0, entry["churn_risk_trend"] or "?")
    if entry["m1_done"]:
        logger.info("*** M1 ACHIEVED — 5 consecutive clean runs complete ***")
    else:
        logger.info("M1 progress: %d/5 clean runs", streak)

    return entry


if __name__ == "__main__":
    main()
