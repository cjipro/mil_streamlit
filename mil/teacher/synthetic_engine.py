"""
synthetic_engine.py — MIL Synthetic Instruction Pair Engine (MIL-7)

Converts teacher autopsies into structured instruction pairs for future QLoRA fine-tuning.

Reads:  mil/teacher/output/autopsies.json
Writes: mil/teacher/output/synthetic_pairs.jsonl

Each pair format:
  input            — a signal scenario an analyst would receive
  reasoning_chain  — step-by-step reasoning referencing CHRONICLE
  recommended_action — what the analyst should do next

Each pair is tagged with:
  chronicle_id, teacher_model_version, inference_approved, quarantine

CHR-003 pairs: generated but quarantine=true — excluded from training set
               until Hussain confirms root cause (inference_approved: false).

DISAGREEMENT flag: applied when a pair contradicts a known verified fact
                   from the source CHRONICLE entry. Flagged pairs held for
                   human review, never included in training set without sign-off.

Target: 550 pairs (200/CHR-001 + 150/CHR-002 + 100/CHR-003 + 100/CHR-004)

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MIL_ROOT       = Path(__file__).parent.parent
OUTPUT_DIR     = MIL_ROOT / "teacher" / "output"
AUTOPSIES_FILE = OUTPUT_DIR / "autopsies.json"
PAIRS_FILE     = OUTPUT_DIR / "synthetic_pairs.jsonl"

TEACHER_MODEL = "claude-sonnet-4-6"
PAIRS_PER_BATCH = 10
MAX_RETRIES     = 3
RETRY_DELAY     = 5

# Target pairs per CHR entry
PAIR_TARGETS = {
    "CHR-001": 200,
    "CHR-002": 150,
    "CHR-003": 100,   # quarantined — generated but excluded from training
    "CHR-004": 100,
}

# Competitors MIL actively monitors
COMPETITORS = ["NatWest", "Lloyds", "HSBC", "Monzo", "Revolut", "Barclays"]

# Signal sources
SIGNAL_SOURCES = [
    "App Store reviews",
    "Google Play reviews",
    "DownDetector report spike",
    "Reddit thread (r/UKPersonalFinance)",
    "Twitter/X complaint volume",
    "App Store rating velocity drop",
]

# Scenario seed categories — rotated across batches to ensure diversity
SCENARIO_SEEDS = [
    "early_warning: signals appearing 48-72 hours before a potential incident peak",
    "acute_incident: signals appearing during the first 2 hours of a live incident",
    "post_incident: signals in the 24-48 hours after service restoration",
    "gradual_drift: slow degradation over 7-14 days, no single spike",
    "cross_competitor: similar pattern appearing at a different competitor",
    "journey_specific: signals concentrated in one customer journey (e.g. login, payment)",
    "severity_escalation: P2 complaints transitioning to P1 then P0 within 6 hours",
    "multi_source: same failure appearing simultaneously across App Store + DownDetector + Reddit",
    "false_positive: signals that superficially resemble the pattern but have a benign cause",
    "designed_ceiling: signals that require internal telemetry to confirm — CAC > 0.45, Delta_tel=0",
]

PAIR_SYSTEM = """You are a banking intelligence analyst trainer generating instruction pairs for an early warning AI system.

Each pair teaches the system how to reason from public market signals to actionable intelligence.

OUTPUT FORMAT: Return a JSON array of exactly {n} objects. No markdown, no preamble.

Each object must have exactly these fields:
{{
  "input": "string — a realistic signal scenario the analyst receives. Include: competitor name, signal source, magnitude, timeframe. 2-4 sentences.",
  "reasoning_chain": "string — step-by-step reasoning. Must reference the CHRONICLE entry by ID. Steps: (1) Signal classification, (2) Pattern matching vs CHRONICLE, (3) CAC estimation, (4) Designed Ceiling check, (5) Confidence assessment. Use numbered steps.",
  "recommended_action": "string — specific action. One of: MONITOR (watch for 24h), ESCALATE (alert analyst immediately), CEILING_TRIGGER (request Phase 2 internal data), DISMISS (benign signal), QUARANTINE_PENDING (CHR-003 class — root cause unconfirmed).",
  "signal_source": "string — primary signal source used in the input",
  "competitor": "string — competitor featured in the scenario",
  "journey_tag": "string — customer journey affected (e.g. J_LOGIN_01, J_PAY_01, J_SERVICE_01)",
  "severity_hint": "string — P0, P1, or P2",
  "cac_estimate": "string — rough CAC range e.g. '0.3-0.5' or '>0.6'"
}}

