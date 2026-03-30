"""
mil_agent.py -- MIL Core RAG-first Inference Engine (MIL-8)

Reads enriched records from mil/data/historical/enriched/
Aggregates signal clusters by (competitor, journey_attribution)
Performs RAG against CHRONICLE entries for historical pattern matching
Computes CAC scores per MIL_SCHEMA.yaml formula
Calls Refuel-8B for finding narrative and blind_spots
Writes structured findings to mil/outputs/mil_findings.json

Vault chain (per ARCH-001):
  1. Polars transformation     <- done during harvest
  2. Refuel-8B enrichment      <- done in qwen_enrichment.py
  3. DuckDB analytical cache   <- mil_vault.db
  4. HDFS Port 9871 anchoring  <- vault_sync.py
  5. CAC inference + RAG       <- THIS FILE (produces mil_findings.json)

CAC Formula: C_mil = (alpha * Vol_sig + beta * Sim_hist) / (delta * Delta_tel + 1)
  Starting weights: alpha=0.40, beta=0.40, delta=0.20 (not tuned before Day 30)

Designed Ceiling Rule:
  When CAC > DESIGNED_CEILING_THRESHOLD and Delta_tel = 0 (no internal
  telemetry available), output:
  "To confirm this I require internal HDFS telemetry data. Request Phase 2."

Article Zero: This system shall prioritise the expression of its own ignorance
over the delivery of any unverified certainty.

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MIL_ROOT     = Path(__file__).parent.parent
ENRICHED_DIR = MIL_ROOT / "data" / "historical" / "enriched"
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"

# CAC formula weights -- NOT tuned before Day 30 per MIL_SCHEMA.yaml
ALPHA = 0.40
BETA  = 0.40
DELTA = 0.20

# Designed Ceiling: trigger above this CAC when telemetry is absent
DESIGNED_CEILING_THRESHOLD = 0.45

# Minimum cluster size to generate a finding (P2 and above require >= 2 signals)
MIN_CLUSTER_SIZE_P2 = 2
MIN_CLUSTER_SIZE_P0 = 1  # Single P0 signal is worth flagging

# Refuel-8B config (same as qwen_enrichment.py per ARCH-001)
OLLAMA_URL      = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_MODEL    = "michaelborck/refuled:latest"
CLASS_VER       = "michaelborck/refuled:latest"
TEACHER_VER     = None      # MIL-7 not yet built -- explicitly None
REQUEST_TIMEOUT = 120
MAX_RETRIES     = 2

# Severity volume multipliers per MIL_SCHEMA.yaml signal_severity
SEV_MULTIPLIER = {"P0": 2.0, "P1": 1.5, "P2": 1.0, "ENRICHMENT_FAILED": 0.0}

# Journey attribution -> journey_id taxonomy (MIL_SCHEMA.yaml journey_ids)
JOURNEY_MAP = {
    "login":              "J_LOGIN_01",
    "payments":           "J_PAY_01",
    "onboarding":         "J_ONBOARD_01",
    "account_management": "J_SERVICE_01",
    "app_performance":    "J_SERVICE_01",
    "other":              None,
    "ENRICHMENT_FAILED":  None,
}

# Clark tier mapping on CAC score
CLARK_TIER = {
    (0.60, 1.01): "P1",
    (0.40, 0.60): "P2",
    (0.00, 0.40): "P3",
}

# CHRONICLE entries -- structured for RAG matching
# Source: mil/CHRONICLE.md (immutable ledger)
# Only inference_approved=True entries may anchor findings.
# CHR-002 cap: confidence_score <= 0.60
CHRONICLE_ENTRIES = [
    {
        "chronicle_id": "CHR-001",
        "bank": "TSB Bank",
        "incident_type": "core_banking_migration_failure",
        "inference_approved": True,
        "confidence_cap": 1.0,
        "journey_tags": ["J_LOGIN_01", "J_PAY_01", "J_SERVICE_01"],
        "pattern_keywords": [
            "locked out", "cannot access", "account access", "authentication",
            "login", "payments", "blocked", "error", "failed", "down",
            "unavailable", "outage", "crash", "cannot log in", "cannot sign in",
            "not working", "access denied", "migration",
        ],
        "pattern_description": (
            "Core banking migration failure. 1.9M customers locked out. "
            "Classic Vane pattern: stable internal metrics, catastrophic customer reality. "
            "Big bang migration + complaint spike + authentication failures."
        ),
    },
    {
        "chronicle_id": "CHR-002",
        "bank": "Lloyds Banking Group",
        "incident_type": "api_defect_data_exposure",
        "inference_approved": True,
        "confidence_cap": 0.60,     # APPROVED WITH CAP -- Hussain 2026-03-28
        "journey_tags": ["J_SERVICE_01", "J_LOGIN_01"],
        "pattern_keywords": [
            "wrong account", "wrong transactions", "other customer", "data",
            "transaction", "update", "software update", "defect", "api",
            "exposed", "visible", "balance", "account details", "incorrect",
            "someone else", "another account",
        ],
        "pattern_description": (
            "API defect after overnight software update. Transaction data crossed "
            "account boundaries. Same-day resolution but exposure already occurred. "
            "API layer defect pattern -- post-update complaints, data visibility issues."
        ),
    },
    {
        "chronicle_id": "CHR-003",
        "bank": "HSBC UK",
        "incident_type": "app_online_banking_outage",
        "inference_approved": False,    # INFERENCE HOLD
        "confidence_cap": 0.40,
        "journey_tags": ["J_LOGIN_01", "J_SERVICE_01"],
        "pattern_keywords": [
            "error", "cannot access", "app down", "not working", "unavailable",
            "login", "err03", "information unavailable", "outage", "authentication",
            "cannot log in", "access failed",
        ],
        "pattern_description": (
            "INFERENCE HOLD -- root cause unconfirmed. App and online banking outage. "
            "ERR03 error pattern. DownDetector as first mover. ~5 hour duration."
        ),
    },
    {
        "chronicle_id": "CHR-004",
        "bank": "Barclays",
        "incident_type": "app_friction_pattern_analysis",
        "inference_approved": False,    # Pending enrichment re-run
        "confidence_cap": 0.50,
        "journey_tags": ["J_LOGIN_01", "J_SERVICE_01", "J_PAY_01"],
        "pattern_keywords": [
            "cards", "crash", "my cards", "pin", "card access", "payment",
            "authorisation", "otp", "2fa", "cannot access", "crashing",
            "cards section", "barclays",
        ],
        "pattern_description": (
            "inference_approved: false -- enrichment re-run required. "
            "Cards section crash cluster (v8.20.1). Payment auth loop. OTP failure."
        ),
    },
]


# ============================================================
# REFUEL AVAILABILITY CHECK
# ============================================================

def _check_refuel() -> bool:
    """Return True if Refuel-8B is reachable via Ollama."""
    try:
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        tags = resp.json().get("models", [])
        model_names = [t.get("name", "") for t in tags]
        # Accept if any tag starts with 'michaelborck/refuled'
        return any("refuled" in n for n in model_names)
    except Exception:
        return False


# ============================================================
# DATA LOADING
# ============================================================

def load_enriched_records() -> dict[str, list[dict]]:
    """
    Load all enriched JSON files from ENRICHED_DIR.
    Returns {competitor_key: [records]}.
    competitor_key = '{source}_{competitor}' e.g. 'google_play_barclays'
    """
    data = {}
    files = sorted(ENRICHED_DIR.glob("*.json"))
    if not files:
        logger.warning("[MILAgent] No enriched files found in %s", ENRICHED_DIR)
        return data

    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            key = f"{payload.get('source', 'unknown')}_{payload.get('competitor', 'unknown')}"
            records = payload.get("records", [])
            data[key] = records
            logger.info("[MILAgent] Loaded %d records from %s (%s)", len(records), f.name, key)
        except Exception as exc:
            logger.error("[MILAgent] Failed to read %s: %s", f.name, exc)

    return data


# ============================================================
# RAG LAYER
# ============================================================

def _keyword_overlap(signal_keywords: list[str], chronicle_keywords: list[str]) -> float:
    """
    Compute keyword overlap similarity score [0.0, 1.0].
    Case-insensitive substring match: a signal keyword 'hits' if it appears
    in any CHRONICLE keyword or vice versa.
    """
    if not signal_keywords or not chronicle_keywords:
        return 0.0

    sig_lower   = [k.lower() for k in signal_keywords]
    chron_lower = [k.lower() for k in chronicle_keywords]

    hits = 0
    for sk in sig_lower:
        for ck in chron_lower:
            if sk in ck or ck in sk:
                hits += 1
                break   # count each signal keyword once

    return min(hits / len(chronicle_keywords), 1.0)


def find_best_chronicle_match(
    journey_id: Optional[str],
    signal_keywords: list[str],
) -> tuple[Optional[dict], float]:
    """
    Find the highest-similarity CHRONICLE entry for a given journey_id + keywords.
    Only considers inference_approved=True entries.

    Returns (best_entry_or_None, sim_hist_score).
    Returns (None, 0.0) if no approved match found -- caller must treat as
    NO_CHRONICLE_MATCH (finding will be UNANCHORED per schema rules).
    """
    best_entry = None
    best_score = 0.0

    for entry in CHRONICLE_ENTRIES:
        if not entry["inference_approved"]:
            continue

        # Journey tag overlap
        if journey_id and journey_id not in entry["journey_tags"]:
            continue    # Hard filter: journey must match

        # Keyword overlap score
        kw_score = _keyword_overlap(signal_keywords, entry["pattern_keywords"])
        if kw_score > best_score:
            best_score = kw_score
            best_entry = entry

    return best_entry, best_score


# ============================================================
# CAC FORMULA
# ============================================================

def compute_vol_sig(cluster: list[dict], total_competitor_records: int) -> float:
    """
    Vol_sig = weighted signal volume, normalized to [0.0, 1.0].
    P0 signals carry 2x weight, P1 1.5x, P2 1.0x (per MIL_SCHEMA.yaml).
    ENRICHMENT_FAILED records contribute 0 weight.
    """
    if total_competitor_records == 0:
        return 0.0

    weighted = sum(
        SEV_MULTIPLIER.get(r.get("severity_class", "P2"), 1.0)
        for r in cluster
    )
    # Normalize: max possible weight if all were P0 (2x) over total
    # Use modest normalization -- cap at 1.0
    raw = weighted / max(total_competitor_records, 1)
    return min(raw * 5.0, 1.0)   # x5 amplifier so realistic cluster sizes register


def compute_cac(vol_sig: float, sim_hist: float, delta_tel: float = 0.0) -> float:
    """
    C_mil = (alpha * Vol_sig + beta * Sim_hist) / (delta * Delta_tel + 1)

    delta_tel = 0.0 means no internal telemetry available.
    When delta_tel = 0: denominator = 1, so CAC = alpha * Vol_sig + beta * Sim_hist.
    When delta_tel > 0: higher Vane gap lowers confidence (denominator > 1).
    """
    numerator   = (ALPHA * vol_sig) + (BETA * sim_hist)
    denominator = (DELTA * delta_tel) + 1.0
    return round(numerator / denominator, 4)


def _clark_tier(cac: float) -> str:
    if cac >= 0.60:
        return "P1"
    if cac >= 0.40:
        return "P2"
    return "P3"


# ============================================================
# REFUEL-8B INFERENCE CALL
# ============================================================

REFUEL_SYSTEM_PROMPT = (
    "You are a data-only agent. "
    "Output MUST be a valid JSON object. "
    "No preamble, no markdown code blocks, no explanation."
)

REFUEL_FINDING_TEMPLATE = (
    "A banking app signal cluster has been detected. Analyse it and output a JSON object.\n"
    "Required keys:\n"
    "  blind_spots: list of 3 to 5 strings -- things this system CANNOT confirm from public data alone\n"
    "  finding_summary: one sentence describing the finding (max 30 words)\n"
    "  failure_mode: one of NONE / SILENCE / CONTRADICTION / NO_CHRONICLE_MATCH\n\n"
    "Cluster data:\n{cluster_summary}"
)


def _repair_json_object(raw: str) -> dict:
    """Strip preamble and attempt to parse a JSON object from Refuel response."""
    m = re.search(r"\{", raw)
    if not m:
        raise ValueError(f"No JSON object start in: {raw[:150]}")
    start = m.start()
    last_close = raw.rfind("}")
    if last_close == -1:
        raise ValueError(f"No JSON object end in: {raw[:150]}")
    trimmed = raw[start: last_close + 1]
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json  # type: ignore
        return json.loads(repair_json(trimmed))
    except Exception as exc:
        raise ValueError(f"json_repair failed: {exc}")


def call_refuel_for_finding(
    competitor: str,
    journey_id: Optional[str],
    severity_summary: dict,
    top_keywords: list[str],
    chronicle_id: Optional[str],
    refuel_available: bool,
) -> dict:
    """
    Ask Refuel-8B for blind_spots, finding_summary, and failure_mode.

    If Refuel is unavailable, return a deterministic fallback derived from
    the cluster data (Article Zero: never fabricate -- always state the gap).
    """
    cluster_summary = (
        f"Competitor: {competitor}\n"
        f"Journey: {journey_id or 'unknown'}\n"
        f"Signal counts -- P0: {severity_summary.get('P0', 0)}, "
        f"P1: {severity_summary.get('P1', 0)}, P2: {severity_summary.get('P2', 0)}\n"
        f"Top keywords: {', '.join(top_keywords[:5])}\n"
        f"CHRONICLE anchor: {chronicle_id or 'NONE -- NO_CHRONICLE_MATCH'}"
    )

    if not refuel_available:
        logger.warning("[MILAgent] Refuel unavailable -- using deterministic fallback for %s %s",
                       competitor, journey_id)
        return _deterministic_fallback(competitor, journey_id, severity_summary, chronicle_id)

    prompt = REFUEL_FINDING_TEMPLATE.format(cluster_summary=cluster_summary)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": REFUEL_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
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
            logger.warning("[MILAgent] Refuel attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)
    else:
        logger.error("[MILAgent] Refuel exhausted retries: %s -- using fallback", last_exc)
        return _deterministic_fallback(competitor, journey_id, severity_summary, chronicle_id)

    raw = resp.json()["choices"][0]["message"]["content"].strip()
    try:
        parsed = _repair_json_object(raw)
        return {
            "blind_spots":      parsed.get("blind_spots", []),
            "finding_summary":  parsed.get("finding_summary", ""),
            "failure_mode":     parsed.get("failure_mode", "NONE"),
            "refuel_called":    True,
        }
    except ValueError as exc:
        logger.warning("[MILAgent] Refuel JSON repair failed (%s) -- using fallback", exc)
        return _deterministic_fallback(competitor, journey_id, severity_summary, chronicle_id)


def _deterministic_fallback(
    competitor: str,
    journey_id: Optional[str],
    severity_summary: dict,
    chronicle_id: Optional[str],
) -> dict:
    """
    Article Zero fallback when Refuel is unavailable.
    Generates honest, minimal blind_spots from structural data.
    Never fabricates -- always states what cannot be confirmed.
    """
    blind_spots = [
        f"Internal {competitor} telemetry unavailable -- cannot confirm actual error rate",
        "Review volume is public-only -- silent failures not captured",
        "Model-generated narrative not available -- Refuel-8B unreachable",
    ]
    if chronicle_id is None:
        blind_spots.append("No approved CHRONICLE anchor -- finding is UNANCHORED, cannot reach Morning Briefing")

    p0 = severity_summary.get("P0", 0)
    p1 = severity_summary.get("P1", 0)
    summary = (
        f"Signal cluster detected on {competitor} {journey_id or 'unknown journey'}: "
        f"{p0} P0 and {p1} P1 signals. CHRONICLE anchor: {chronicle_id or 'NONE'}."
    )
    return {
        "blind_spots":    blind_spots,
        "finding_summary": summary,
        "failure_mode":   "NONE" if chronicle_id else "NO_CHRONICLE_MATCH",
        "refuel_called":  False,
    }


# ============================================================
# FINDING BUILDER
# ============================================================

def build_finding(
    finding_id: str,
    competitor: str,
    source: str,
    journey_id: Optional[str],
    cluster: list[dict],
    chronicle_entry: Optional[dict],
    cac_score: float,
    sim_hist: float,
    vol_sig: float,
    refuel_output: dict,
    designed_ceiling_reached: bool,
) -> dict:
    """Build a structured MIL finding per MIL_SCHEMA.yaml mandatory_output_fields."""

    severity_counts = defaultdict(int)
    for r in cluster:
        sev = r.get("severity_class", "P2")
        severity_counts[sev] += 1

    # Dominant severity = highest severity class present
    dominant_sev = "P2"
    for sev in ("P0", "P1", "P2"):
        if severity_counts[sev] > 0:
            dominant_sev = sev
            break

    # Top keywords from cluster (most common)
    kw_counter: dict[str, int] = defaultdict(int)
    for r in cluster:
        for kw in r.get("keywords", []):
            if kw and kw.lower() not in ("enrichment_failed",):
                kw_counter[kw.lower()] += 1
    top_3 = [k for k, _ in sorted(kw_counter.items(), key=lambda x: -x[1])[:3]]

    chronicle_id  = chronicle_entry["chronicle_id"] if chronicle_entry else None
    is_unanchored = chronicle_id is None

    # Apply confidence cap from CHRONICLE entry
    if chronicle_entry:
        cac_score = min(cac_score, chronicle_entry["confidence_cap"])

    blind_spots = refuel_output.get("blind_spots", [])
    if designed_ceiling_reached:
        blind_spots.insert(0,
            "Designed Ceiling reached: to confirm this finding I require "
            "internal HDFS telemetry data. Request Phase 2."
        )

    signal_ids = [
        f"{competitor}_{i}"
        for i, r in enumerate(cluster)
        if r.get("severity_class") in ("P0", "P1")
    ][:20]  # cap at 20 for readability

    finding = {
        "finding_id":             finding_id,
        "generated_at":           datetime.now(timezone.utc).isoformat(),
        "competitor":             competitor,
        "source":                 source,
        # Mandatory output fields (MIL_SCHEMA.yaml)
        "confidence_score":       cac_score,
        "blind_spots":            blind_spots,
        "top_3_keywords":         top_3,
        "human_countersign_status": "PENDING",
        "signal_severity":        dominant_sev,
        "journey_id":             journey_id or "UNMAPPED",
        "finding_tier":           _clark_tier(cac_score),
        "designed_ceiling_reached": designed_ceiling_reached,
        # Finding content
        "finding_summary":        refuel_output.get("finding_summary", ""),
        "failure_mode":           refuel_output.get("failure_mode", "NONE"),
        "is_unanchored":          is_unanchored,
        # Signal counts
        "signal_counts": {
            "total":  len(cluster),
            "P0":     severity_counts["P0"],
            "P1":     severity_counts["P1"],
            "P2":     severity_counts["P2"],
            "failed": severity_counts["ENRICHMENT_FAILED"],
        },
        # CAC components (for auditability)
        "cac_components": {
            "vol_sig":   vol_sig,
            "sim_hist":  sim_hist,
            "delta_tel": 0.0,
            "alpha":     ALPHA,
            "beta":      BETA,
            "delta":     DELTA,
        },
        # Provenance chain (MIL_SCHEMA.yaml provenance_chain)
        "provenance": {
            "chronicle_id":             chronicle_id,
            "signal_ids":               signal_ids,
            "classification_version":   CLASS_VER,
            "teacher_model_version":    TEACHER_VER,
            "refuel_narrative_called":  refuel_output.get("refuel_called", False),
        },
        # Chronicle context
        "chronicle_match": {
            "chronicle_id":      chronicle_id,
            "bank":              chronicle_entry["bank"] if chronicle_entry else None,
            "incident_type":     chronicle_entry["incident_type"] if chronicle_entry else None,
            "sim_hist_score":    sim_hist,
            "inference_approved": chronicle_entry["inference_approved"] if chronicle_entry else False,
        },
    }

    return finding


# ============================================================
# MAIN INFERENCE ENGINE
# ============================================================

def run_inference(sample_size: Optional[int] = None) -> list[dict]:
    """
    Main entry point. Runs full inference pass over enriched records.

    sample_size: if set, process only first N records per competitor (validation mode).
    Returns list of structured MIL findings.

    Finding generation rules (per MIL_SCHEMA.yaml):
    - Only P0/P1/P2 signal clusters generate findings
    - UNANCHORED findings (no approved CHRONICLE match) are included but marked
      is_unanchored=True and do not reach Morning Briefing
    - ENRICHMENT_FAILED records are excluded from CAC calculation
    - Designed Ceiling triggers when CAC > threshold and delta_tel = 0
    """
    refuel_available = _check_refuel()
    if not refuel_available:
        logger.warning(
            "[MILAgent] Refuel-8B not confirmed available. "
            "Will use deterministic fallback for finding narratives. "
            "Article Zero: all inferences will be marked accordingly."
        )

    all_records = load_enriched_records()
    if not all_records:
        logger.error("[MILAgent] No enriched records found. Cannot run inference.")
        return []

    findings = []
    finding_seq = 0

    for competitor_key, records in sorted(all_records.items()):
        if sample_size:
            records = records[:sample_size]

        total = len(records)
        # Parse source/competitor from key -- source prefixes are multi-word
        # e.g. 'app_store_lloyds' -> source='app_store', competitor='lloyds'
        # e.g. 'google_play_barclays' -> source='google_play', competitor='barclays'
        source, competitor = competitor_key, competitor_key
        for known_src in ("app_store", "google_play", "trustpilot", "reddit", "youtube"):
            if competitor_key.startswith(known_src + "_"):
                source     = known_src
                competitor = competitor_key[len(known_src) + 1:]
                break

        logger.info("[MILAgent] Processing %s -- %d records", competitor_key, total)

        # Aggregate by (journey_attribution, severity_class) cluster
        # Group by journey_attribution first, then assess severity mix
        journey_clusters: dict[str, list[dict]] = defaultdict(list)
        for r in records:
            attribution = r.get("journey_attribution", "other")
            journey_clusters[attribution].append(r)

        for attribution, cluster in sorted(journey_clusters.items()):
            journey_id = JOURNEY_MAP.get(attribution)

            # Skip unmappable journeys (no inference value)
            if journey_id is None:
                logger.debug("[MILAgent] %s: '%s' unmapped -- skipping", competitor_key, attribution)
                continue

            # Count by severity
            sev_counts: dict[str, int] = defaultdict(int)
            for r in cluster:
                sev_counts[r.get("severity_class", "P2")] += 1

            # Apply minimum cluster size filter
            p0_count = sev_counts.get("P0", 0)
            p1_count = sev_counts.get("P1", 0)
            p2_count = sev_counts.get("P2", 0)
            total_meaningful = p0_count + p1_count + p2_count

            if p0_count < MIN_CLUSTER_SIZE_P0 and total_meaningful < MIN_CLUSTER_SIZE_P2:
                logger.debug("[MILAgent] %s %s: cluster too small (%d) -- skipping",
                             competitor_key, attribution, total_meaningful)
                continue

            # Collect signal keywords
            all_keywords: list[str] = []
            for r in cluster:
                all_keywords.extend(r.get("keywords", []))

            # RAG: find best approved CHRONICLE match
            chronicle_entry, sim_hist = find_best_chronicle_match(journey_id, all_keywords)

            # CAC calculation
            vol_sig   = compute_vol_sig(cluster, total)
            delta_tel = 0.0   # No internal telemetry -- Phase 2 boundary
            cac_score = compute_cac(vol_sig, sim_hist, delta_tel)

            # Designed Ceiling check
            designed_ceiling = (
                cac_score > DESIGNED_CEILING_THRESHOLD
                and delta_tel == 0.0
            )

            # Skip very low CAC clusters (signal noise floor)
            if cac_score < 0.05 and not p0_count:
                logger.debug("[MILAgent] %s %s: CAC %.4f below noise floor -- skipping",
                             competitor_key, attribution, cac_score)
                continue

            # If no approved CHRONICLE match: finding is UNANCHORED
            if chronicle_entry is None:
                logger.info(
                    "[MILAgent] %s %s: NO_CHRONICLE_MATCH -- UNANCHORED (CAC=%.4f). "
                    "Will not reach Morning Briefing.",
                    competitor_key, attribution, cac_score,
                )

            # Refuel-8B call for finding narrative
            refuel_out = call_refuel_for_finding(
                competitor=competitor_key,
                journey_id=journey_id,
                severity_summary=dict(sev_counts),
                top_keywords=list(set(all_keywords))[:10],
                chronicle_id=chronicle_entry["chronicle_id"] if chronicle_entry else None,
                refuel_available=refuel_available,
            )

            finding_seq += 1
            finding_id = f"MIL-F-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{finding_seq:03d}"

            finding = build_finding(
                finding_id=finding_id,
                competitor=competitor,
                source=source,
                journey_id=journey_id,
                cluster=cluster,
                chronicle_entry=chronicle_entry,
                cac_score=cac_score,
                sim_hist=sim_hist,
                vol_sig=vol_sig,
                refuel_output=refuel_out,
                designed_ceiling_reached=designed_ceiling,
            )

            findings.append(finding)
            anchor_note = (
                f"ANCHORED ({chronicle_entry['chronicle_id']}, sim={sim_hist:.2f})"
                if chronicle_entry else "UNANCHORED"
            )
            logger.info(
                "[MILAgent] %s %s -- CAC=%.4f, %s, tier=%s, ceiling=%s",
                competitor_key, attribution, cac_score,
                anchor_note, _clark_tier(cac_score),
                "YES" if designed_ceiling else "no",
            )

    logger.info("[MILAgent] Inference complete. %d findings generated.", len(findings))
    return findings


# ============================================================
# OUTPUT WRITER
# ============================================================

def write_findings(findings: list[dict]) -> None:
    """
    Write findings to mil/outputs/mil_findings.json.
    This is THE ONLY EXIT POINT from MIL per zero_entanglement rule.
    """
    FINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    anchored   = [f for f in findings if not f["is_unanchored"]]
    unanchored = [f for f in findings if f["is_unanchored"]]
    ceiling    = [f for f in findings if f["designed_ceiling_reached"]]

    output = {
        "_comment": (
            "MIL FINDINGS -- THE ONLY EXIT POINT. "
            "This file is the sole data crossing from MIL to CJI Pulse. "
            "Nothing else crosses the boundary."
        ),
        "_schema_version":   "1.0",
        "_status":           "LIVE" if findings else "NO_FINDINGS",
        "_zero_entanglement": (
            "mil/outputs/mil_findings.json is the only file CJI Pulse may "
            "read from mil/. No other mil/ file may be imported or read by "
            "external systems."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_findings":       len(findings),
            "anchored":             len(anchored),
            "unanchored":           len(unanchored),
            "designed_ceiling_hits": len(ceiling),
            "cac_weights": {"alpha": ALPHA, "beta": BETA, "delta": DELTA},
            "delta_tel_note": (
                "delta_tel=0.0 for all findings -- no internal telemetry. "
                "Phase 2 required to close Vane gap."
            ),
        },
        "findings":           findings,
        "unanchored_signals": unanchored,
    }

    FINDINGS_FILE.write_text(
        json.dumps(output, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("[MILAgent] Wrote %d findings to %s", len(findings), FINDINGS_FILE)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    import argparse
    parser = argparse.ArgumentParser(description="MIL Inference Engine (MIL-8) -- Refuel-8B RAG")
    parser.add_argument("--sample", type=int, default=None,
                        help="Process only first N records per competitor (validation mode)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run inference but do not write mil_findings.json")
    args = parser.parse_args()

    mode = f"SAMPLE mode ({args.sample} records/competitor)" if args.sample else "FULL mode"
    logger.info("MIL Inference Engine -- %s%s", mode, " [DRY RUN]" if args.dry_run else "")

    findings = run_inference(sample_size=args.sample)

    if not args.dry_run:
        write_findings(findings)
    else:
        logger.info("[MILAgent] DRY RUN -- not writing findings file")

    # -- Results summary --
    print()
    print("=" * 60)
    print("MIL INFERENCE RESULTS")
    print("=" * 60)

    if not findings:
        print("No findings generated.")
        sys.exit(0)

    anchored   = [f for f in findings if not f["is_unanchored"]]
    unanchored = [f for f in findings if f["is_unanchored"]]
    ceiling    = [f for f in findings if f["designed_ceiling_reached"]]

    print(f"\nTotal findings  : {len(findings)}")
    print(f"Anchored        : {len(anchored)}")
    print(f"Unanchored      : {len(unanchored)}  (will not reach Morning Briefing)")
    print(f"Ceiling triggers: {len(ceiling)}")
    print()

    # Show anchored findings first
    for f in sorted(findings, key=lambda x: -x["confidence_score"]):
        anchor_tag = f["provenance"]["chronicle_id"] or "UNANCHORED"
        ceiling_tag = " [CEILING]" if f["designed_ceiling_reached"] else ""
        print(
            f"  [{f['finding_id']}] {f['competitor']} | {f['journey_id']} | "
            f"CAC={f['confidence_score']:.4f} | {f['signal_severity']} | "
            f"tier={f['finding_tier']} | {anchor_tag}{ceiling_tag}"
        )
        print(f"    {f['finding_summary']}")
        if f["is_unanchored"]:
            print("    ** UNANCHORED -- NO_CHRONICLE_MATCH -- held for Hussain review **")
        if f["designed_ceiling_reached"]:
            print("    ** DESIGNED CEILING: to confirm this I require internal HDFS telemetry. Request Phase 2. **")
        if f["blind_spots"]:
            print(f"    Blind spots: {f['blind_spots'][0]}")
        print()

    if not args.dry_run:
        print(f"Findings written to: {FINDINGS_FILE}")
    print()
