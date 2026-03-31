"""
enrich_sonnet.py — MIL enrichment using Claude Sonnet API.

Replaces Refuel-8B for enrichment. Same batch structure, new schema:
  issue_type       — what went wrong (16 operational categories)
  customer_journey — what the customer was trying to do (9 intent categories)
  sentiment_score  — float -1.0 to 1.0
  severity_class   — P0 / P1 / P2
  reasoning        — one sentence

Sources:
  - Existing enriched files (mil/data/historical/enriched/*.json) — re-enriched
  - New raw files (mil/data/historical/{source}/{competitor}/live_*.json) — first-time enrichment

Output: writes back to mil/data/historical/enriched/{source}_{competitor}_enriched.json

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MIL_ROOT      = Path(__file__).parent.parent
ENRICHED_DIR  = MIL_ROOT / "data" / "historical" / "enriched"
HIST_BASE     = MIL_ROOT / "data" / "historical"

MODEL         = "claude-haiku-4-5-20251001"
BATCH_SIZE    = 10   # records per API call — Sonnet handles larger batches cleanly
MAX_RETRIES   = 3

ISSUE_TYPES = [
    "App Not Opening",
    "App Crashing",
    "Login Failed",
    "Payment Failed",
    "Transfer Failed",
    "Biometric / Face ID Issue",
    "Card Frozen or Blocked",
    "Slow Performance",
    "Feature Broken",
    "Notification Issue",
    "Account Locked",
    "Missing Transaction",
    "Incorrect Balance",
    "Customer Support Failure",
    "Positive Feedback",
    "Other",
]

CUSTOMER_JOURNEYS = [
    "Log In to Account",
    "Make a Payment",
    "Transfer Money",
    "Check Balance or Statement",
    "Open or Register Account",
    "Apply for Loan or Overdraft",
    "Manage Card",
    "Get Support",
    "General App Use",
]

SYSTEM_PROMPT = (
    "You are a banking app complaints analyst. "
    "Output MUST be a valid JSON array only. "
    "No preamble, no markdown, no explanation outside the JSON."
)

BATCH_PROMPT_TEMPLATE = """Classify each numbered banking app review. Return a JSON array with one object per review.

Each object must have exactly these fields:
- issue_type: what went wrong. One of: {issues}
- customer_journey: what the customer was trying to do. One of: {journeys}
- sentiment_score: number from -1.0 (very negative) to 1.0 (very positive)
- severity_class: P0, P1, or P2 using these rules:
    P0 = complete block (cannot log in at all, payment completely fails, app will not open, total loss of access)
    P1 = significant friction (repeated failures, feature broken after update, cannot complete key action after retrying)
    P2 = minor annoyance, cosmetic issue, or positive review
- reasoning: one sentence explaining the severity choice

