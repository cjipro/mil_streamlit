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

from mil.inference.chronicle_loader import load_chronicle_entries as _load_chr

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from mil.config.get_model import get_model as _get_model

MIL_ROOT     = Path(__file__).parent.parent
ENRICHED_DIR = MIL_ROOT / "data" / "historical" / "enriched"
FINDINGS_FILE = MIL_ROOT / "outputs" / "mil_findings.json"

try:
    from mil.config.thresholds import T as _T
except ImportError:
    from config.thresholds import T as _T

ALPHA                      = _T("inference.cac_alpha")
BETA                       = _T("inference.cac_beta")
DELTA                      = _T("inference.cac_delta")
DESIGNED_CEILING_THRESHOLD = _T("inference.designed_ceiling")
MIN_CLUSTER_SIZE_P2        = int(_T("inference.min_cluster_size_p2"))
MIN_CLUSTER_SIZE_P0        = int(_T("inference.min_cluster_size_p0"))
REQUEST_TIMEOUT            = int(_T("api.ollama_timeout_s"))

# Inference model — routed via mil/config/model_routing.yaml
_INFERENCE_CFG  = _get_model("inference")
OLLAMA_URL      = f"{_INFERENCE_CFG['api_compat_url']}/chat/completions"
OLLAMA_MODEL    = _INFERENCE_CFG["model"]
CLASS_VER       = _INFERENCE_CFG["model"]
TEACHER_VER     = None      # MIL-7 not yet built -- explicitly None
MAX_RETRIES     = int(_T("api.max_retries"))

# Severity volume multipliers per MIL_SCHEMA.yaml signal_severity
SEV_MULTIPLIER = {"P0": 2.0, "P1": 1.5, "P2": 1.0, "ENRICHMENT_FAILED": 0.0}

# issue_type (v3 schema) -> journey_id taxonomy (MIL_SCHEMA.yaml)
# Also retains v2 journey_category keys for backwards compatibility
JOURNEY_MAP = {
    # v3 issue_type keys
    "Login Failed":              "J_LOGIN_01",
    "Biometric / Face ID Issue": "J_LOGIN_01",
    "Account Locked":            "J_LOGIN_01",
    "Payment Failed":            "J_PAY_01",
    "Transfer Failed":           "J_PAY_01",
    "Missing Transaction":       "J_PAY_01",
    "App Not Opening":           "J_SERVICE_01",
    "App Crashing":              "J_SERVICE_01",
    "Slow Performance":          "J_SERVICE_01",
    "Feature Broken":            "J_SERVICE_01",
    "Notification Issue":        "J_SERVICE_01",
    "Card Frozen or Blocked":    "J_SERVICE_01",
    "Incorrect Balance":         "J_SERVICE_01",
    "Customer Support Failure":  "J_SERVICE_01",
    "Positive Feedback":         None,
    "Other":                     None,
    "ENRICHMENT_FAILED":         None,
    # v2 journey_category keys (fallback)
    "Login & Account Access":    "J_LOGIN_01",
    "Password Issues":           "J_LOGIN_01",
    "Failed Transaction":        "J_PAY_01",
    "Transaction Charges":       "J_PAY_01",
    "Account Registration":      "J_ONBOARD_01",
    "App Installation Issues":   "J_ONBOARD_01",
    "App crashes or Slow":       "J_SERVICE_01",
    "App not Opening":           "J_SERVICE_01",
    "Network Failure":           "J_SERVICE_01",
    "Customer Support":          "J_SERVICE_01",
    "Customer Inquiry":          "J_SERVICE_01",
    "General Feedback":          None,
}

# Clark tier mapping on CAC score
CLARK_TIER = {
    (0.60, 1.01): "P1",
    (0.40, 0.60): "P2",
    (0.00, 0.40): "P3",
}

# CHRONICLE entries — loaded from mil/CHRONICLE.md at startup via chronicle_loader.
# All inference_approved=True entries are included automatically.
# No code change required when Hussain approves a new CHR entry.
CHRONICLE_ENTRIES = _load_chr()


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

# Lazy-init embedding support (sentence-transformers all-MiniLM-L6-v2)
_EMBED_MODEL = None          # SentenceTransformer instance, or False when unavailable
_CHR_EMBED_CACHE: dict = {}  # chronicle_id -> L2-normalised embedding vector


