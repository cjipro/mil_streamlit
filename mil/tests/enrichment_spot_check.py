#!/usr/bin/env python3
"""
mil/tests/enrichment_spot_check.py — Gap 6 enrichment quality monitor

Monthly spot-check workflow:
  1. Sample:  py mil/tests/enrichment_spot_check.py --sample
             Writes mil/tests/spot_check_YYYY-MM-DD.json — 50 records ready for labelling.
             Each record has model-assigned labels and empty human label fields.

  2. Label:   Hussain opens spot_check_YYYY-MM-DD.json and fills in:
               "issue_type_human": "<correct label or AGREE>"
               "severity_class_human": "<correct label or AGREE>"
             AGREE means the model label is correct.

  3. Score:   py mil/tests/enrichment_spot_check.py --score mil/tests/spot_check_YYYY-MM-DD.json
             Computes accuracy, prints report, appends to enrichment_accuracy_log.jsonl.

Targets (from DS review):
  issue_type accuracy    > 85%
  severity_class accuracy > 90%
"""
import argparse
import json
import logging
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("spot_check")

MIL_ROOT      = Path(__file__).parent.parent
ENRICHED_DIR  = MIL_ROOT / "data" / "historical" / "enriched"
TESTS_DIR     = Path(__file__).parent
ACCURACY_LOG  = MIL_ROOT / "data" / "enrichment_accuracy_log.jsonl"

ISSUE_TYPES = [
    "App Not Opening", "App Crashing", "Login Failed", "Payment Failed",
    "Transfer Failed", "Biometric / Face ID Issue", "Card Frozen or Blocked",
    "Slow Performance", "Feature Broken", "Notification Issue", "Account Locked",
    "Missing Transaction", "Incorrect Balance", "Customer Support Failure",
    "Positive Feedback", "Other",
]
SEVERITY_CLASSES = ["P0", "P1", "P2"]


# ── Stratified sampler ────────────────────────────────────────────────────────

def _stratified_sample(records: list[dict], n: int, rng: random.Random) -> list[dict]:
    """
    Stratify by issue_type: min 2 per type present in corpus, remainder filled randomly.
    Prevents a random draw from reporting 90% accuracy on 3 dominant categories while
    silently missing the other 13.
    """
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_type[r["issue_type_model"]].append(r)

    selected: list[dict] = []
    MIN_PER_TYPE = 2

    # Floor: pick min 2 from each type (shuffle so we don't always take the first)
    for bucket in by_type.values():
        rng.shuffle(bucket)
        selected.extend(bucket[:MIN_PER_TYPE])

    # Cap at n
    if len(selected) >= n:
        rng.shuffle(selected)
        return selected[:n]

    # Fill remainder randomly from unselected records
    selected_ids = {id(r) for r in selected}
    remaining = [r for r in records if id(r) not in selected_ids]
    rng.shuffle(remaining)
    selected.extend(remaining[: n - len(selected)])
    rng.shuffle(selected)
    return selected


# ── Sample ────────────────────────────────────────────────────────────────────

