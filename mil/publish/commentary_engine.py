#!/usr/bin/env python3
"""
mil/publish/commentary_engine.py — MIL-28

Sonnet-powered analyst commentary engine.

Reads the issue persistence log and benchmark cache, selects the most
significant Barclays issues, and calls Sonnet to produce analyst-grade
prose per issue type.

Returns a list of commentary dicts — publish_v3.py renders the HTML.

Selection rules:
  Over-indexed (risk):  gap_pp > 5pp OR (days_active > 3 AND gap_pp > 0) OR P0/P1
  Under-indexed (strength): gap_pp < -3pp (Barclays meaningfully better than peers)
  Max output: 3 risk boxes + 1 strength box = 4 total

Chronicle resonance: conditional — only surfaced when the issue type pattern
genuinely matches a CHR entry (keyword overlap >= 0.4). Not forced.
"""
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("commentary_engine")

MIL_ROOT         = Path(__file__).parent.parent
PERSISTENCE_LOG  = MIL_ROOT / "data" / "issue_persistence_log.jsonl"
ENRICHED_DIR     = MIL_ROOT / "data" / "historical" / "enriched"

sys.path.insert(0, str(MIL_ROOT))
sys.path.insert(0, str(MIL_ROOT.parent))


# ── Chronicle resonance map ───────────────────────────────────────────────────
# issue_types that have a natural Chronicle anchor — included in Sonnet prompt
# as optional context. Sonnet decides whether to reference it.

CHR_RESONANCE: dict[str, str] = {
    "App Not Opening":    "CHR-001 (TSB 2018): sustained app access failure preceded mass lockout. CHR-003 (HSBC 2025): app refresh outage caused login failures at scale.",
    "Login Failed":       "CHR-001 (TSB 2018): authentication failures at scale were the first visible signal of core banking collapse.",
    "Account Locked":     "CHR-001 (TSB 2018): mass account lockout was the defining customer impact of the migration failure.",
    "App Crashing":       "CHR-003 (HSBC 2025): app instability post-platform refresh — crashes and ERR03 errors persisted for weeks.",
    "Incorrect Balance":  "CHR-002 (Lloyds 2025): API defect caused transaction data to cross account boundaries. Incorrect balance reports are an early exposure indicator.",
    "Missing Transaction":"CHR-002 (Lloyds 2025): missing/crossed transactions were the customer-visible symptom of the Lloyds API defect.",
}


# ── Quote extraction ──────────────────────────────────────────────────────────

def _load_barclays_records() -> list[dict]:
    """Load all Barclays enriched records from app_store + google_play once."""
    records: list[dict] = []
    for source in ("app_store", "google_play"):
        f = ENRICHED_DIR / f"{source}_barclays_enriched.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            records.extend(data.get("records", []))
        except Exception:
            pass
    return records


def get_top_quotes(issue_type: str, n: int = 2, records: list[dict] | None = None) -> list[str]:
    """
    Return up to n customer quotes for an issue type from Barclays enriched records.
    Priority: P0 > P1 > P2. Length: 40-200 chars preferred.
    Pass pre-loaded records to avoid repeated file reads per call.
    """
    if records is None:
        records = _load_barclays_records()

    candidates: list[tuple[int, str]] = []
    for r in records:
        if r.get("issue_type") != issue_type:
            continue
        text = r.get("review") or r.get("content", "")
        if not text:
            continue
        text = text.strip().replace("\n", " ")
        if len(text) < 40:
            continue
        text = text[:200]
        sev = r.get("severity_class", "P2")
        priority = {"P0": 0, "P1": 1, "P2": 2}.get(sev, 2)
        candidates.append((priority, text))

    candidates.sort(key=lambda x: x[0])
    seen: set[str] = set()
    quotes: list[str] = []
    for _, text in candidates:
        if text not in seen:
            seen.add(text)
            quotes.append(text)
            if len(quotes) >= n:
                break
    return quotes


# ── Sonnet synthesis ──────────────────────────────────────────────────────────