def _load_embed_model():
    """Load all-MiniLM-L6-v2 once; return False if sentence-transformers not installed."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("[MILAgent] Loaded sentence-transformer: all-MiniLM-L6-v2")
        except Exception as exc:
            logger.warning("[MILAgent] sentence-transformers unavailable (%s) — using keyword overlap", exc)
            _EMBED_MODEL = False
    return _EMBED_MODEL


def _chr_vec(entry: dict, model):
    """Return cached L2-normalised embedding for a CHRONICLE entry."""
    cid = entry["chronicle_id"]
    if cid not in _CHR_EMBED_CACHE:
        text = entry["pattern_description"] + " " + " ".join(entry["pattern_keywords"])
        _CHR_EMBED_CACHE[cid] = model.encode(text, normalize_embeddings=True)
    return _CHR_EMBED_CACHE[cid]


def _keyword_overlap(signal_keywords: list[str], chronicle_keywords: list[str]) -> float:
    """
    Fallback similarity: keyword overlap [0.0, 1.0].
    Used when sentence-transformers is unavailable.
    """
    if not signal_keywords or not chronicle_keywords:
        return 0.0
    sig_lower   = list(dict.fromkeys(k.lower() for k in signal_keywords))
    chron_lower = [k.lower() for k in chronicle_keywords]
    hits = 0
    for sk in sig_lower:
        for ck in chron_lower:
            if sk in ck or ck in sk:
                hits += 1
                break
    return min(hits / len(chronicle_keywords), 1.0)


def find_best_chronicle_match(
    journey_id: Optional[str],
    signal_keywords: list[str],
) -> tuple[Optional[dict], float]:
    """
    Find the highest-similarity CHRONICLE entry for a given journey_id + keywords.
    Only considers inference_approved=True entries.

    Uses all-MiniLM-L6-v2 cosine similarity (384-dim, CPU-fast).
    Falls back to keyword overlap if sentence-transformers is unavailable.

    Returns (best_entry_or_None, sim_hist_score [0.0, 1.0]).
    Returns (None, 0.0) if no approved match — finding will be UNANCHORED.
    """
    model = _load_embed_model()

    # Pre-encode signal text once for this cluster
    signal_vec = None
    if model:
        signal_text = " ".join(dict.fromkeys(k.lower() for k in signal_keywords if k))[:512]
        try:
            signal_vec = model.encode(signal_text, normalize_embeddings=True)
        except Exception as exc:
            logger.warning("[MILAgent] embed encode failed (%s) — falling back to keyword overlap", exc)
            signal_vec = None

    best_entry = None
    best_score = 0.0

    for entry in CHRONICLE_ENTRIES:
        if not entry["inference_approved"]:
            continue
        if journey_id and journey_id not in entry["journey_tags"]:
            continue

        if signal_vec is not None:
            try:
                import numpy as np
                score = float(np.dot(signal_vec, _chr_vec(entry, model)))
            except Exception:
                score = _keyword_overlap(signal_keywords, entry["pattern_keywords"])
        else:
            score = _keyword_overlap(signal_keywords, entry["pattern_keywords"])

        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry, round(best_score, 4)


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
        f"CHRONICLE anchor: {chronicle_id or 'NONE -- NO_CHRONICLE_MATCH'}\n"
        f"Note: P0/P1 signals are pre-validated high-risk journey+product combinations only."
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
            "blind_spots":   parsed.get("blind_spots", []),
            "failure_mode":  parsed.get("failure_mode", "NONE"),
            "refuel_called": True,
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
        "blind_spots":   blind_spots,
        "failure_mode":  "NONE" if chronicle_id else "NO_CHRONICLE_MATCH",
        "refuel_called": False,
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

    # Top keywords: v2 schema uses reasoning text; v1 used keywords list
    # Support both: prefer keywords list if present, else extract from reasoning
    kw_counter: dict[str, int] = defaultdict(int)
    for r in cluster:
        for kw in r.get("keywords", []):
            if kw and kw.lower() not in ("enrichment_failed",):
                kw_counter[kw.lower()] += 1
        # v2 schema: extract meaningful words from reasoning
        reasoning = r.get("reasoning", "")
        if reasoning and not r.get("keywords"):
            for word in reasoning.lower().split():
                word = word.strip(".,;:\"'()")
                if len(word) > 4 and word not in ("cannot", "unable", "their", "which", "these"):
                    kw_counter[word] += 1
    top_3 = [k for k, _ in sorted(kw_counter.items(), key=lambda x: -x[1])[:3]]

    chronicle_id  = chronicle_entry["chronicle_id"] if chronicle_entry else None
    is_unanchored = chronicle_id is None

    # Apply confidence cap from CHRONICLE entry
    if chronicle_entry:
        cac_score = min(cac_score, chronicle_entry["confidence_cap"])

    blind_spots = refuel_output.get("blind_spots", [])
    if isinstance(blind_spots, str):
        blind_spots = [blind_spots] if blind_spots else []
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
        # Finding content — summary is deterministic; blind_spots from Refuel
        "finding_summary":        (
            f"{dominant_sev} signal cluster: {competitor} {journey_id or 'unknown'}, "
            f"{severity_counts.get('P0', 0)} P0 / {severity_counts.get('P1', 0)} P1 signals, "
            f"anchor: {chronicle_id or 'UNANCHORED'}."
        ),
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

        # Aggregate by journey_category (v2 schema) cluster
        journey_clusters: dict[str, list[dict]] = defaultdict(list)
        for r in records:
            attribution = r.get("issue_type") or r.get("journey_category") or r.get("journey_attribution", "Other")
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

            # Collect signal keywords for RAG (v1: keywords list, v2: journey_category + reasoning)
            all_keywords: list[str] = []
            for r in cluster:
                all_keywords.extend(r.get("keywords", []))
                # v3 schema: supplement with issue_type + customer_journey labels
                jcat = r.get("issue_type") or r.get("journey_category", "")
                if jcat:
                    all_keywords.extend(jcat.lower().split())
                cj = r.get("customer_journey", "")
                if cj:
                    all_keywords.extend(cj.lower().split())
                reasoning = r.get("reasoning", "")
                if reasoning:
                    all_keywords.extend(w.strip(".,;:\"'()").lower()
                                        for w in reasoning.split() if len(w) > 4)

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
        summary_raw = f['finding_summary'] if isinstance(f['finding_summary'], str) else ' '.join(f['finding_summary'])
        summary_safe = summary_raw.encode('ascii', 'replace').decode('ascii')
        print(f"    {summary_safe}")
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
