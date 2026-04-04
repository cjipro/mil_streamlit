"""
collect_cityam.py — City A.M. + Financial Times RSS daily collection. MIL-18.

Standalone script. Runs independently from run_daily.py.
Purpose: capture banking news signals from editorial sources.

  Fetch   — RSS feeds: cityam.com/feed/ + ft.com/rss/home/uk
  Filter  — competitor mention + banking relevance keywords
  Dedup   — on article_id (sha256 of URL), never stores duplicates
  Store   — mil/data/historical/city_am/{competitor}/live_TIMESTAMP.json
  Enrich  — claude-haiku-4-5-20251001 (Haiku) via Anthropic API
            Trust weight: 0.90 — editorial verification adds signal weight

Note: FT articles are paywalled but RSS headlines/summaries are public.
      Signal is in the headline — full article text not required.

Usage:
  py mil/collect_cityam.py                # fetch + enrich
  py mil/collect_cityam.py --fetch-only   # fetch and store raw, skip enrichment
  py mil/collect_cityam.py --enrich-only  # enrich existing raw, skip fetch

Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("collect_cityam")

REPO_ROOT     = Path(__file__).parent.parent
MIL_ROOT      = Path(__file__).parent
APPS_CONFIG   = MIL_ROOT / "config" / "apps_config.yaml"
HIST_BASE     = MIL_ROOT / "data" / "historical"
NEWS_DIR      = HIST_BASE / "city_am"
ENRICHED_DIR  = HIST_BASE / "enriched"

sys.path.insert(0, str(REPO_ROOT))

ENRICH_MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE   = 10

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
BLOCKING_ISSUES = {
    "App Not Opening", "Login Failed", "Payment Failed",
    "Transfer Failed", "Account Locked", "App Crashing",
}
SYSTEM_PROMPT = (
    "You are a banking technology news analyst. "
    "Output MUST be a valid JSON array only. "
    "No preamble, no markdown, no explanation outside the JSON."
)
BATCH_PROMPT_TEMPLATE = """Classify each numbered banking news headline/summary. Return a JSON array with one object per article.

Each object must have exactly these fields:
- issue_type: what went wrong or what the article is about. One of: {issues}
- customer_journey: what customer journey is affected. One of: {journeys}
- sentiment_score: number from -1.0 (very negative) to 1.0 (very positive)
- severity_class: P0, P1, or P2 using these rules:
    P0 = major outage or system failure reported (bank down, payments failed at scale)
    P1 = significant issue reported (IT disruption, service degradation, regulatory action)
    P2 = general news, minor issue, or positive coverage
- reasoning: one sentence explaining the classification