ARTICLE ZERO: Never invent regulatory outcomes, specific fines, or customer counts not present in the CHRONICLE.
Express uncertainty explicitly in the reasoning chain when source confidence is MEDIUM or LOW."""


def _get_client():
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise ImportError("anthropic package required. Run: pip install anthropic")


def _load_autopsies() -> list[dict]:
    if not AUTOPSIES_FILE.exists():
        raise FileNotFoundError(
            f"Autopsies file not found: {AUTOPSIES_FILE}\n"
            "Run teacher_agent.py first."
        )
    autopsies = json.loads(AUTOPSIES_FILE.read_text(encoding="utf-8"))
    if not autopsies:
        raise ValueError("Autopsies file is empty — re-run teacher_agent.py")
    return autopsies


def _known_facts_for(chr_id: str) -> list[str]:
    """
    Return key verified facts used for disagreement detection.
    Only includes HIGH confidence facts from CHRONICLE.
    """
    facts = {
        "CHR-001": [
            "TSB migration date 22 April 2018",
            "1.9 million customers locked out",
            "225492 complaints",
            "FCA fine 29750000",
            "PRA fine 18900000",
            "combined fine 48650000",
            "CEO Paul Pester resigned 4 August 2018",
            "5.2 million customers",
            "4424 defects open at go-live",
        ],
        "CHR-002": [
            "Lloyds defect date 12 March 2025",
            "447936 customers potentially exposed",
            "114182 customers actively viewed data",
            "139000 compensation",
            "3625 customers compensated",
        ],
        "CHR-003": [
            # CHR-003: very few HIGH confidence facts
            "HSBC outage 27 August 2025",
            "approximately 5 hours duration",
            "over 4000 DownDetector complaints within first hour",
            # NOTE: 14.5M is UNCONFIRMED — any pair citing it is a DISAGREEMENT
        ],
        "CHR-004": [
            "817 Barclays reviews",
            "83.6 percent positive",
            "P0 count 18",
            "P1 count 20",
        ],
    }
    return facts.get(chr_id, [])


def _disagreement_check(pair: dict, chr_id: str) -> bool:
    """
    Simple disagreement detection: flag if the pair contains figures
    that contradict known verified facts.

    Returns True if a DISAGREEMENT is detected.
    """
    text = (pair.get("input", "") + " " + pair.get("reasoning_chain", "")).lower()

    # CHR-003 specific: 14.5M affected count is UNCONFIRMED — flag if cited as fact
    if chr_id == "CHR-003":
        if "14.5" in text and ("million" in text or "customers" in text):
            return True

    # CHR-001: check for wrong fine amounts
    if chr_id == "CHR-001":
        # Correct combined fine is £48.65M — flag obvious wrong figures
        wrong_fines = ["£50m", "£60m", "£100m", "50 million", "60 million", "100 million"]
        if any(f in text for f in wrong_fines):
            return True

    return False


def _generate_pairs_batch(
    client,
    autopsy: dict,
    batch_idx: int,
    n: int,
    dry_run: bool = False,
) -> list[dict]:
    """Generate n instruction pairs for one autopsy, batch_idx-th call."""
    chr_id   = autopsy["chronicle_id"]
    seed_idx = batch_idx % len(SCENARIO_SEEDS)
    seed     = SCENARIO_SEEDS[seed_idx]

    # Rotate competitors so each batch foregrounds a different one
    primary_competitor = COMPETITORS[batch_idx % len(COMPETITORS)]

    if dry_run:
        return [_stub_pair(chr_id, batch_idx, i) for i in range(n)]

    user_prompt = (
        f"Generate {n} diverse instruction pairs based on this CHRONICLE autopsy.\n\n"
        f"CHRONICLE ENTRY: {chr_id} — {autopsy.get('title', '')}\n"
        f"Bank: {autopsy.get('bank', '')}\n"
        f"Incident type: {autopsy.get('incident_type', '')}\n"
        f"Confidence score: {autopsy.get('confidence_score', 0.0)}\n"
        f"Quarantine: {autopsy['quarantine']}\n\n"
        f"CAUSAL ANALYSIS:\n{autopsy.get('causal_analysis', '')}\n\n"
        f"FAILURE MODES:\n{json.dumps(autopsy.get('failure_modes', []), indent=2)}\n\n"
        f"EARLY WARNING SIGNALS:\n{json.dumps(autopsy.get('early_warning_signals', []), indent=2)}\n\n"
        f"INFERENCE LESSONS:\n{json.dumps(autopsy.get('inference_lessons', []), indent=2)}\n\n"
        f"BLIND SPOTS:\n{json.dumps(autopsy.get('blind_spots', []), indent=2)}\n\n"
        f"SCENARIO SEED FOR THIS BATCH: {seed}\n"
        f"PRIMARY COMPETITOR FOR THIS BATCH: {primary_competitor}\n\n"
        f"{'NOTE: This entry is QUARANTINED (inference_approved=false). All reasoning_chain steps must include the caveat: [QUARANTINE: root cause unconfirmed — CHR-003 confidence penalty applies]' if autopsy['quarantine'] else ''}\n\n"
        f"Return a JSON array of {n} objects only. No markdown."
    )

    system_prompt = PAIR_SYSTEM.format(n=n)

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            import anthropic
            response = client.messages.create(
                model=TEACHER_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            pairs = json.loads(raw)
            if not isinstance(pairs, list):
                raise ValueError(f"Expected JSON array, got {type(pairs)}")
            return pairs

        except (json.JSONDecodeError, ValueError) as exc:
            last_exc = exc
            logger.warning(
                "%s batch %d attempt %d/%d parse error: %s",
                chr_id, batch_idx, attempt, MAX_RETRIES, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "%s batch %d attempt %d/%d error: %s",
                chr_id, batch_idx, attempt, MAX_RETRIES, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(
        f"{chr_id} batch {batch_idx} failed after {MAX_RETRIES} attempts"
    ) from last_exc


def _stub_pair(chr_id: str, batch_idx: int, pair_idx: int) -> dict:
    return {
        "input":              f"[DRY RUN] {chr_id} batch {batch_idx} pair {pair_idx}",
        "reasoning_chain":    "[DRY RUN]",
        "recommended_action": "MONITOR",
        "signal_source":      "App Store reviews",
        "competitor":         "NatWest",
        "journey_tag":        "J_SERVICE_01",
        "severity_hint":      "P1",
        "cac_estimate":       "0.3-0.5",
    }


def _assemble_pair(
    raw: dict,
    chr_id: str,
    autopsy: dict,
    batch_idx: int,
    pair_idx: int,
) -> dict:
    """Attach metadata and run disagreement check on a raw generated pair."""
    disagreement = _disagreement_check(raw, chr_id)
    pair_id      = f"{chr_id.replace('-', '')}-{batch_idx:03d}-{pair_idx:03d}"

    return {
        "pair_id":               pair_id,
        "chronicle_id":          chr_id,
        "teacher_model_version": TEACHER_MODEL,
        "inference_approved":    autopsy.get("inference_approved", False),
        "quarantine":            autopsy["quarantine"],
        "disagreement_flag":     "DISAGREEMENT" if disagreement else None,
        "generated_at":          datetime.now(timezone.utc).isoformat(),
        **raw,
    }


def run(dry_run: bool = False, resume: bool = False) -> dict:
    """
    Generate synthetic instruction pairs from all autopsies.

    Args:
        dry_run: skip API calls, write stubs
        resume:  skip CHR entries already present in existing pairs file

    Returns dict with counts per CHR entry.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    autopsies = _load_autopsies()

    # Build lookup by chr_id
    autopsy_map = {a["chronicle_id"]: a for a in autopsies}

    # Load existing pairs if resuming
    existing_ids: set[str] = set()
    if resume and PAIRS_FILE.exists():
        with PAIRS_FILE.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        p = json.loads(line)
                        existing_ids.add(p.get("pair_id", ""))
                    except json.JSONDecodeError:
                        pass
        logger.info("Resume mode: %d existing pairs found", len(existing_ids))

    client = None if dry_run else _get_client()

    counts: dict[str, int]    = {}
    disagreements: list[str]  = []

    mode = "a" if resume else "w"
    with PAIRS_FILE.open(mode, encoding="utf-8") as out:
        for chr_id, target in PAIR_TARGETS.items():
            autopsy = autopsy_map.get(chr_id)
            if not autopsy:
                logger.warning("No autopsy found for %s — skipping", chr_id)
                continue

            quarantine_label = " [QUARANTINED]" if autopsy["quarantine"] else ""
            logger.info("Generating %d pairs for %s%s", target, chr_id, quarantine_label)

            n_batches = (target + PAIRS_PER_BATCH - 1) // PAIRS_PER_BATCH
            written   = 0

            for batch_idx in range(n_batches):
                remaining = target - written
                if remaining <= 0:
                    break
                n = min(PAIRS_PER_BATCH, remaining)

                try:
                    raw_pairs = _generate_pairs_batch(
                        client, autopsy, batch_idx, n, dry_run=dry_run
                    )
                except RuntimeError as exc:
                    logger.error("Batch failed, stopping %s: %s", chr_id, exc)
                    break

                for pair_idx, raw in enumerate(raw_pairs):
                    pair = _assemble_pair(raw, chr_id, autopsy, batch_idx, pair_idx)
                    pid  = pair["pair_id"]

                    if pid in existing_ids:
                        continue

                    if pair.get("disagreement_flag") == "DISAGREEMENT":
                        disagreements.append(pid)
                        logger.warning("  DISAGREEMENT flagged: %s", pid)

                    out.write(json.dumps(pair, ensure_ascii=False) + "\n")
                    written += 1

                logger.info(
                    "  %s batch %d/%d — %d/%d pairs written",
                    chr_id, batch_idx + 1, n_batches, written, target,
                )

            counts[chr_id] = written

    total        = sum(counts.values())
    approved_tot = sum(v for k, v in counts.items() if autopsy_map.get(k, {}).get("inference_approved"))
    quarant_tot  = total - approved_tot

    logger.info("=" * 50)
    logger.info("Synthetic pair generation complete")
    logger.info("Total pairs: %d (approved=%d, quarantined=%d)", total, approved_tot, quarant_tot)
    logger.info("Disagreements flagged: %d", len(disagreements))
    for chr_id, count in counts.items():
        logger.info("  %s: %d pairs", chr_id, count)
    logger.info("Output: %s", PAIRS_FILE)

    return {
        "total":         total,
        "approved":      approved_tot,
        "quarantined":   quarant_tot,
        "disagreements": len(disagreements),
        "per_chr":       counts,
        "output_file":   str(PAIRS_FILE),
    }


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="MIL Synthetic Engine — instruction pair generation")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls, write stubs")
    parser.add_argument("--resume",  action="store_true", help="Append to existing pairs file, skip duplicates")
    args = parser.parse_args()

    result = run(dry_run=args.dry_run, resume=args.resume)
    print(f"\nDone.")
    print(f"  Total pairs:    {result['total']}")
    print(f"  Approved:       {result['approved']}")
    print(f"  Quarantined:    {result['quarantined']} (CHR-003 — held pending root cause)")
    print(f"  Disagreements:  {result['disagreements']} (held for human review)")
    print(f"  Output:         {result['output_file']}")