def _call_sonnet(prompt: str) -> str:
    """Call Sonnet via model_client unified wrapper. Returns prose string."""
    try:
        from mil.config.model_client import call_anthropic
        from mil.config.get_model import get_model
        cfg = get_model("commentary")
        return call_anthropic(
            task="commentary",
            user_prompt=prompt,
            max_tokens=cfg.get("max_tokens", 300),
        )
    except Exception as exc:
        logger.warning("[commentary] Sonnet call failed: %s", exc)
        return ""


def _prose_risk(entry: dict, quotes: list[str], chr_context: str) -> str:
    """Generate analyst prose for an over-indexed (risk) issue."""
    quote_block = ""
    if quotes:
        quote_block = "\nCustomer evidence:\n" + "\n".join(f'  - "{q}"' for q in quotes)

    chr_block = f"\nChronicle context (use only if genuinely relevant): {chr_context}" if chr_context else ""

    prompt = f"""You are a senior banking app intelligence analyst writing a briefing for a Barclays product director.

Write exactly 3 sentences of analytical commentary about this signal. Follow this structure strictly:

Sentence 1 — INTRODUCE THE ISSUE: State what the issue is, how long it has been active, and its severity class. This is factual orientation — no analysis yet. Use the signal data directly.
Sentence 2 — ROOT CAUSE INFERENCE: State what the customer evidence implies about root cause. Be specific — what does the pattern rule out, and what does it point to?
Sentence 3 — BUSINESS RISK: State the business consequence if unresolved. Be direct about churn, regulatory, or reputational exposure.

SIGNAL DATA:
- Issue type: {entry['issue_type']} ({entry['category']})
- Barclays complaint rate: {entry['barclays_rate']:.1f}% of reviews
- Peer average: {entry['peer_avg_rate']:.1f}% (NatWest, Lloyds, HSBC, Monzo, Revolut)
- Over-index gap: +{entry['gap_pp']:.1f} percentage points above peers
- Severity: {entry['dominant_severity']}
- Consecutive days active: {entry['days_active']} days (first seen: {entry['first_seen']}){quote_block}{chr_block}

3 sentences only. Do not start with "Barclays". Do not use bullet points."""

    return _call_sonnet(prompt)


def _prose_strength(entry: dict) -> str:
    """Generate analyst prose for an under-indexed (strength) issue."""
    prompt = f"""You are a senior banking app intelligence analyst writing a briefing for a Barclays product director.

Write exactly 2 sentences about this competitive strength. First sentence: what Barclays is doing better than peers and by how much. Second sentence: what this means for customer retention or relationship depth. Be specific, not generic.

SIGNAL DATA:
- Issue type: {entry['issue_type']} ({entry['category']})
- Barclays complaint rate: {entry['barclays_rate']:.1f}%
- Peer average: {entry['peer_avg_rate']:.1f}%
- Barclays advantage: {abs(entry['gap_pp']):.1f}pp below peer average

2 sentences only."""

    return _call_sonnet(prompt)


# ── Issue selection ───────────────────────────────────────────────────────────

def _is_significant_risk(entry: dict) -> bool:
    """True if the over-indexed issue warrants a commentary box."""
    if not entry.get("over_indexed"):
        return False
    gap   = entry["gap_pp"]
    days  = entry["days_active"]
    sev   = entry["dominant_severity"]
    return gap > 5.0 or (days > 3 and gap > 0) or sev in ("P0", "P1")


def _is_significant_strength(entry: dict) -> bool:
    """True if the under-indexed issue warrants a strength box."""
    return (
        not entry.get("over_indexed")
        and entry["barclays_rate"] > 0
        and entry["gap_pp"] < -3.0
    )


