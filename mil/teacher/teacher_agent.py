"""
teacher_agent.py — MIL Teacher Agent (MIL-7)

Performs deep causal autopsies on CHRONICLE entries using Claude Sonnet.
Retrieval-first architecture: full CHRONICLE context loaded before each autopsy.

Output: mil/teacher/output/autopsies.json

Article Zero: Every claim in an autopsy must trace to verified facts in the CHRONICLE.
              Sonnet is instructed to express ignorance before unverified certainty.

CHR-003 quarantine: inference_approved=false entries are processed but flagged
                    quarantine=true — excluded from synthetic pair training set
                    until Hussain confirms root cause.

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MIL_ROOT       = Path(__file__).parent.parent
CHRONICLE_FILE = MIL_ROOT / "CHRONICLE.md"
OUTPUT_DIR     = MIL_ROOT / "teacher" / "output"
AUTOPSIES_FILE = OUTPUT_DIR / "autopsies.json"

TEACHER_MODEL = "claude-sonnet-4-6"
MAX_RETRIES   = 3
RETRY_DELAY   = 5  # seconds

AUTOPSY_SYSTEM = """You are a sovereign banking intelligence analyst performing deep causal autopsies on historical banking failures.

CONSTRAINTS:
- Article Zero applies: express your own ignorance before delivering any unverified certainty.
- Every claim must trace to verified facts in the CHRONICLE entry. Never invent figures, dates, or regulatory outcomes.
- If a field is marked UNCONFIRMED or [REVIEW REQUIRED] in the source, your autopsy must reflect that uncertainty.
- You are building training data for an early warning system. Precision over completeness.

OUTPUT FORMAT:
Return a JSON object with exactly these fields — no markdown, no preamble:

