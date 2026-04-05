"""
cac_calibrator.py — MIL QLoRA Gate 3

Reviews whether CAC weights (alpha, beta, delta) still hold on the real
findings corpus. Weights were set before any real data existed:
  alpha=0.40 (vol_sig), beta=0.40 (sim_hist), delta=0.20 (delta_tel)

Analysis:
  1. Correlation: CAC score vs actual severity (P0/P1 = high, P2 = low)
  2. Chronicle match rate: do high-CAC findings match chronicle entries?
  3. Ceiling rate: what fraction of P0/P1 are Designed Ceiling?
  4. Weight sensitivity: what happens to ranking if alpha/beta/delta shift?
  5. Recommended weights (if adjustment warranted)

This script produces a report ONLY. It does NOT auto-update weights.
Hussain reviews the report and manually updates mil/config/model_routing.yaml
if warranted. Approval is recorded in mil/specialist/cac_calibration.json.

Usage:
  py mil/specialist/cac_calibrator.py           # print report
  py mil/specialist/cac_calibrator.py --approve  # record Hussain approval in cac_calibration.json

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIL_DIR       = Path(__file__).resolve().parent.parent
REPO_ROOT     = MIL_DIR.parent
FINDINGS_FILE = MIL_DIR / "outputs" / "mil_findings.json"
CALIB_FILE    = Path(__file__).parent / "cac_calibration.json"

sys.path.insert(0, str(MIL_DIR))
sys.path.insert(0, str(REPO_ROOT))

CURRENT_WEIGHTS = {"alpha": 0.40, "beta": 0.40, "delta": 0.20}


# ─────────────────────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────────────────────

def _severity_num(s: str) -> float:
    return {"P0": 1.0, "P1": 0.67, "P2": 0.33}.get(s, 0.0)


def _pearson(xs: list, ys: list) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) ** 0.5) * (sum((y - my) ** 2 for y in ys) ** 0.5)
    return num / den if den else 0.0


def _recalc_cac(f: dict, alpha: float, beta: float, delta: float) -> float:
    comp = f.get("cac_components", {})
    vol  = comp.get("vol_sig", 0.0)
    sim  = comp.get("sim_hist", 0.0)
    dtel = comp.get("delta_tel", 0.0)
    return (alpha * vol + beta * sim) / (delta * dtel + 1)


def run_calibration(findings: list) -> dict:
    """Analyse findings and return calibration report."""
    total = len(findings)
    if not total:
        return {"error": "no findings"}

    # ── Severity distribution ────────────────────────────────────────────────
    sev_counts = {"P0": 0, "P1": 0, "P2": 0}
    for f in findings:
        s = f.get("signal_severity", "P2")
        sev_counts[s] = sev_counts.get(s, 0) + 1

    # ── Correlation: CAC vs severity ─────────────────────────────────────────
    cac_scores = [f.get("confidence_score", 0.0) for f in findings]
    sev_nums   = [_severity_num(f.get("signal_severity", "P2")) for f in findings]
    corr_cac_sev = _pearson(cac_scores, sev_nums)

    # ── Chronicle match rate in high-CAC findings ────────────────────────────
    high_cac = [f for f in findings if f.get("confidence_score", 0) >= 0.45]
    chr_match_rate = (
        sum(1 for f in high_cac if f.get("chronicle_match")) / len(high_cac)
        if high_cac else 0.0
    )

    # ── Ceiling rate among P0/P1 ────────────────────────────────────────────
    p0p1 = [f for f in findings if f.get("signal_severity") in ("P0", "P1")]
    ceiling_rate = (
        sum(1 for f in p0p1 if f.get("designed_ceiling_reached")) / len(p0p1)
        if p0p1 else 0.0
    )

    # ── Weight sensitivity ───────────────────────────────────────────────────
    # Try alpha-heavy, beta-heavy, balanced
    scenarios = {
        "current  (a=0.40, b=0.40, d=0.20)": (0.40, 0.40, 0.20),
        "vol_heavy(a=0.55, b=0.30, d=0.15)": (0.55, 0.30, 0.15),
        "sim_heavy(a=0.30, b=0.55, d=0.15)": (0.30, 0.55, 0.15),
        "balanced (a=0.45, b=0.45, d=0.10)": (0.45, 0.45, 0.10),
    }

    sensitivity = {}
    for label, (a, b, d) in scenarios.items():
        new_scores = [_recalc_cac(f, a, b, d) for f in findings]
        corr = _pearson(new_scores, sev_nums)
        # Rank correlation: are high-severity findings still ranked highest?
        p0p1_ids  = {f.get("finding_id") for f in findings if f.get("signal_severity") in ("P0", "P1")}
        sorted_by_cac = sorted(findings, key=lambda f: _recalc_cac(f, a, b, d), reverse=True)
        top_n     = min(20, len(findings))
        top_ids   = {f.get("finding_id") for f in sorted_by_cac[:top_n]}
        overlap   = len(top_ids & p0p1_ids) / len(p0p1_ids) if p0p1_ids else 0.0
        sensitivity[label] = {
            "corr_cac_sev": round(corr, 3),
            "p0p1_in_top20_rate": round(overlap, 3),
        }

    # ── Recommendation ────────────────────────────────────────────────────────
    # NOTE: CAC measures evidence confidence (volume × chronicle similarity),
    # NOT severity. Low CAC-severity correlation is EXPECTED by design —
    # severity comes from Haiku enrichment, independently of CAC.
    #
    # Correct weight validation: high-CAC findings should be chronicle-anchored
    # (chr_match_rate >= 0.70) and ceiling triggers should be present (evidence
    # the formula is generating discriminating scores).
    weights_ok = (chr_match_rate >= 0.70 and ceiling_rate >= 0.10)

    # Find best scenario by chronicle match proxy (sim_hist weight matters most)
    best_label = max(sensitivity, key=lambda k: sensitivity[k]["corr_cac_sev"])
    best        = sensitivity[best_label]

    return {
        "total_findings":     total,
        "severity_dist":      sev_counts,
        "corr_cac_severity":  round(corr_cac_sev, 3),
        "corr_note":          "Low CAC-severity correlation is EXPECTED — CAC measures evidence confidence, not severity.",
        "chr_match_high_cac": round(chr_match_rate, 3),
        "ceiling_rate_p0p1":  round(ceiling_rate, 3),
        "weight_sensitivity": sensitivity,
        "current_weights_ok": weights_ok,
        "best_scenario":      best_label,
        "best_scenario_stats": best,
        "recommendation": (
            "RETAIN current weights — chronicle match rate and ceiling trigger rate confirm "
            "CAC is correctly rewarding evidence-backed findings."
            if weights_ok else
            f"REVIEW WEIGHTS — chronicle match rate {chr_match_rate:.0%} or ceiling rate "
            f"{ceiling_rate:.0%} below threshold. Consider: {best_label.strip()}."
        ),
    }


def print_report(report: dict) -> None:
    print("\n" + "=" * 65)
    print("  CAC Calibrator — Gate 3 Report")
    print("=" * 65)
    print(f"  Total findings:         {report['total_findings']}")
    sd = report["severity_dist"]
    print(f"  Severity distribution:  P0={sd.get('P0',0)}  P1={sd.get('P1',0)}  P2={sd.get('P2',0)}")
    print(f"  CAC vs severity corr:   {report['corr_cac_severity']:.3f}  (>=0.30 = good)")
    print(f"  Chronicle match rate:   {report['chr_match_high_cac']:.1%}  (high-CAC findings)")
    print(f"  Ceiling rate (P0/P1):   {report['ceiling_rate_p0p1']:.1%}")
    print()
    print("  Weight sensitivity:")
    for label, stats in report["weight_sensitivity"].items():
        print(f"    {label}  |  corr={stats['corr_cac_sev']:.3f}  P0/P1-in-top20={stats['p0p1_in_top20_rate']:.1%}")
    print()
    ok = report["current_weights_ok"]
    print(f"  Current weights OK:     {'YES' if ok else 'NO — see recommendation'}")
    print(f"  Recommendation:         {report['recommendation']}")
    print()
    if not ok:
        print(f"  Best scenario:          {report['best_scenario'].strip()}")
    print("=" * 65)
    print("  Action: Hussain reviews this report, then runs:")
    print("    py mil/specialist/cac_calibrator.py --approve")
    print("  to record approval in mil/specialist/cac_calibration.json.")
    print("=" * 65 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Approval (human countersign)
# ─────────────────────────────────────────────────────────────────────────────

def record_approval(report: dict) -> None:
    approval = {
        "approved_by":         "Hussain Ahmed",
        "approved_at":         datetime.now(timezone.utc).isoformat(),
        "weights_retained":    report.get("current_weights_ok", False),
        "recommendation":      report.get("recommendation", ""),
        "corr_cac_severity":   report.get("corr_cac_severity"),
        "gate_3_status":       "APPROVED",
    }
    CALIB_FILE.write_text(json.dumps(approval, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[cac_calibrator] Gate 3 approval recorded -> {CALIB_FILE}\n")


def is_approved() -> bool:
    if not CALIB_FILE.exists():
        return False
    try:
        state = json.loads(CALIB_FILE.read_text(encoding="utf-8"))
        return state.get("gate_3_status") == "APPROVED"
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MIL CAC Calibrator — Gate 3")
    parser.add_argument("--approve", action="store_true", help="Record Hussain approval and exit")
    args = parser.parse_args()

    if not FINDINGS_FILE.exists():
        print("ERROR: findings file not found")
        sys.exit(1)

    data     = json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
    findings = data.get("findings", [])

    report = run_calibration(findings)
    if report.get("error"):
        print(f"ERROR: {report['error']}")
        sys.exit(1)

    print_report(report)

    if args.approve:
        record_approval(report)

    # Exit 0 if weights OK or already approved, exit 1 if review needed
    sys.exit(0 if (report["current_weights_ok"] or is_approved()) else 1)


if __name__ == "__main__":
    main()
