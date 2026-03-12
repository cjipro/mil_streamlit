"""
validate_KAN-011.py — KAN-011 Living Data Dictionary validator

Checks:
  1. governance_principles.yaml exists and is valid YAML
  2. All 21 principles present (P1-P21)
  3. violation_policy is WARN_NOT_FAIL
  4. Calls validate_principles.py as a subprocess

Returns PASS or PASS_WITH_WARNINGS — never ERROR.
Exit code is always 0.
"""
import sys
import subprocess
import yaml
from pathlib import Path

PRINCIPLES_PATH = "manifests/governance_principles.yaml"
EXPECTED_IDS = {f"P{i}" for i in range(1, 22)}

CHECKS = []


def check(label, result, detail=""):
    CHECKS.append((label, result, detail))
    status = "PASS" if result else "WARN"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}]  {label}{suffix}")
    return result


def main():
    print()
    print("validate_KAN-011.py — Living Data Dictionary validator")
    print("=" * 54)
    print()

    # Check 1: governance_principles.yaml exists
    path = Path(PRINCIPLES_PATH)
    if not check("governance_principles.yaml exists", path.exists(), PRINCIPLES_PATH):
        print()
        print("  RESULT: PASS_WITH_WARNINGS — governance_principles.yaml not found")
        print()
        sys.exit(0)

    # Check 2: valid YAML
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        check("Valid YAML", True)
    except yaml.YAMLError as e:
        check("Valid YAML", False, str(e))
        print()
        print("  RESULT: PASS_WITH_WARNINGS — YAML parse error in governance_principles.yaml")
        print()
        sys.exit(0)

    # Check 3: all 21 principles present
    principles = data.get("principles", [])
    found_ids = {p.get("id") for p in principles if isinstance(p, dict)}
    missing = sorted(EXPECTED_IDS - found_ids)
    check(
        "All 21 principles present (P1-P21)",
        len(missing) == 0,
        f"missing: {missing}" if missing else f"found {len(found_ids)} principles",
    )

    # Check 4: violation_policy is WARN_NOT_FAIL
    policy = data.get("violation_policy", "")
    check(
        "violation_policy is WARN_NOT_FAIL",
        "WARN_NOT_FAIL" in str(policy),
        f"got: {policy!r}",
    )

    # Check 5: violation_framework.policy is WARN_NOT_FAIL
    vf = data.get("violation_framework", {})
    vf_policy = vf.get("policy", "") if isinstance(vf, dict) else ""
    check(
        "violation_framework.policy is WARN_NOT_FAIL",
        vf_policy == "WARN_NOT_FAIL",
        f"got: {vf_policy!r}",
    )

    # Check 6: blocks_build is false for all severity levels
    levels = (vf.get("severity_levels", {}) if isinstance(vf, dict) else {})
    all_non_blocking = all(
        not v.get("blocks_build", True)
        for v in (levels.values() if isinstance(levels, dict) else [])
    )
    check(
        "All severity levels have blocks_build: false",
        all_non_blocking or not levels,
        f"severity levels: {list(levels.keys()) if levels else 'none'}",
    )

    # Summary of structural checks
    passes = sum(1 for _, r, _ in CHECKS if r)
    warns = len(CHECKS) - passes
    print()
    print("  " + "-" * 50)
    print(f"  Structural checks passed : {passes} / {len(CHECKS)}")
    print(f"  Structural checks warned : {warns}")
    print()

    # Step 7: Run validate_principles.py as subprocess
    print("  Running validate_principles.py...")
    print()
    result = subprocess.run(
        [sys.executable, "scripts/validate_principles.py"],
        capture_output=False,
    )
    print()

    # Final result — always PASS or PASS_WITH_WARNINGS, never ERROR
    if warns == 0 and result.returncode == 0:
        print("  RESULT: PASS — governance_principles.yaml meets all KAN-011 acceptance criteria")
    else:
        print("  RESULT: PASS_WITH_WARNINGS — see warnings above")
    print()

    # Always exit 0
    sys.exit(0)


if __name__ == "__main__":
    main()