Articles:
{articles}"""


def _make_article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _parse_date(entry) -> str:
    """Extract ISO date from feedparser entry. Falls back to today."""
    try:
        import time as _time
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:3]).strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_review_text(entry: dict) -> str:
    title   = entry.get("title", "").strip()
    summary = entry.get("summary", "").strip()
    # Strip HTML tags from summary
    import re
    summary = re.sub(r"<[^>]+>", " ", summary)
    summary = re.sub(r"\s+", " ", summary).strip()[:400]
    if summary:
        return f"{title}. {summary}"
    return title


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_all() -> dict[str, int]:
    """Fetch RSS articles for all active competitors. Returns {competitor: new_count}."""
    from mil.harvester.sources.ft_cityam import build_all_sources

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    counts: dict[str, int] = {}

    for src in build_all_sources(APPS_CONFIG):
        competitor = src.competitor.lower().replace(" ", "_")
        raw_dir = NEWS_DIR / competitor
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Load existing article_ids for dedup
        existing_ids: set[str] = set()
        for f in raw_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for r in data.get("records", []):
                    aid = r.get("article_id", "")
                    if aid:
                        existing_ids.add(aid)
            except Exception:
                pass

        logger.info("[fetch] %s — existing: %d article IDs", competitor, len(existing_ids))

        try:
            raw_entries = src.fetch()
            filtered    = src.parse(raw_entries)
        except Exception as exc:
            logger.warning("[fetch] %s — FAILED: %s", competitor, exc)
            counts[competitor] = 0
            continue

        # Convert to enrichment-compatible records
        records = []
        for entry in filtered:
            url = entry.get("link", "")
            aid = _make_article_id(url) if url else _make_article_id(entry.get("title", ""))
            records.append({
                "review":        _build_review_text(entry),
                "rating":        None,
                "author":        entry.get("feed_source", "ft_cityam"),
                "date":          _parse_date(entry),
                "article_id":    aid,
                "title":         entry.get("title", ""),
                "url":           url,
                "feed_source":   entry.get("feed_source", ""),
                "published":     entry.get("published", ""),
                "source":        "city_am",
                "competitor":    competitor,
            })

        new = [r for r in records if r.get("article_id", "") not in existing_ids]
        logger.info("[fetch] %s — %d matched, %d new", competitor, len(records), len(new))

        if not new:
            counts[competitor] = 0
            continue

        out = raw_dir / f"live_{timestamp}.json"
        out.write_text(
            json.dumps({
                "source":          "city_am",
                "competitor":      competitor,
                "fetch_timestamp": timestamp,
                "record_count":    len(new),
                "records":         new,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        counts[competitor] = len(new)
        logger.info("[fetch] %s — saved %d new -> %s", competitor, len(new), out.name)

    return counts


# ── Enrich (Haiku) ────────────────────────────────────────────────────────────

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
        "issue_type":       issue,
        "customer_journey": journey,
        "sentiment_score":  sentiment,
        "severity_class":   severity,
        "reasoning":        str(obj.get("reasoning", ""))[:300],
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
        f"{i+1}. {r.get('review', '')[:400]}"
        for i, r in enumerate(records)
    ]
    prompt = BATCH_PROMPT_TEMPLATE.format(
        issues=", ".join(ISSUE_TYPES),
        journeys=", ".join(CUSTOMER_JOURNEYS),
        articles="\n".join(lines),
    )
    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=ENRICH_MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
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
    """Enrich raw news articles with Haiku. Returns {competitor: enriched_count}."""
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        import os
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    client = anthropic.Anthropic(api_key=api_key)
    counts: dict[str, int] = {}

    for comp_dir in sorted(NEWS_DIR.iterdir()):
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
        enriched_file = ENRICHED_DIR / f"city_am_{competitor}_enriched.json"
        existing_enriched: list[dict] = []
        if enriched_file.exists():
            try:
                payload = json.loads(enriched_file.read_text(encoding="utf-8"))
                existing_enriched = payload.get("records", [])
            except Exception:
                pass

        enriched_ids = {r.get("article_id", "") for r in existing_enriched if _is_enriched(r)}
        to_enrich = [r for r in raw_records if r.get("article_id", "") not in enriched_ids]

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
            batch_id = f"city_am_{competitor}_b{batch_num}"
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
                        "issue_type":       "ENRICHMENT_FAILED",
                        "customer_journey": "ENRICHMENT_FAILED",
                        "sentiment_score":  0.0,
                        "severity_class":   "ENRICHMENT_FAILED",
                        "reasoning":        "haiku batch failed",
                    })

        final = existing_enriched + freshly_enriched
        ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
        enriched_file.write_text(
            json.dumps({
                "source":         "city_am",
                "competitor":     competitor,
                "enriched_count": len(final),
                "model":          ENRICH_MODEL,
                "schema_version": "v3",
                "records":        final,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("[enrich] %s — wrote %d records (%d new)",
                    competitor, len(final), len(freshly_enriched))
        counts[competitor] = len(freshly_enriched)

    return counts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="City A.M. + FT RSS collection — MIL-18")
    parser.add_argument("--fetch-only",  action="store_true", help="Fetch and store raw only, skip enrichment")
    parser.add_argument("--enrich-only", action="store_true", help="Enrich existing raw only, skip fetch")
    args = parser.parse_args()

    logger.info("=== City A.M. Collection — %s ===",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    if not args.enrich_only:
        logger.info("--- Fetch ---")
        fetch_counts = fetch_all()
        total = sum(fetch_counts.values())
        logger.info("Fetch complete — %d new articles across %d competitors",
                    total, len(fetch_counts))

    if not args.fetch_only:
        logger.info("--- Enrich (Haiku) ---")
        enrich_counts = enrich_all()
        total = sum(enrich_counts.values())
        logger.info("Enrich complete — %d articles enriched", total)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
