"""
qwen_enrichment.py — MIL Refuel enrichment factory.

Reads historical backfill files from mil/data/historical/{source}/{competitor}/
Processes records in batches via Refuel-8B (michaelborck/refuled:latest, Ollama).
Appends three fields per record:
  journey_attribution  — login / payments / onboarding / account_management /
                         app_performance / other
  severity_class       — P0 / P1 / P2
  keywords             — list[str], up to 5

Writes enriched output to: mil/data/historical/enriched/
  One file per source per competitor:
  {source}_{competitor}_enriched.json

MIL Import Rule: no imports from pulse/, poc/, app/, dags/

Failure handling:
  - Ollama unreachable → stop immediately, report
  - Individual record classification failure → mark as ENRICHMENT_FAILED, continue
  - Batch failure → log batch index, skip, continue to next batch
"""
import json
import logging
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

MIL_ROOT = Path(__file__).parent.parent
HISTORICAL_BASE = MIL_ROOT / "data" / "historical"
ENRICHED_DIR = HISTORICAL_BASE / "enriched"

BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_URL = f"{BASE_URL}/chat/completions"
OLLAMA_MODEL = "michaelborck/refuled:latest"
BATCH_SIZE = 50
RECORDS_PER_PROMPT = 3    # records per call — Refuel 1.5B needs smaller batches
REQUEST_TIMEOUT = 180     # seconds per call
MAX_RETRIES = 3           # retry attempts on connection/timeout errors

JOURNEY_OPTIONS = [
    "login", "payments", "onboarding",
    "account_management", "app_performance", "other",
]

SYSTEM_PROMPT = (
    "You are a data-only agent. "
    "Output MUST be a valid JSON array. "
    "No preamble, no markdown code blocks."
)

BATCH_PROMPT_TEMPLATE = (
    "Classify each numbered banking app review below.\n"
    "Return a JSON array with one object per review.\n"
    "Each object must have exactly these keys:\n"
    "  journey_attribution: one of login / payments / onboarding / account_management / app_performance / other\n"
    "  severity_class: P0 (outage, cannot complete), P1 (significant friction), P2 (minor/cosmetic)\n"
    "  keywords: list of up to 5 strings from the review text\n"
    "Reviews:\n{reviews}"
)


def _check_ollama() -> bool:
    """Return True if Ollama is reachable. Model presence verified on first generate call."""
    try:
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _get_review_text(record: dict) -> str:
    """Extract review text. App Store uses 'review', Google Play uses 'content'."""
    return record.get("review") or record.get("content") or ""


def _normalise_enrichment(obj: dict) -> dict:
    """Validate and normalise a single Refuel-returned classification object."""
    journey = obj.get("journey_attribution", "other")
    if journey not in JOURNEY_OPTIONS:
        journey = "other"
    severity = obj.get("severity_class", "P2")
    if severity not in ("P0", "P1", "P2"):
        severity = "P2"
    keywords = obj.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []
    return {
        "journey_attribution": journey,
        "severity_class": severity,
        "keywords": [str(k) for k in keywords[:5]],
    }


def _repair_json(raw: str) -> object:
    """
    Attempt to extract and repair a JSON array from a Refuel response.

    Strategy:
      1. Strip any text before the first '[' or '{' and after the last ']' or '}'
      2. Try standard json.loads()
      3. On failure, try json_repair.repair_json() as fallback
      4. On second failure, raise ValueError — caller decides skip vs abort
    """
    import re

    # Step 1: trim preamble and trailing text
    m = re.search(r"[\[\{]", raw)
    if not m:
        raise ValueError(f"No JSON start character found in response: {raw[:200]}")
    start = m.start()

    # Find the last closing bracket/brace
    last_close = max(raw.rfind("]"), raw.rfind("}"))
    if last_close == -1:
        raise ValueError(f"No JSON end character found in response: {raw[:200]}")

    trimmed = raw[start: last_close + 1]

    # Step 2: standard parse
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        pass

    # Step 3: json_repair fallback
    try:
        from json_repair import repair_json  # type: ignore
        repaired = repair_json(trimmed)
        return json.loads(repaired)
    except Exception as exc:
        raise ValueError(f"json_repair also failed: {exc} | trimmed[:200]={trimmed[:200]}")


