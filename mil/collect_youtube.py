"""
collect_youtube.py — YouTube daily data collection. MIL-22.

Standalone script. Runs independently from run_daily.py.
Purpose: build YouTube comment database for all active competitors.

  Fetch   — YouTube Data API v3, comments on competitor-related videos
  Dedup   — on comment_id, never stores duplicates
  Store   — mil/data/historical/youtube/{competitor}/live_TIMESTAMP.json
  Enrich  — qwen3:14b via Ollama (zero API cost)
  Vault   — HDFS /user/mil/youtube/ (uses existing vault_sync pattern)

Usage:
  py mil/collect_youtube.py                # fetch + enrich
  py mil/collect_youtube.py --fetch-only   # fetch and store raw, skip enrichment
  py mil/collect_youtube.py --enrich-only  # enrich existing raw, skip fetch

Quota: ~300 units/competitor (search) + comment pages — ~2,000 units/run total.
Free tier: 10,000 units/day. Safe to run once daily.

Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("collect_youtube")

REPO_ROOT   = Path(__file__).parent.parent
MIL_ROOT    = Path(__file__).parent
APPS_CONFIG = MIL_ROOT / "config" / "apps_config.yaml"
HIST_BASE   = MIL_ROOT / "data" / "historical"
YOUTUBE_DIR = HIST_BASE / "youtube"
ENRICHED_DIR = HIST_BASE / "enriched"

sys.path.insert(0, str(REPO_ROOT))

ENRICH_MODEL  = "qwen3:14b"
OLLAMA_BASE   = "http://127.0.0.1:11434/v1"
BATCH_SIZE    = 10

ISSUE_TYPES = [
    "App Not Opening", "App Crashing", "Login Failed", "Payment Failed",
    "Transfer Failed", "Biometric / Face ID Issue", "Card Frozen or Blocked",
    "Slow Performance", "Feature Broken", "Notification Issue", "Account Locked",
    "Missing Transaction", "Incorrect Balance", "Customer Support Failure",
    "Positive Feedback", "Other",
]
CUSTOMER_JOURNEYS = [
    "Log In to Account", "Make a Payment", "Transfer Money",
    "Check Balance or Statement", "Open or Register Account",
    "Apply for Loan or Overdraft", "Manage Card", "Get Support", "General App Use",
]
SYSTEM_PROMPT = (
    "You are a banking app complaints analyst. "
    "Output MUST be a valid JSON array only. "
    "No preamble, no markdown, no explanation outside the JSON."
)
BATCH_PROMPT_TEMPLATE = """Classify each numbered YouTube comment about a banking app. Return a JSON array with one object per comment.

Each object must have exactly these fields:
- issue_type: what went wrong. One of: {issues}
- customer_journey: what the customer was trying to do. One of: {journeys}
- sentiment_score: number from -1.0 (very negative) to 1.0 (very positive)
- severity_class: P0, P1, or P2 using these rules:
    P0 = complete block (cannot log in at all, payment completely fails, app will not open)
    P1 = significant friction (repeated failures, feature broken, cannot complete key action)
    P2 = minor annoyance, general comment, or positive feedback
- reasoning: one sentence explaining the classification