def cmd_sample(n: int = 50, seed: int | None = None) -> Path:
    """
    Sample n records from all enriched files, stratified by issue_type (min 2 per type).
    Write spot_check_YYYY-MM-DD.json for manual labelling.
    """
    all_records: list[dict] = []
    for f in sorted(ENRICHED_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            source     = payload.get("source", "")
            competitor = payload.get("competitor", "")
            model      = payload.get("model", "unknown")
            for r in payload.get("records", []):
                it = r.get("issue_type", "")
                sc = r.get("severity_class", "")
                text = (r.get("review") or r.get("content") or "").strip()
                if not text or it in ("ENRICHMENT_FAILED", "") or sc == "ENRICHMENT_FAILED":
                    continue
                all_records.append({
                    "source":       source,
                    "competitor":   competitor,
                    "model":        model,
                    "text":         text[:400],
                    "rating":       r.get("rating"),
                    "date":         r.get("date") or r.get("at", ""),
                    "issue_type_model":    it,
                    "severity_class_model": sc,
                    "issue_type_human":    "",
                    "severity_class_human": "",
                })
        except Exception as exc:
            logger.warning("Failed to load %s: %s", f.name, exc)

    if not all_records:
        logger.error("No enriched records found in %s", ENRICHED_DIR)
        sys.exit(1)

    rng = random.Random(seed)
    sample = _stratified_sample(all_records, n, rng)

    out_file = TESTS_DIR / f"spot_check_{date.today().isoformat()}.json"
    out_file.write_text(
        json.dumps({
            "_instructions": (
                "Fill in issue_type_human and severity_class_human for each record. "
                "Write AGREE if the model label is correct. "
                f"Valid issue_type values: {ISSUE_TYPES}. "
                f"Valid severity_class values: {SEVERITY_CLASSES}."
            ),
            "sample_date":  date.today().isoformat(),
            "sample_size":  len(sample),
            "records":      sample,
        }, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Spot-check file written: %s (%d records)", out_file, len(sample))
    logger.info("Fill in issue_type_human + severity_class_human, then run --score %s", out_file)
    return out_file


# ── Score ─────────────────────────────────────────────────────────────────────

def cmd_score(spot_check_file: Path) -> None:
    """
    Read a completed spot-check file, compute accuracy, append to enrichment_accuracy_log.jsonl.
    """
    payload = json.loads(spot_check_file.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    model   = records[0].get("model", "unknown") if records else "unknown"

    it_correct = 0
    sc_correct = 0
    scored     = 0
    per_issue: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})

    skipped = 0
    for r in records:
        h_it = r.get("issue_type_human", "").strip()
        h_sc = r.get("severity_class_human", "").strip()
        if not h_it or not h_sc:
            skipped += 1
            continue

        m_it = r["issue_type_model"]
        m_sc = r["severity_class_model"]

        effective_it = m_it if h_it.upper() == "AGREE" else h_it
        effective_sc = m_sc if h_sc.upper() == "AGREE" else h_sc

        it_match = (m_it == effective_it)
        sc_match = (m_sc == effective_sc)

        it_correct += int(it_match)
        sc_correct += int(sc_match)
        scored += 1

        per_issue[m_it]["total"] += 1
        per_issue[m_it]["correct"] += int(it_match)

    if scored == 0:
        logger.error("No labelled records found — fill in human labels first")
        sys.exit(1)

    if skipped:
        logger.warning("%d records skipped (empty human labels)", skipped)

    it_acc  = round(it_correct / scored, 4)
    sc_acc  = round(sc_correct / scored, 4)

    it_flag = "PASS" if it_acc >= 0.85 else "FAIL"
    sc_flag = "PASS" if sc_acc >= 0.90 else "FAIL"

    print()
    print("=" * 50)
    print("ENRICHMENT SPOT-CHECK RESULTS")
    print("=" * 50)
    print(f"Model:               {model}")
    print(f"Sample size:         {scored} ({skipped} skipped)")
    print(f"issue_type accuracy: {it_acc:.1%}  [{it_flag}]  (target >85%)")
    print(f"severity accuracy:   {sc_acc:.1%}  [{sc_flag}]  (target >90%)")
    print()
    print("Per issue_type accuracy:")
    for issue, counts in sorted(per_issue.items(), key=lambda x: -x[1]["total"]):
        acc = counts["correct"] / counts["total"] if counts["total"] else 0
        print(f"  {issue:<35} {acc:.0%}  ({counts['correct']}/{counts['total']})")
    print()

    log_entry = {
        "date":                    payload.get("sample_date", date.today().isoformat()),
        "model":                   model,
        "sample_size":             scored,
        "issue_type_accuracy":     it_acc,
        "severity_class_accuracy": sc_acc,
        "issue_type_pass":         it_flag == "PASS",
        "severity_class_pass":     sc_flag == "PASS",
        "per_issue_type":          {k: round(v["correct"] / v["total"], 4) for k, v in per_issue.items() if v["total"] > 0},
        "spot_check_file":         spot_check_file.name,
    }

    with ACCURACY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log_entry) + "\n")
    logger.info("Results appended to %s", ACCURACY_LOG)

    if it_flag == "FAIL" or sc_flag == "FAIL":
        print("ACTION REQUIRED: accuracy below target — review per-issue breakdown above.")
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrichment quality spot-check")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--sample", action="store_true",
                     help="Sample 50 records and write spot-check file")
    grp.add_argument("--score", metavar="FILE",
                     help="Score a completed spot-check file")
    parser.add_argument("--n", type=int, default=50,
                        help="Number of records to sample (default 50)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible sampling")
    args = parser.parse_args()

    if args.sample:
        cmd_sample(n=args.n, seed=args.seed)
    else:
        cmd_score(Path(args.score))