def _classify_batch(records: list[dict], chunk_id: str = "?") -> tuple[list[dict], int]:
    """
    Call Refuel once for a list of records (up to RECORDS_PER_PROMPT).
    Returns (enrichment_dicts, skipped_count).
    skipped_count > 0 means JSON repair failed — caller receives ENRICHMENT_FAILED entries.
    Raises on network failure only — parse failures are handled here.
    """
    # Build numbered list — truncate each review to keep prompt manageable
    lines = []
    for i, rec in enumerate(records, 1):
        text = _get_review_text(rec)[:400].replace("\n", " ")
        if not text.strip():
            text = "(no review text)"
        lines.append(f"{i}. {text}")

    prompt = BATCH_PROMPT_TEMPLATE.format(reviews="\n".join(lines))

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            logger.warning("_classify_batch chunk %s: attempt %d/%d failed: %s",
                           chunk_id, attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)
    else:
        raise last_exc

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    # Attempt JSON repair pipeline
    try:
        parsed = _repair_json(raw)
    except ValueError as exc:
        logger.debug("_classify_batch chunk %s raw response: %s", chunk_id, raw)
        logger.warning(
            "_classify_batch chunk %s: JSON repair failed (%s) — skipping %d records",
            chunk_id, exc, len(records),
        )
        # Return ENRICHMENT_FAILED entries so caller never silently drops records
        failed = [{
            "journey_attribution": "ENRICHMENT_FAILED",
            "severity_class": "ENRICHMENT_FAILED",
            "keywords": [],
            "enrichment_error": f"JSON repair failed — chunk {chunk_id}",
        } for _ in records]
        return failed, len(records)

    if not isinstance(parsed, list):
        logger.debug("_classify_batch chunk %s raw response: %s", chunk_id, raw)
        logger.warning(
            "_classify_batch chunk %s: Refuel returned non-list JSON — skipping %d records",
            chunk_id, len(records),
        )
        failed = [{
            "journey_attribution": "ENRICHMENT_FAILED",
            "severity_class": "ENRICHMENT_FAILED",
            "keywords": [],
            "enrichment_error": f"Non-list JSON — chunk {chunk_id}",
        } for _ in records]
        return failed, len(records)

    # Pad or truncate to match input count
    result = []
    for i, rec in enumerate(records):
        if i < len(parsed) and isinstance(parsed[i], dict):
            result.append(_normalise_enrichment(parsed[i]))
        else:
            result.append({
                "journey_attribution": "other",
                "severity_class": "P2",
                "keywords": [],
                "enrichment_note": "MISSING_FROM_RESPONSE",
            })
    return result, 0