Comments:
{comments}"""

BLOCKING_ISSUES = {
    "App Not Opening", "Login Failed", "Payment Failed",
    "Transfer Failed", "Account Locked", "App Crashing",
}


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_all() -> dict[str, int]:
    """Fetch YouTube comments for all active competitors. Returns {competitor: new_count}."""
    from mil.harvester.sources.youtube import build_all_sources

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    counts: dict[str, int] = {}

    for src in build_all_sources(APPS_CONFIG, REPO_ROOT / ".env"):
        competitor = src.competitor.lower().replace(" ", "_")
        raw_dir = YOUTUBE_DIR / competitor
        raw_dir.mkdir(parents=True, exist_ok=True)

        existing_ids: set[str] = set()
        for f in raw_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for r in data.get("records", []):
                    cid = r.get("comment_id", "")
                    if cid:
                        existing_ids.add(cid)
            except Exception:
                pass

        logger.info("[fetch] %s — existing: %d comment IDs", competitor, len(existing_ids))

        try:
            raw = src.fetch()
        except Exception as exc:
            logger.warning("[fetch] %s — FAILED: %s", competitor, exc)
            counts[competitor] = 0
            continue

        new = [r for r in raw if r.get("comment_id", "") not in existing_ids]
        logger.info("[fetch] %s — %d fetched, %d new", competitor, len(raw), len(new))

        if not new:
            counts[competitor] = 0
            continue

        out = raw_dir / f"live_{timestamp}.json"
        out.write_text(
            json.dumps({
                "source": "youtube",
                "competitor": competitor,
                "fetch_timestamp": timestamp,
                "record_count": len(new),
                "records": new,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        counts[competitor] = len(new)
        logger.info("[fetch] %s — saved %d new -> %s", competitor, len(new), out.name)

    return counts


# ── Enrich (qwen3) ────────────────────────────────────────────────────────────

def _normalise(obj: dict) -> dict:
    issue = obj.get("issue_type", "Other")
    if issue not in ISSUE_TYPES:
        issue = "Other"
    journey = obj.get("customer_journey", "General App Use")
    if journey not in CUSTOMER_JOURNEYS:
        journey = "General App Use"
    try:
        sentiment = round(max(-1.0, min(1.0, float(obj.get("sentiment_score", 0.0)))), 3)
    except (TypeError, ValueError):
        sentiment = 0.0
    severity = obj.get("severity_class", "P2")
    if severity not in ("P0", "P1", "P2"):
        severity = "P2"
    if severity in ("P0", "P1") and issue not in BLOCKING_ISSUES:
        severity = "P2"
    if issue == "Positive Feedback":
        severity = "P2"
    return {
        "issue_type": issue,
        "customer_journey": journey,
        "sentiment_score": sentiment,
        "severity_class": severity,
        "reasoning": str(obj.get("reasoning", ""))[:300],
    }


def _is_enriched(r: dict) -> bool:
    v3_fields = {"issue_type", "customer_journey", "sentiment_score", "severity_class"}
    return (
        all(f in r for f in v3_fields)
        and r.get("severity_class") not in ("ENRICHMENT_FAILED", None)
        and r.get("issue_type") not in ("ENRICHMENT_FAILED", None)
    )


def _enrich_batch(client, records: list[dict], batch_id: str) -> list[dict]:
    import re
    lines = [
        f"{i+1}. {r.get('review', '')[:300]}"
        for i, r in enumerate(records)
    ]
    prompt = BATCH_PROMPT_TEMPLATE.format(
        issues=", ".join(ISSUE_TYPES),
        journeys=", ".join(CUSTOMER_JOURNEYS),
        comments="\n".join(lines),
    )
    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=ENRICH_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0,
                extra_body={"think": False},
            )
            raw = resp.choices[0].message.content.strip()
            break
        except Exception as exc:
            logger.warning("[enrich] %s attempt %d/3 failed: %s", batch_id, attempt, exc)
            if attempt < 3:
                time.sleep(3 * attempt)
    else:
        return []

    m = re.search(r"[\[\{]", raw)
    if not m:
        return []
    trimmed = raw[m.start(): max(raw.rfind("]"), raw.rfind("}")) + 1]
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            parsed = json.loads(repair_json(trimmed))
        except Exception:
            return []
    return parsed if isinstance(parsed, list) else [parsed]


def enrich_all() -> dict[str, int]:
    """Enrich raw YouTube comments with qwen3:14b. Returns {competitor: enriched_count}."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    client = OpenAI(base_url=OLLAMA_BASE, api_key="ollama")
    counts: dict[str, int] = {}

    for comp_dir in sorted(YOUTUBE_DIR.iterdir()):
        if not comp_dir.is_dir():
            continue
        competitor = comp_dir.name

        # Load all raw records
        raw_records = []
        for f in sorted(comp_dir.glob("live_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                raw_records.extend(data.get("records", []))
            except Exception as exc:
                logger.warning("[enrich] failed to read %s: %s", f, exc)

        if not raw_records:
            continue

        # Load existing enriched file
        enriched_file = ENRICHED_DIR / f"youtube_{competitor}_enriched.json"
        existing_enriched: list[dict] = []
        if enriched_file.exists():
            try:
                payload = json.loads(enriched_file.read_text(encoding="utf-8"))
                existing_enriched = payload.get("records", [])
            except Exception:
                pass

        enriched_ids = {r.get("comment_id", "") for r in existing_enriched if _is_enriched(r)}

        to_enrich = [r for r in raw_records if r.get("comment_id", "") not in enriched_ids]

        logger.info("[enrich] %s — %d existing, %d to enrich",
                    competitor, len(existing_enriched), len(to_enrich))

        if not to_enrich:
            counts[competitor] = 0
            continue

        freshly_enriched = []
        total_batches = (len(to_enrich) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(to_enrich), BATCH_SIZE):
            batch = to_enrich[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            batch_id = f"youtube_{competitor}_b{batch_num}"
            logger.info("[enrich] %s batch %d/%d (%d records)",
                        competitor, batch_num, total_batches, len(batch))
            results = _enrich_batch(client, batch, batch_id)
            for j, rec in enumerate(batch):
                enr = results[j] if j < len(results) else {}
                if enr:
                    freshly_enriched.append({**rec, **_normalise(enr)})
                else:
                    freshly_enriched.append({
                        **rec,
                        "issue_type": "ENRICHMENT_FAILED",
                        "customer_journey": "ENRICHMENT_FAILED",
                        "sentiment_score": 0.0,
                        "severity_class": "ENRICHMENT_FAILED",
                        "reasoning": "qwen3 batch failed",
                    })

        final = existing_enriched + freshly_enriched
        ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
        enriched_file.write_text(
            json.dumps({
                "source": "youtube",
                "competitor": competitor,
                "enriched_count": len(final),
                "model": ENRICH_MODEL,
                "schema_version": "v3",
                "records": final,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("[enrich] %s — wrote %d records (%d new)",
                    competitor, len(final), len(freshly_enriched))
        counts[competitor] = len(freshly_enriched)

    return counts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube daily data collection — MIL-22")
    parser.add_argument("--fetch-only",  action="store_true", help="Fetch and store raw only, skip enrichment")
    parser.add_argument("--enrich-only", action="store_true", help="Enrich existing raw only, skip fetch")
    args = parser.parse_args()

    logger.info("=== YouTube Collection — %s ===",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    if not args.enrich_only:
        logger.info("--- Fetch ---")
        fetch_counts = fetch_all()
        total = sum(fetch_counts.values())
        logger.info("Fetch complete — %d new comments across %d competitors",
                    total, len(fetch_counts))

    if not args.fetch_only:
        logger.info("--- Enrich (qwen3:14b) ---")
        enrich_counts = enrich_all()
        total = sum(enrich_counts.values())
        logger.info("Enrich complete — %d comments enriched", total)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
