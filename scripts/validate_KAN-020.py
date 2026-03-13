"""
validate_PULSE-20.py — PULSE-20 data contract validator
Validates contracts/ma_d.yaml against PULSE-20 acceptance criteria.
"""
import sys
import yaml
from pathlib import Path

CONTRACT_PATH = "contracts/ma_d.yaml"

CHECKS = []


def check(label, result, detail=""):
    CHECKS.append((label, result, detail))
    status = "PASS" if result else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}]  {label}{suffix}")
    return result


def main():
    print()
    print("validate_PULSE-20.py — contracts/ma_d.yaml")
    print("=" * 50)
    print()

    # Check 1: file exists
    path = Path(CONTRACT_PATH)
    if not check("File exists", path.exists(), CONTRACT_PATH):
        print("\n  RESULT: FAIL — file not found, cannot continue.\n")
        sys.exit(1)

    # Check 2: valid YAML
    try:
        with open(path, "r", encoding="utf-8") as f:
            contract = yaml.safe_load(f)
        check("Valid YAML", True)
    except yaml.YAMLError as e:
        check("Valid YAML", False, str(e))
        print("\n  RESULT: FAIL — YAML parse error, cannot continue.\n")
        sys.exit(1)

    # Check 3: metadata_lookup_only is true
    mlo = contract.get("metadata_lookup_only")
    check("metadata_lookup_only is true", mlo is True, f"got: {mlo!r}")

    # Check 4: write_inhibit is true
    wi = contract.get("write_inhibit")
    check("write_inhibit is true", wi is True, f"got: {wi!r}")

    # Check 5: permitted_storage_targets present and not empty
    pst = contract.get("permitted_storage_targets")
    check(
        "permitted_storage_targets present and not empty",
        isinstance(pst, list) and len(pst) > 0,
        f"targets: {pst}",
    )

    # Check 6: fairness_audit_hooks present
    fah = contract.get("fairness_audit_hooks")
    check("fairness_audit_hooks present", isinstance(fah, dict) and len(fah) > 0)

    # Check 7: infrastructure_context present
    ic = contract.get("infrastructure_context")
    check("infrastructure_context present", isinstance(ic, dict) and len(ic) > 0)

    # Summary
    passes = sum(1 for _, r, _ in CHECKS if r)
    fails = len(CHECKS) - passes
    print()
    print("  " + "-" * 46)
    print(f"  Checks passed : {passes} / {len(CHECKS)}")
    print(f"  Checks failed : {fails}")
    print()
    if fails:
        print("  RESULT: FAIL")
        print()
        sys.exit(1)
    else:
        print("  RESULT: PASS — contracts/ma_d.yaml meets all PULSE-20 acceptance criteria")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
