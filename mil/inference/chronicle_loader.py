"""
mil/inference/chronicle_loader.py

Parses mil/CHRONICLE.md at startup and returns inference-ready CHRONICLE_ENTRIES.

Fixes the maintenance trap: approved CHR entries live in CHRONICLE.md (the canonical
ledger). Previously mil_agent.py had 4 entries hardcoded while CHRONICLE.md had 19
approved. This loader ensures every inference_approved=true entry is automatically
available — no code change required when Hussain approves a new CHR entry.

Field mapping:
  CHR-001/002/003/004 — have pattern_keywords + pattern_description (rich, formal)
  CHR-005 to CHR-019  — have summary + signal_summary.top_keywords (derived)

Journey tags for CHR-005+ derived from incident_type via INCIDENT_JOURNEY_MAP.
Explicit journey_tags in YAML always take precedence.
"""
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

CHRONICLE_MD = Path(__file__).parent.parent / "CHRONICLE.md"

# incident_type → journey tags for entries that don't declare them explicitly
INCIDENT_JOURNEY_MAP: dict[str, list[str]] = {
    "core_banking_migration_failure":    ["J_LOGIN_01", "J_PAY_01", "J_SERVICE_01"],
    "api_defect_data_exposure":          ["J_SERVICE_01", "J_LOGIN_01"],
    "app_platform_refresh_outage":       ["J_LOGIN_01", "J_SERVICE_01"],
    "app_friction_pattern_analysis":     ["J_LOGIN_01", "J_SERVICE_01", "J_PAY_01"],
    "login_regression":                  ["J_LOGIN_01"],
    "payment_failure_cluster":           ["J_PAY_01"],
    "app_friction_pattern":              ["J_SERVICE_01"],
    "account_access_friction_pattern":   ["J_SERVICE_01"],
}


def _parse_yaml_blocks(text: str) -> list[dict]:
    """Extract and parse all ```yaml ... ``` blocks from CHRONICLE.md."""
    # \r?\n handles both Unix and Windows line endings
    blocks = re.findall(r"```yaml\r?\n(.*?)\r?\n```", text, re.DOTALL)
    parsed = []
    for block in blocks:
        try:
            obj = yaml.safe_load(block)
            if isinstance(obj, dict):
                parsed.append(obj)
        except Exception as exc:
            logger.warning("[chronicle_loader] YAML parse error (block skipped): %s", exc)
    return parsed


def _normalise_journey_tags(raw) -> list[str]:
    """Normalise journey_tags: strip YAML inline comments, deduplicate."""
    if not raw:
        return []
    tags = []
    for item in raw:
        # 'J_LOGIN_01       # comment' → 'J_LOGIN_01'
        tag = str(item).strip().split()[0]
        if tag.startswith("J_"):
            tags.append(tag)
    return list(dict.fromkeys(tags))


def _build_entry(parsed: dict) -> Optional[dict]:
    """Convert a parsed YAML block to a CHRONICLE_ENTRIES-compatible dict."""
    cid = str(parsed.get("chronicle_id", ""))
    if not cid.startswith("CHR-"):
        return None
    if not parsed.get("inference_approved"):
        return None

    incident_type = str(parsed.get("incident_type", ""))

    # Journey tags: explicit YAML field takes precedence, else derive from incident_type
    raw_tags = parsed.get("journey_tags")
    if raw_tags:
        journey_tags = _normalise_journey_tags(raw_tags)
    else:
        journey_tags = INCIDENT_JOURNEY_MAP.get(incident_type, ["J_SERVICE_01"])

    # pattern_description: prefer explicit field > summary > pattern_signals + mil_relevance
    pattern_description = str(
        parsed.get("pattern_description") or parsed.get("summary") or ""
    )
    if not pattern_description:
        parts: list[str] = []
        for ps in (parsed.get("pattern_signals") or [])[:4]:
            parts.append(str(ps))
        for mr in (parsed.get("mil_relevance") or [])[:2]:
            parts.append(str(mr))
        it_str = str(incident_type).replace("_", " ")
        if it_str:
            parts.append(it_str)
        bank_str = str(parsed.get("bank", ""))
        if bank_str:
            parts.append(f"{bank_str} banking app failure")
        pattern_description = " ".join(parts)

    # pattern_keywords: prefer explicit field > signal_summary.top_keywords > causal_chain words
    pattern_keywords = parsed.get("pattern_keywords")
    if not pattern_keywords:
        signal_summary = parsed.get("signal_summary", {})
        if isinstance(signal_summary, dict):
            pattern_keywords = signal_summary.get("top_keywords", [])
    if not pattern_keywords:
        # Derive short keyword list from causal_chain
        chain = parsed.get("causal_chain") or []
        words: list[str] = []
        for step in chain[:6]:
            for w in str(step).lower().split():
                w = w.strip(".,;:()")
                if len(w) > 4 and w not in ("their", "which", "these", "after", "since",
                                             "while", "until", "about", "could", "would"):
                    words.append(w)
        # Deduplicate, take top 12 by frequency
        from collections import Counter
        pattern_keywords = [w for w, _ in Counter(words).most_common(12)]
    pattern_keywords = [str(k) for k in (pattern_keywords or [])]

    confidence_cap = float(parsed.get("confidence_score", 1.0))

    return {
        "chronicle_id":      cid,
        "bank":              str(parsed.get("bank", "")),
        "incident_type":     incident_type,
        "inference_approved": True,
        "confidence_cap":    confidence_cap,
        "journey_tags":      journey_tags,
        "pattern_keywords":  pattern_keywords,
        "pattern_description": pattern_description,
    }


@lru_cache(maxsize=1)
def load_chronicle_entries() -> list[dict]:
    """
    Load all inference_approved=True CHRONICLE entries from mil/CHRONICLE.md.
    Result is cached — file is read once per process.
    """
    if not CHRONICLE_MD.exists():
        logger.error("[chronicle_loader] CHRONICLE.md not found at %s", CHRONICLE_MD)
        return []

    text = CHRONICLE_MD.read_text(encoding="utf-8")
    blocks = _parse_yaml_blocks(text)

    entries = []
    skipped = []
    for block in blocks:
        entry = _build_entry(block)
        if entry:
            entries.append(entry)
        elif block.get("chronicle_id", "").startswith("CHR-"):
            skipped.append(block.get("chronicle_id"))

    entries.sort(key=lambda e: e["chronicle_id"])

    if skipped:
        logger.info("[chronicle_loader] %d CHR entries skipped (inference_approved=false): %s",
                    len(skipped), skipped)
    logger.info("[chronicle_loader] Loaded %d inference-approved CHRONICLE entries: %s",
                len(entries), [e["chronicle_id"] for e in entries])

    MIN_EXPECTED = 15
    if len(entries) < MIN_EXPECTED:
        raise RuntimeError(
            f"[chronicle_loader] Only {len(entries)} CHRONICLE entries loaded — "
            f"expected at least {MIN_EXPECTED}. Check CHRONICLE.md for malformed YAML blocks."
        )
    return entries


def reload() -> list[dict]:
    """Force reload (clears lru_cache). Useful in tests."""
    load_chronicle_entries.cache_clear()
    return load_chronicle_entries()