Reviews:
{reviews}"""


def _get_client():
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")


def _get_review_text(record: dict) -> str:
    return record.get("review") or record.get("content") or ""


def _normalise(obj: dict) -> dict:
    issue = obj.get("issue_type", "Other")
    if issue not in ISSUE_TYPES:
        issue = "Other"

    journey = obj.get("customer_journey", "General App Use")
    if journey not in CUSTOMER_JOURNEYS:
        journey = "General App Use"

    try:
        sentiment = float(obj.get("sentiment_score", 0.0))
        sentiment = max(-1.0, min(1.0, sentiment))
    except (TypeError, ValueError):
        sentiment = 0.0

    severity = obj.get("severity_class", "P2")
    if severity not in ("P0", "P1", "P2"):
        severity = "P2"

    # Severity gate: P0/P1 only for genuine blocking issues
    BLOCKING_ISSUES = {
        "App Not Opening", "Login Failed", "Payment Failed",
        "Transfer Failed", "Account Locked", "App Crashing",
    }
    if severity in ("P0", "P1") and issue not in BLOCKING_ISSUES:
        severity = "P2"

    # Positive feedback is always P2
    if issue == "Positive Feedback":
        severity = "P2"

    reasoning = str(obj.get("reasoning", ""))[:300]

    return {
        "issue_type":       issue,
        "customer_journey": journey,
        "sentiment_score":  round(sentiment, 3),
        "severity_class":   severity,
        "reasoning":        reasoning,
    }


def _classify_batch(client, records: list[dict], batch_id: str) -> list[dict]:
    lines = []
    for i, r in enumerate(records, 1):
        text = _get_review_text(r)[:300]
        rating = r.get("rating", "?")
        lines.append(f"{i}. [rating {rating}/5] {text}")

    prompt = BATCH_PROMPT_TEMPLATE.format(
        issues=", ".join(ISSUE_TYPES),
        journeys=", ".join(CUSTOMER_JOURNEYS),
        reviews="\n".join(lines),
    )

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            break
        except Exception as exc:
            last_exc = exc
            logger.warning("[enrich_sonnet] batch %s attempt %d/%d failed: %s",
                           batch_id, attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(3 * attempt)
    else:
        raise last_exc

    # JSON repair pipeline
    import re
    m = re.search(r"[\[\{]", raw)
    if not m:
        raise ValueError(f"No JSON in response: {raw[:200]}")
    start = m.start()
    last_close = max(raw.rfind("]"), raw.rfind("}"))
    trimmed = raw[start:last_close + 1]

    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            parsed = json.loads(repair_json(trimmed))
        except Exception as exc:
            raise ValueError(f"JSON repair failed: {exc}")

    if not isinstance(parsed, list):
        parsed = [parsed]

    return parsed


def enrich_records(source: str, competitor: str, records: list[dict]) -> list[dict]:
    """
    Enrich a list of raw records. Returns enriched records.
    """
    client = _get_client()
    enriched = []
    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(records), BATCH_SIZE):
        batch = records[batch_idx: batch_idx + BATCH_SIZE]
        batch_num = (batch_idx // BATCH_SIZE) + 1
        batch_id = f"{source}_{competitor}_b{batch_num}"
        logger.info("[enrich_sonnet] %s/%s batch %d/%d (%d records)",
                    source, competitor, batch_num, total_batches, len(batch))

        try:
            results = _classify_batch(client, batch, batch_id)
            # Align results to batch length
            for i, rec in enumerate(batch):
                enr = results[i] if i < len(results) else {}
                enriched.append({**rec, **_normalise(enr)})
        except Exception as exc:
            logger.error("[enrich_sonnet] %s batch %d failed: %s — marking ENRICHMENT_FAILED",
                         batch_id, batch_num, exc)
            for rec in batch:
                enriched.append({
                    **rec,
                    "issue_type":       "ENRICHMENT_FAILED",
                    "customer_journey": "ENRICHMENT_FAILED",
                    "sentiment_score":  0.0,
                    "severity_class":   "ENRICHMENT_FAILED",
                    "reasoning":        str(exc)[:200],
                })

    return enriched


def run_enrichment() -> dict:
    """
    Main entry point.
    Records already enriched with schema v3 (issue_type + customer_journey present
    and not ENRICHMENT_FAILED) are kept as-is — zero API calls for them.
    Only enriches: new live_ records + any existing records missing v3 fields.
    Returns summary dict.
    """
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}

    _V3_FIELDS = {"issue_type", "customer_journey", "sentiment_score", "severity_class"}
    _RAW_FIELDS = ["rating", "title", "review", "content", "version",
                   "date", "at", "author", "userName", "page",
                   "thumbsUpCount", "reviewCreatedVersion"]

    def _is_v3(r: dict) -> bool:
        return (
            all(f in r for f in _V3_FIELDS)
            and r.get("severity_class") not in ("ENRICHMENT_FAILED", None)
            and r.get("issue_type") not in ("ENRICHMENT_FAILED", None)
        )

    def _to_raw(r: dict) -> dict:
        return {k: r[k] for k in _RAW_FIELDS if k in r}

    # Build map of live_ raw records per source+competitor
    live_map: dict[str, list[dict]] = {}
    for source_dir in sorted(HIST_BASE.iterdir()):
        if not source_dir.is_dir() or source_dir.name == "enriched":
            continue
        for comp_dir in sorted(source_dir.iterdir()):
            if not comp_dir.is_dir():
                continue
            key = f"{source_dir.name}_{comp_dir.name}"
            live_records = []
            for live_file in sorted(comp_dir.glob("live_*.json")):
                try:
                    d = json.loads(live_file.read_text(encoding="utf-8"))
                    live_records.extend(d.get("records", []))
                except Exception as exc:
                    logger.warning("[enrich_sonnet] failed to read %s: %s", live_file, exc)
            if live_records:
                live_map[key] = live_records

    # Process each enriched file
    for enriched_file in sorted(ENRICHED_DIR.glob("*.json")):
        try:
            payload = json.loads(enriched_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[enrich_sonnet] cannot read %s: %s", enriched_file, exc)
            continue

        source     = payload.get("source", "")
        competitor = payload.get("competitor", "")
        key        = f"{source}_{competitor}"
        file_is_v3 = payload.get("schema_version") == "v3"

        all_existing = payload.get("records", [])

        # Partition existing: already v3 (keep) vs needs enrichment (re-enrich)
        already_enriched = []
        needs_enrichment = []
        for r in all_existing:
            if file_is_v3 and _is_v3(r):
                already_enriched.append(r)
            else:
                needs_enrichment.append(_to_raw(r))

        # New records from live_ files not already present
        existing_texts = {
            (r.get("review") or r.get("content", ""))[:80]
            for r in all_existing
        }
        new_records = [
            _to_raw(r) for r in live_map.get(key, [])
            if (r.get("review") or r.get("content", ""))[:80] not in existing_texts
        ]

        to_enrich = needs_enrichment + new_records

        logger.info(
            "[enrich_sonnet] %s: %d kept (v3) | %d re-enrich | %d new",
            key, len(already_enriched), len(needs_enrichment), len(new_records),
        )

        freshly_enriched = enrich_records(source, competitor, to_enrich) if to_enrich else []

        final_records = already_enriched + freshly_enriched
        if not final_records:
            continue

        enriched_file.write_text(
            json.dumps({
                "source":         source,
                "competitor":     competitor,
                "enriched_count": len(final_records),
                "model":          MODEL,
                "schema_version": "v3",
                "records":        final_records,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("[enrich_sonnet] %s: wrote %d records (%d new enrichments)",
                    key, len(final_records), len(freshly_enriched))
        summary[key] = {
            "records_total":    len(final_records),
            "records_enriched": len(freshly_enriched),
            "records_kept":     len(already_enriched),
        }

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger.info("MIL Sonnet Enrichment — starting full re-enrich")
    result = run_enrichment()
    logger.info("Done. Summary: %s", result)