def enrich_file(source: str, competitor: str, records: list[dict],
                max_records: int = None) -> tuple[list[dict], int]:
    """
    Enrich a list of records.
    Outer loop: checkpointing batches of BATCH_SIZE (for error recovery).
    Inner loop: Refuel calls of RECORDS_PER_PROMPT (for throughput).
    Returns (enriched_records, batches_skipped).
    max_records: if set, only process first N records (sample/validation mode).
    """
    if max_records is not None:
        records = records[:max_records]

    enriched: list[dict] = []
    batches_skipped = 0
    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(records), BATCH_SIZE):
        batch = records[batch_idx: batch_idx + BATCH_SIZE]
        batch_num = (batch_idx // BATCH_SIZE) + 1
        logger.info("[%s] %s — batch %d/%d (%d records)",
                    source, competitor, batch_num, total_batches, len(batch))

        batch_results: list[dict] = []
        batch_enriched = 0
        batch_skipped = 0
        batch_failed_chunks = 0

        # Inner loop: RECORDS_PER_PROMPT records per Refuel call
        for prompt_idx in range(0, len(batch), RECORDS_PER_PROMPT):
            chunk = batch[prompt_idx: prompt_idx + RECORDS_PER_PROMPT]
            chunk_id = f"b{batch_num}c{prompt_idx // RECORDS_PER_PROMPT + 1}"
            try:
                enrichments, skipped = _classify_batch(chunk, chunk_id=chunk_id)
                for rec, enr in zip(chunk, enrichments):
                    batch_results.append({**rec, **enr})
                batch_skipped += skipped
                batch_enriched += len(chunk) - skipped
            except Exception as exc:
                logger.error("[%s] %s — chunk %s network error: %s",
                             source, competitor, chunk_id, exc)
                for rec in chunk:
                    batch_results.append({
                        **rec,
                        "journey_attribution": "ENRICHMENT_FAILED",
                        "severity_class": "ENRICHMENT_FAILED",
                        "keywords": [],
                        "enrichment_error": str(exc),
                    })
                batch_skipped += len(chunk)
                batch_failed_chunks += 1

        enriched.extend(batch_results)
        batches_skipped += batch_failed_chunks

        logger.info(
            "[%s] %s — batch %d summary: %d enriched, %d skipped, %d failed chunks",
            source, competitor, batch_num, batch_enriched, batch_skipped, batch_failed_chunks,
        )

    return enriched, batches_skipped


def run_enrichment(max_records_per_file: int = None) -> dict:
    """
    Main entry point. Discovers all historical files, enriches them,
    writes to ENRICHED_DIR. Returns summary dict.
    max_records_per_file: if set, only process first N records per file
    (used for sample validation runs).
    """
    if not _check_ollama():
        logger.error("Ollama unreachable or %s not available. Stopping.", OLLAMA_MODEL)
        return {"error": f"Ollama unreachable or {OLLAMA_MODEL} not available"}

    logger.info("Ollama confirmed — %s ready", OLLAMA_MODEL)
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    summary: dict = {}  # {source: {competitor: {"records": N, "batches_skipped": N}}}

    # Walk mil/data/historical/{source}/{competitor}/*.json
    # Skip the enriched/ subdirectory
    for source_dir in sorted(HISTORICAL_BASE.iterdir()):
        if not source_dir.is_dir():
            continue
        if source_dir.name == "enriched":
            continue

        source_name = source_dir.name
        summary[source_name] = {}

        for comp_dir in sorted(source_dir.iterdir()):
            if not comp_dir.is_dir():
                continue
            competitor_name = comp_dir.name

            json_files = sorted(comp_dir.glob("*.json"))
            if not json_files:
                logger.info("[%s] %s — no JSON files found, skipping", source_name, competitor_name)
                continue

            # Merge records from all files for this competitor
            all_records: list[dict] = []
            for jf in json_files:
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    all_records.extend(data.get("records", []))
                except Exception as exc:
                    logger.warning("[%s] %s — failed to read %s: %s", source_name, competitor_name, jf.name, exc)

            if not all_records:
                logger.info("[%s] %s — 0 records after merge, skipping", source_name, competitor_name)
                continue

            label = f"{len(all_records)} records" + (f" (capped at {max_records_per_file})" if max_records_per_file else "")
            logger.info("[%s] %s — %s to enrich", source_name, competitor_name, label)

            enriched_records, batches_skipped = enrich_file(
                source_name, competitor_name, all_records,
                max_records=max_records_per_file,
            )

            out_file = ENRICHED_DIR / f"{source_name}_{competitor_name}_enriched.json"
            payload = {
                "source": source_name,
                "competitor": competitor_name,
                "enriched_count": len(enriched_records),
                "batches_skipped": batches_skipped,
                "model": OLLAMA_MODEL,
                "records": enriched_records,
            }
            out_file.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            logger.info("[%s] %s -- enrichment complete. %d records -> %s",
                        source_name, competitor_name, len(enriched_records), out_file.name)

            summary[source_name][competitor_name] = {
                "records_enriched": len(enriched_records),
                "batches_skipped": batches_skipped,
                "output_file": str(out_file),
            }

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None,
                        help="Only enrich first N records per file (validation mode)")
    args = parser.parse_args()

    mode = f"SAMPLE mode (first {args.sample} records/file)" if args.sample else "FULL mode"
    logger.info("MIL Refuel Enrichment Factory — starting [%s]", mode)
    result = run_enrichment(max_records_per_file=args.sample)

    if "error" in result:
        print(f"\nFATAL: {result['error']}")
        sys.exit(1)

    print()
    print("=" * 50)
    print("ENRICHMENT RESULTS")
    print("=" * 50)
    for source, competitors in result.items():
        print(f"\n{source}:")
        for comp, stats in competitors.items():
            skipped = stats["batches_skipped"]
            print(f"  {comp}: {stats['records_enriched']} enriched"
                  + (f", {skipped} batches skipped" if skipped else ""))
            print(f"    -> {stats['output_file']}")
    print()
