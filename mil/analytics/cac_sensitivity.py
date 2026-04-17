"""
cac_sensitivity.py — CAC weight sensitivity analysis on real corpus.

Reruns the CAC formula across all current findings using alternative weight
combinations and reports how much the tier distribution changes.

Current weights: alpha=0.40, beta=0.40, delta=0.20

Usage: py mil/analytics/cac_sensitivity.py
"""
import json
import logging
from itertools import product
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

FINDINGS_FILE = Path(__file__).resolve().parents[2] / "mil/outputs/mil_findings.json"

DESIGNED_CEILING = 0.45

# Weight grid to test — must sum to 1.0
WEIGHT_GRID = [
    (0.40, 0.40, 0.20),  # current
    (0.50, 0.30, 0.20),  # vol-heavy
    (0.30, 0.50, 0.20),  # sim-heavy
    (0.45, 0.45, 0.10),  # low delta
    (0.35, 0.35, 0.30),  # high delta
    (0.33, 0.33, 0.34),  # balanced
]


def _cac(vol_sig, sim_hist, delta_tel, alpha, beta, delta) -> float:
    return (alpha * vol_sig + beta * sim_hist) / (delta * delta_tel + 1)


def tier(score: float) -> str:
    if score >= 0.60:
        return "CLARK-3"
    if score >= 0.45:
        return "CLARK-2"
    if score >= 0.30:
        return "CLARK-1"
    return "CLARK-0"


def run():
    with open(FINDINGS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    findings = data.get("findings", [])

    log.info("Corpus: %d findings", len(findings))

    results = []
    for alpha, beta, delta in WEIGHT_GRID:
        scores = []
        ceiling_hits = 0
        for f in findings:
            c = f.get("cac_components") or {}
            vol  = c.get("vol_sig", 0.0)
            sim  = c.get("sim_hist", 0.0)
            dtel = c.get("delta_tel", 0.0)
            score = _cac(vol, sim, dtel, alpha, beta, delta)
            scores.append(score)
            if score > DESIGNED_CEILING and dtel == 0.0:
                ceiling_hits += 1

        tiers = [tier(s) for s in scores]
        results.append({
            "alpha": alpha, "beta": beta, "delta": delta,
            "is_current": (alpha, beta, delta) == (0.40, 0.40, 0.20),
            "clark_3": tiers.count("CLARK-3"),
            "clark_2": tiers.count("CLARK-2"),
            "clark_1": tiers.count("CLARK-1"),
            "clark_0": tiers.count("CLARK-0"),
            "ceiling_hits": ceiling_hits,
            "mean_cac": round(sum(scores) / len(scores), 4),
            "max_cac":  round(max(scores), 4),
        })

    # Print report
    print(f"\n{'-'*80}")
    print(f"  CAC Weight Sensitivity Analysis — {len(findings)} findings")
    print(f"{'-'*80}")
    print(f"  {'alpha':>5} {'beta':>5} {'delt':>5}  {'C3':>4} {'C2':>4} {'C1':>4} {'C0':>4}  {'Ceil':>5}  {'MeanCAC':>8}  {'MaxCAC':>7}  {'Note':>10}")
    print(f"  {'-'*5} {'-'*5} {'-'*5}  {'-'*4} {'-'*4} {'-'*4} {'-'*4}  {'-'*5}  {'-'*8}  {'-'*7}  {'-'*10}")
    for r in results:
        note = "<< CURRENT" if r["is_current"] else ""
        print(f"  {r['alpha']:>5.2f} {r['beta']:>5.2f} {r['delta']:>5.2f}  "
              f"{r['clark_3']:>4} {r['clark_2']:>4} {r['clark_1']:>4} {r['clark_0']:>4}  "
              f"{r['ceiling_hits']:>5}  {r['mean_cac']:>8.4f}  {r['max_cac']:>7.4f}  {note:>10}")
    print(f"{'-'*80}")

    # Sensitivity verdict
    current = next(r for r in results if r["is_current"])
    variants = [r for r in results if not r["is_current"]]
    max_c3_delta = max(abs(r["clark_3"] - current["clark_3"]) for r in variants)
    print(f"\n  Max CLARK-3 swing across weight variants: ±{max_c3_delta}")
    if max_c3_delta <= 2:
        print("  VERDICT: Weights are STABLE — tier distribution robust to weight changes.")
    elif max_c3_delta <= 5:
        print("  VERDICT: Weights are MODERATE sensitivity — monitor as corpus grows.")
    else:
        print("  VERDICT: Weights are HIGH sensitivity — consider tuning before Day 60.")
    print()


if __name__ == "__main__":
    run()