def _churn_contribution(entry: dict) -> float:
    """Score for sorting risk entries by churn contribution."""
    sw = {"P0": 3.0, "P1": 2.0, "P2": 1.0}.get(entry.get("dominant_severity", "P2"), 1.0)
    pm = min(1.0 + 0.2 * entry.get("days_active", 1), 3.0)
    return entry["gap_pp"] * sw * pm


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_commentary(today: str | None = None) -> list[dict]:
    """
    Read today's persistence log entries, select significant issues,
    call Sonnet per issue, return list of commentary dicts.

    Each dict contains:
      type, issue_type, category, barclays_rate, peer_avg_rate, gap_pp,
      dominant_severity, days_active, first_seen, prose, top_quotes, chr_resonance
    """
    if not PERSISTENCE_LOG.exists():
        logger.warning("[commentary] persistence log not found — skipping")
        return []

    # Load today's entries
    all_entries = []
    for line in PERSISTENCE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                all_entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Default to latest date in log
    if not today:
        dates = sorted(set(e["date"] for e in all_entries), reverse=True)
        today = dates[0] if dates else ""

    today_entries = [e for e in all_entries if e["date"] == today]
    if not today_entries:
        logger.warning("[commentary] no entries for date=%s", today)
        return []

    # Select risk issues (over-indexed), sorted by churn contribution
    risk_entries = [e for e in today_entries if _is_significant_risk(e)]
    risk_entries.sort(key=_churn_contribution, reverse=True)
    risk_entries = risk_entries[:3]

    # Select top strength (most under-indexed)
    strength_entries = [e for e in today_entries if _is_significant_strength(e)]
    strength_entries.sort(key=lambda e: e["gap_pp"])  # most negative first
    strength_entries = strength_entries[:1]

    results: list[dict] = []

    # Load Barclays records once — reused across all get_top_quotes calls
    _barclays_records = _load_barclays_records()

    # Generate risk commentaries
    for entry in risk_entries:
        issue = entry["issue_type"]
        quotes = get_top_quotes(issue, n=2, records=_barclays_records)
        chr_context = CHR_RESONANCE.get(issue, "")
        logger.info("[commentary] generating risk prose for '%s' (gap=+%.1fpp, %dd, %s)",
                    issue, entry["gap_pp"], entry["days_active"], entry["dominant_severity"])
        prose = _prose_risk(entry, quotes, chr_context)
        if not prose:
            prose = f"{issue} is running {entry['gap_pp']:.1f}pp above the peer average and has persisted for {entry['days_active']} consecutive days."

        results.append({
            "type":              "risk",
            "issue_type":        issue,
            "category":          entry["category"],
            "barclays_rate":     entry["barclays_rate"],
            "peer_avg_rate":     entry["peer_avg_rate"],
            "gap_pp":            entry["gap_pp"],
            "dominant_severity": entry["dominant_severity"],
            "days_active":       entry["days_active"],
            "first_seen":        entry["first_seen"],
            "prose":             prose,
            "top_quotes":        quotes,
            "chr_resonance":     chr_context,
        })

    # Generate strength commentary
    for entry in strength_entries:
        issue = entry["issue_type"]
        quotes = get_top_quotes(issue, n=1, records=_barclays_records)
        logger.info("[commentary] generating strength prose for '%s' (gap=%.1fpp)",
                    issue, entry["gap_pp"])
        prose = _prose_strength(entry)
        if not prose:
            prose = f"Barclays is {abs(entry['gap_pp']):.1f}pp below the peer average on {issue} — a meaningful competitive advantage."

        results.append({
            "type":              "strength",
            "issue_type":        issue,
            "category":          entry["category"],
            "barclays_rate":     entry["barclays_rate"],
            "peer_avg_rate":     entry["peer_avg_rate"],
            "gap_pp":            entry["gap_pp"],
            "dominant_severity": entry["dominant_severity"],
            "days_active":       entry.get("days_active", 0),
            "first_seen":        entry.get("first_seen", ""),
            "prose":             prose,
            "top_quotes":        quotes,
            "chr_resonance":     "",
        })

    logger.info("[commentary] generated %d boxes (%d risk, %d strength)",
                len(results),
                sum(1 for r in results if r["type"] == "risk"),
                sum(1 for r in results if r["type"] == "strength"))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    boxes = generate_commentary()
    for box in boxes:
        print(f"\n{'='*60}")
        print(f"[{box['type'].upper()}] {box['issue_type']} | {box['dominant_severity']} | {box['days_active']}d | gap={box['gap_pp']:+.1f}pp")
        print(f"{box['prose']}")
        if box["top_quotes"]:
            print(f'Quote: "{box["top_quotes"][0]}"')
