"""
build_severity_pairs.py — generate severity classification training pairs from enriched records.

Samples P0/P1/P2 records from Haiku-enriched corpus and formats them as
instruction pairs for QLoRA fine-tuning. Output appended to severity_pairs.jsonl.

Targets:
  P0: 60 pairs  (over-sample — boundary cases most important)
  P1: 60 pairs  (over-sample — boundary cases most important)
  P2: 30 pairs  (under-sample — model already biased toward P2)

Usage:
  py mil/specialist/build_severity_pairs.py
  py mil/specialist/build_severity_pairs.py --n-p0 60 --n-p1 60 --n-p2 30
"""
import argparse
import json
import random
import sys
from pathlib import Path

MIL_DIR     = Path(__file__).resolve().parent.parent
ENRICHED_DIR = MIL_DIR / "data" / "historical" / "enriched"
OUT_FILE    = MIL_DIR / "teacher" / "output" / "severity_pairs.jsonl"

SYSTEM_PREFIX = (
    "You are a banking app complaints analyst classifying review severity.\n"
    "P0 = complete block (cannot log in at all, payment completely fails, app will not open, total loss of access).\n"
    "P1 = significant friction (repeated failures, feature broken after update, cannot complete key action after retrying).\n"
    "P2 = minor annoyance, cosmetic issue, or positive review.\n"
)


def _load_enriched() -> dict[str, list[dict]]:
    """Load all enriched records, grouped by severity_class."""
    buckets: dict[str, list[dict]] = {"P0": [], "P1": [], "P2": []}
    for path in sorted(ENRICHED_DIR.glob("*_enriched.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            recs = data.get("records", []) if isinstance(data, dict) else data
            for r in recs:
                sev = r.get("severity_class")
                text = (r.get("review") or r.get("review_text") or "").strip()
                reasoning = (r.get("reasoning") or "").strip()
                if sev in buckets and text and reasoning and len(text) >= 20:
                    buckets[sev].append(r)
        except Exception:
            pass
    return buckets


def _make_pair(record: dict, idx: int) -> dict:
    text      = (record.get("review") or record.get("review_text") or "").strip()[:400]
    sev       = record["severity_class"]
    reasoning = record.get("reasoning", "").strip()
    issue     = record.get("issue_type", "")
    journey   = record.get("customer_journey", "")

    instruction = (
        f"{SYSTEM_PREFIX}\n"
        f'Classify the severity of this banking app review.\n\n'
        f'Review: "{text}"\n\n'
        f'Return valid JSON with severity_class and reasoning.'
    )

    response = json.dumps({
        "severity_class": sev,
        "reasoning": reasoning,
        "issue_type": issue,
        "customer_journey": journey,
    }, ensure_ascii=False)

    return {
        "pair_id":              f"SEV-{sev}-{idx:04d}",
        "chronicle_id":         "SEVERITY_CALIBRATION",
        "teacher_model_version": "claude-haiku-4-5-20251001",
        "inference_approved":   True,
        "quarantine":           False,
        "severity_hint":        sev,
        "input":                instruction,
        "reasoning_chain":      response,
        "recommended_action":   f"Classify as {sev}.",
        "signal_source":        record.get("signal_source", "enriched"),
        "competitor":           record.get("competitor", ""),
    }


def build(n_p0: int, n_p1: int, n_p2: int, seed: int = 42) -> int:
    random.seed(seed)
    buckets = _load_enriched()

    print(f"[severity_pairs] corpus: P0={len(buckets['P0'])}  P1={len(buckets['P1'])}  P2={len(buckets['P2'])}")

    sample_p0 = random.sample(buckets["P0"], min(n_p0, len(buckets["P0"])))
    sample_p1 = random.sample(buckets["P1"], min(n_p1, len(buckets["P1"])))
    sample_p2 = random.sample(buckets["P2"], min(n_p2, len(buckets["P2"])))

    pairs = []
    for i, r in enumerate(sample_p0):
        pairs.append(_make_pair(r, i))
    for i, r in enumerate(sample_p1):
        pairs.append(_make_pair(r, i))
    for i, r in enumerate(sample_p2):
        pairs.append(_make_pair(r, i))

    random.shuffle(pairs)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"[severity_pairs] wrote {len(pairs)} pairs -> {OUT_FILE}")
    print(f"  P0: {len(sample_p0)}  P1: {len(sample_p1)}  P2: {len(sample_p2)}")
    return len(pairs)


def main():
    parser = argparse.ArgumentParser(description="Build severity classification training pairs")
    parser.add_argument("--n-p0", type=int, default=60)
    parser.add_argument("--n-p1", type=int, default=60)
    parser.add_argument("--n-p2", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    n = build(args.n_p0, args.n_p1, args.n_p2, args.seed)
    sys.exit(0 if n > 0 else 1)


if __name__ == "__main__":
    main()
