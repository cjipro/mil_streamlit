#!/usr/bin/env python3
"""
run_teacher.py — MIL Teacher + Synthetic Engine runner.

NOT part of the daily pipeline. Run manually when:
  - A new CHR entry is added to mil/CHRONICLE.md
  - An existing CHR entry flips inference_approved (e.g. CHR-003 root cause confirmed)
  - Pre-QLoRA fine-tune: generate clean training set

Steps:
  1. teacher_agent.py  — Sonnet causal autopsies on all CHRONICLE entries
  2. synthetic_engine.py — 550 instruction pairs from autopsies

Output:
  mil/teacher/output/autopsies.json
  mil/teacher/output/synthetic_pairs.jsonl

Usage:
  py run_teacher.py
  py run_teacher.py --dry-run            # stub output, no API calls
  py run_teacher.py --chr CHR-005        # autopsy + pairs for one new entry only
  py run_teacher.py --pairs-only         # skip autopsies, regenerate pairs from existing autopsies
  py run_teacher.py --resume             # append to existing pairs file, skip duplicates
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_teacher")

REPO_ROOT = Path(__file__).parent
MIL_ROOT  = REPO_ROOT / "mil"
sys.path.insert(0, str(MIL_ROOT))


def main():
    parser = argparse.ArgumentParser(description="MIL Teacher + Synthetic Engine")
    parser.add_argument("--dry-run",    action="store_true", help="Stub output, no API calls")
    parser.add_argument("--chr",        metavar="CHR_ID",    help="Run for one CHR entry only (e.g. CHR-005)")
    parser.add_argument("--pairs-only", action="store_true", help="Skip autopsies, regenerate pairs from existing autopsies.json")
    parser.add_argument("--resume",     action="store_true", help="Append to existing pairs file, skip duplicates")
    args = parser.parse_args()

    # -- Step 1: Autopsies --
    if not args.pairs_only:
        logger.info("=" * 60)
        logger.info("STEP 1 — Teacher autopsies")
        if args.chr:
            logger.info("Scope: %s only", args.chr)
        logger.info("=" * 60)

        from teacher.teacher_agent import run as run_autopsies, _parse_chronicle_entries, _run_autopsy, _get_client, AUTOPSIES_FILE, OUTPUT_DIR
        import json

        if args.chr:
            # Single-entry mode: load existing autopsies, replace/append the target entry
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            chronicle_file = MIL_ROOT / "CHRONICLE.md"
            entries, chronicle_full = _parse_chronicle_entries(chronicle_file)

            target = next((e for e in entries if e["chr_id"] == args.chr), None)
            if not target:
                logger.error("CHR entry '%s' not found in CHRONICLE.md", args.chr)
                sys.exit(1)

            client = None if args.dry_run else _get_client()
            new_autopsy = _run_autopsy(client, target, chronicle_full, dry_run=args.dry_run)

            # Merge into existing autopsies file
            existing = []
            if AUTOPSIES_FILE.exists():
                existing = json.loads(AUTOPSIES_FILE.read_text(encoding="utf-8"))

            merged = [a for a in existing if a["chronicle_id"] != args.chr]
            merged.append(new_autopsy)
            AUTOPSIES_FILE.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Autopsy complete: %s (quarantine=%s)", args.chr, new_autopsy["quarantine"])
            autopsies = merged
        else:
            autopsies = run_autopsies(dry_run=args.dry_run)
    else:
        logger.info("--pairs-only: skipping autopsies, using existing autopsies.json")

    # -- Step 2: Synthetic pairs --
    logger.info("=" * 60)
    logger.info("STEP 2 — Synthetic pair generation")
    logger.info("=" * 60)

    from teacher.synthetic_engine import run as run_pairs, PAIR_TARGETS

    # If --chr, only generate pairs for that entry
    if args.chr:
        import teacher.synthetic_engine as se
        original_targets = dict(se.PAIR_TARGETS)
        se.PAIR_TARGETS = {args.chr: original_targets.get(args.chr, 100)}

    result = run_pairs(dry_run=args.dry_run, resume=args.resume)

    if args.chr:
        import teacher.synthetic_engine as se
        se.PAIR_TARGETS = original_targets

    # -- Summary --
    logger.info("=" * 60)
    logger.info("run_teacher.py complete")
    logger.info("  Total pairs:   %d", result["total"])
    logger.info("  Approved:      %d", result["approved"])
    logger.info("  Quarantined:   %d (held pending CHR-003 root cause)", result["quarantined"])
    logger.info("  Disagreements: %d (held for human review)", result["disagreements"])
    logger.info("=" * 60)

    print(f"\nDone.")
    print(f"  Autopsies:    mil/teacher/output/autopsies.json")
    print(f"  Pairs:        mil/teacher/output/synthetic_pairs.jsonl ({result['total']} total)")
    if result["quarantined"]:
        print(f"  Note: {result['quarantined']} CHR-003 pairs quarantined — resolve root cause to unlock")
    if result["disagreements"]:
        print(f"  Note: {result['disagreements']} DISAGREEMENT pairs held for human review")


if __name__ == "__main__":
    main()