{
  "causal_analysis": "string — deep analysis of WHY this failure occurred: business pressures -> governance gaps -> technical failures -> customer impact. Be specific. Cite facts.",
  "failure_modes": ["array", "of", "strings — discrete failure modes that contributed (e.g. 'outsourcing governance gap', 'big-bang cutover', 'API boundary leak')"],
  "early_warning_signals": [
    {
      "signal_type": "string — e.g. 'complaint_spike', 'downdetector_surge', 'app_store_rating_drop'",
      "detection_window": "string — how far before peak impact this signal would appear",
      "source_hint": "string — where in public data this signal would appear",
      "description": "string — what the signal looks like specifically"
    }
  ],
  "inference_lessons": ["array of strings — what MIL should infer when it sees analogous patterns in competitor signals today"],
  "blind_spots": ["array of strings — what MIL cannot determine from public signals alone for this incident class"],
  "confidence_note": "string — one sentence on the confidence limitations of this autopsy given source quality"
}"""


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


def _parse_chronicle_entries(path: Path) -> tuple[list[dict], str]:
    """
    Parse CHRONICLE.md into a list of CHR entry dicts plus the full text.

    Returns:
        (entries, full_text)
        entries: list of {chr_id, title, full_section_text, meta}
        full_text: complete CHRONICLE content for context injection
    """
    full_text = path.read_text(encoding="utf-8")

    # Split on CHR section headers: ### CHR-NNN — Title
    pattern = re.compile(r'\n(### (CHR-\d{3})[^\n]*)', re.MULTILINE)
    splits   = pattern.split(full_text)

    # splits layout: [pre_content, full_header_1, chr_id_1, body_1, full_header_2, ...]
    entries = []
    i = 1
    while i < len(splits) - 2:
        full_header = splits[i]
        chr_id      = splits[i + 1]
        body        = splits[i + 2]
        section_text = f"\n{full_header}{body}"

        # Extract title from header
        title_match = re.match(r'### (CHR-\d{3})\s*[—-]\s*(.+)', full_header)
        title = title_match.group(2).strip() if title_match else chr_id

        # Extract YAML block for metadata
        yaml_match = re.search(r'```yaml\n(.*?)```', section_text, re.DOTALL)
        meta = {}
        if yaml_match:
            try:
                meta = yaml.safe_load(yaml_match.group(1)) or {}
            except yaml.YAMLError as exc:
                logger.warning("YAML parse failed for %s: %s", chr_id, exc)

        entries.append({
            "chr_id":        chr_id,
            "title":         title,
            "section_text":  section_text,
            "meta":          meta,
        })
        i += 3

    if not entries:
        raise ValueError(f"No CHR entries found in {path}")

    return entries, full_text


def _run_autopsy(client, entry: dict, chronicle_full: str, dry_run: bool = False) -> dict:
    """Run a Sonnet autopsy on one CHRONICLE entry."""
    chr_id  = entry["chr_id"]
    meta    = entry["meta"]
    quarantine = not bool(meta.get("inference_approved", False))

    if dry_run:
        logger.info("[DRY RUN] Would autopsy %s (quarantine=%s)", chr_id, quarantine)
        return _stub_autopsy(entry)

    # Truncate full chronicle to fit context — keep first 6000 chars for background
    chronicle_context = chronicle_full[:6000]

    user_prompt = (
        f"Perform a deep causal autopsy on the following CHRONICLE entry.\n\n"
        f"BACKGROUND — Full Chronicle (for cross-reference only):\n"
        f"```\n{chronicle_context}\n```\n\n"
        f"TARGET ENTRY:\n{entry['section_text']}\n\n"
        f"Return a JSON object only. No markdown, no preamble."
    )

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            import anthropic
            response = client.messages.create(
                model=TEACHER_MODEL,
                max_tokens=8192,
                system=AUTOPSY_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown code fences if present
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)

            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                from json_repair import repair_json
                result = json.loads(repair_json(raw))
            break

        except (json.JSONDecodeError, anthropic.APIError) as exc:
            last_exc = exc
            logger.warning("%s attempt %d/%d failed: %s", chr_id, attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    else:
        raise RuntimeError(f"Autopsy failed for {chr_id} after {MAX_RETRIES} attempts") from last_exc

    return {
        "chronicle_id":       chr_id,
        "title":              entry["title"],
        "bank":               meta.get("bank", ""),
        "incident_type":      meta.get("incident_type", ""),
        "inference_approved": meta.get("inference_approved", False),
        "confidence_score":   meta.get("confidence_score", 0.0),
        "teacher_model":      TEACHER_MODEL,
        "autopsy_timestamp":  datetime.now(timezone.utc).isoformat(),
        "quarantine":         quarantine,
        **result,
    }


def _stub_autopsy(entry: dict) -> dict:
    """Dry-run stub — structural placeholder, no API call."""
    meta = entry["meta"]
    return {
        "chronicle_id":       entry["chr_id"],
        "title":              entry["title"],
        "bank":               meta.get("bank", ""),
        "incident_type":      meta.get("incident_type", ""),
        "inference_approved": meta.get("inference_approved", False),
        "confidence_score":   meta.get("confidence_score", 0.0),
        "teacher_model":      f"{TEACHER_MODEL}__DRY_RUN",
        "autopsy_timestamp":  datetime.now(timezone.utc).isoformat(),
        "quarantine":         not bool(meta.get("inference_approved", False)),
        "causal_analysis":    "[DRY RUN]",
        "failure_modes":      [],
        "early_warning_signals": [],
        "inference_lessons":  [],
        "blind_spots":        [],
        "confidence_note":    "[DRY RUN]",
    }


def run(dry_run: bool = False) -> list[dict]:
    """
    Run autopsies on all CHRONICLE entries.

    Returns list of autopsy dicts. Writes to mil/teacher/output/autopsies.json.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Parsing CHRONICLE: %s", CHRONICLE_FILE)
    entries, chronicle_full = _parse_chronicle_entries(CHRONICLE_FILE)
    logger.info("Found %d CHR entries: %s", len(entries), [e["chr_id"] for e in entries])

    client = None if dry_run else _get_client()

    autopsies = []
    for entry in entries:
        chr_id     = entry["chr_id"]
        quarantine = not bool(entry["meta"].get("inference_approved", False))
        q_label    = " [QUARANTINED]" if quarantine else ""
        logger.info("Autopsy: %s%s", chr_id, q_label)

        try:
            autopsy = _run_autopsy(client, entry, chronicle_full, dry_run=dry_run)
            autopsies.append(autopsy)
            logger.info(
                "  %s complete — %d failure_modes, %d early_warning_signals, quarantine=%s",
                chr_id,
                len(autopsy.get("failure_modes", [])),
                len(autopsy.get("early_warning_signals", [])),
                autopsy["quarantine"],
            )
        except Exception as exc:
            logger.error("  %s FAILED: %s", chr_id, exc)
            raise

    AUTOPSIES_FILE.write_text(
        json.dumps(autopsies, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Wrote %d autopsies to %s",
        len(autopsies),
        AUTOPSIES_FILE.relative_to(MIL_ROOT),
    )

    approved   = sum(1 for a in autopsies if not a["quarantine"])
    quarantined = sum(1 for a in autopsies if a["quarantine"])
    logger.info("Summary: %d approved, %d quarantined", approved, quarantined)

    return autopsies


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="MIL Teacher Agent — CHRONICLE autopsies")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls, write stubs")
    args = parser.parse_args()

    autopsies = run(dry_run=args.dry_run)
    print(f"\nDone. {len(autopsies)} autopsies written to {AUTOPSIES_FILE}")
    for a in autopsies:
        q = " [QUARANTINED]" if a["quarantine"] else ""
        print(f"  {a['chronicle_id']}{q} — {a['bank']}")
