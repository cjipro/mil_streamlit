"""
validate_pairs.py — MIL QLoRA Gate 2

Prints a side-by-side comparison of synthetic instruction pairs vs real
confirmed findings for human review.

Hussain reviews the output, then runs with --sign to countersign Gate 2.

Usage:
  py mil/specialist/validate_pairs.py             # show 3 random pairs
  py mil/specialist/validate_pairs.py --n 5       # show 5 pairs
  py mil/specialist/validate_pairs.py --chr CHR-001  # filter by chronicle
  py mil/specialist/validate_pairs.py --sign      # countersign after review

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIL_DIR       = Path(__file__).resolve().parent.parent
REPO_ROOT     = MIL_DIR.parent
PAIRS_FILE    = MIL_DIR / "teacher" / "output" / "synthetic_pairs.jsonl"
FINDINGS_FILE = MIL_DIR / "outputs" / "mil_findings.json"
VALIDATION_FILE = Path(__file__).parent / "pair_validation.json"

sys.path.insert(0, str(MIL_DIR))
sys.path.insert(0, str(REPO_ROOT))

JOURNEY_LABELS = {
    "J_AUTH_01": "Log In", "J_PAY_01": "Make a Payment",
    "J_TRANSFER_01": "Transfer Money", "J_ACCOUNT_01": "View Account",
    "J_CARD_01": "Card Management", "J_SERVICE_01": "General App Use",
    "J_ONBOARD_01": "Onboarding", "J_SAVINGS_01": "Savings",
}


# ─────────────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────────────

def _load_pairs(chr_filter: str = None) -> list[dict]:
    if not PAIRS_FILE.exists():
        return []
    pairs = []
    for line in PAIRS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            p = json.loads(line)
            # Only approved, non-quarantined pairs
            if p.get("quarantine"):
                continue
            if chr_filter and p.get("chronicle_id") != chr_filter:
                continue
            pairs.append(p)
        except json.JSONDecodeError:
            pass
    return pairs


def _load_findings_by_competitor() -> dict[str, list[dict]]:
    """Return findings grouped by competitor."""
    if not FINDINGS_FILE.exists():
        return {}
    data     = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    grouped  = {}
    for f in findings:
        comp = f.get("competitor", "unknown")
        grouped.setdefault(comp, []).append(f)
    return grouped


def _find_matching_findings(pair: dict, by_comp: dict) -> list[dict]:
    """Find real findings that match the pair's competitor + journey tag."""
    comp    = (pair.get("competitor") or "").lower()
    journey = pair.get("journey_tag", "")
    matches = [
        f for f in by_comp.get(comp, [])
        if f.get("journey_id") == journey
    ]
    # Fallback: any finding for that competitor
    if not matches:
        matches = by_comp.get(comp, [])[:2]
    return matches[:2]


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────

def _print_divider(char="─", width=70):
    print(char * width)


def _print_pair_comparison(pair: dict, findings: list[dict], idx: int) -> None:
    chr_id   = pair.get("chronicle_id", "?")
    pair_id  = pair.get("pair_id", "?")
    comp     = (pair.get("competitor") or "?").title()
    journey  = JOURNEY_LABELS.get(pair.get("journey_tag", ""), pair.get("journey_tag", "?"))
    sev_hint = pair.get("severity_hint", "?")
    action   = pair.get("recommended_action", "?")

    _print_divider("=")
    print(f"  Pair {idx}  |  {pair_id}  |  {chr_id}  |  {comp}  |  {journey}  |  {sev_hint}")
    _print_divider()

    print("  SYNTHETIC INPUT:")
    for line in (pair.get("input") or "No input.").split(". "):
        if line.strip():
            print(f"    {line.strip()}.")
    print()
    print("  SYNTHETIC REASONING CHAIN:")
    for line in (pair.get("reasoning_chain") or "No reasoning.").split("\n"):
        if line.strip():
            print(f"    {line.strip()}")
    print()
    print(f"  RECOMMENDED ACTION:  {action}")
    print(f"  CAC ESTIMATE:        {pair.get('cac_estimate', '?')}")
    print()

    if findings:
        print("  MATCHING REAL FINDINGS:")
        for f in findings:
            fid     = f.get("finding_id", "?")
            f_sev   = f.get("signal_severity", "?")
            f_cac   = f.get("confidence_score", 0.0)
            f_sum   = (f.get("finding_summary") or "")[:100]
            f_tier  = f.get("finding_tier", "?")
            ceiling = " [CEILING]" if f.get("designed_ceiling_reached") else ""
            print(f"    {fid}  |  {f_tier}/{f_sev}  |  CAC {f_cac:.3f}{ceiling}")
            print(f"    {f_sum}")
            print()
    else:
        print("  MATCHING REAL FINDINGS:  none found for this competitor/journey")
        print()

    print("  REVIEW QUESTIONS:")
    print("    1. Does the synthetic reasoning match what you see in real findings?")
    print("    2. Is the severity hint appropriate?")
    print("    3. Would you accept this pair for fine-tuning?")
    _print_divider()
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Validation (Gate 2)
# ─────────────────────────────────────────────────────────────────────────────

def show_comparison(n: int = 3, chr_filter: str = None) -> int:
    """Print n pair comparisons. Returns count shown."""
    pairs    = _load_pairs(chr_filter)
    by_comp  = _load_findings_by_competitor()

    if not pairs:
        print("No approved synthetic pairs found.")
        return 0

    sample = random.sample(pairs, min(n, len(pairs)))

    print(f"\n{'='*70}")
    print(f"  MIL Synthetic Pair Validator — Gate 2")
    print(f"  Showing {len(sample)} of {len(pairs)} approved pairs")
    if chr_filter:
        print(f"  Filter: {chr_filter}")
    print(f"{'='*70}\n")

    for i, pair in enumerate(sample, 1):
        findings = _find_matching_findings(pair, by_comp)
        _print_pair_comparison(pair, findings, i)

    print(f"  After review, run:  py mil/specialist/validate_pairs.py --sign")
    print(f"  to countersign Gate 2.\n")

    return len(sample)


def record_countersign(n_reviewed: int = 3) -> None:
    validation = {
        "approved_by":     "Hussain Ahmed",
        "approved_at":     datetime.now(timezone.utc).isoformat(),
        "pairs_reviewed":  n_reviewed,
        "total_pairs":     len(_load_pairs()),
        "gate_2_status":   "APPROVED",
        "note":            "Human review: synthetic pairs align with real findings."
    }
    VALIDATION_FILE.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[validate_pairs] Gate 2 countersignature recorded -> {VALIDATION_FILE}\n")
    print(f"  Pairs reviewed: {n_reviewed}")
    print(f"  Status:         APPROVED\n")


def is_approved() -> bool:
    if not VALIDATION_FILE.exists():
        return False
    try:
        state = json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))
        return state.get("gate_2_status") == "APPROVED"
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MIL Synthetic Pair Validator — Gate 2")
    parser.add_argument("--n",    type=int,  default=3,    help="Number of pairs to show (default: 3)")
    parser.add_argument("--chr",  type=str,  default=None, help="Filter by chronicle (e.g. CHR-001)")
    parser.add_argument("--sign", action="store_true",     help="Countersign Gate 2 after review")
    args = parser.parse_args()

    if args.sign:
        if not PAIRS_FILE.exists():
            print("ERROR: pairs file not found")
            sys.exit(1)
        record_countersign(n_reviewed=args.n)
        sys.exit(0)

    count = show_comparison(n=args.n, chr_filter=args.chr)
    sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()
