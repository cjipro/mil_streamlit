"""
validate_PULSE-18.py — validator for PULSE-18 build_from_manifest.py
Runs: py scripts/build_from_manifest.py --component PULSE-13 --dry-run
Validates: exit code 0, output contains expected fields.
"""
import subprocess
import sys


def main():
    errors = []

    print("validate_PULSE-18.py — running build_from_manifest.py --component PULSE-13 --dry-run")
    print()

    result = subprocess.run(
        [sys.executable, "scripts/build_from_manifest.py", "--component", "PULSE-13", "--dry-run"],
        capture_output=True,
        text=True,
    )

    stdout = result.stdout
    stderr = result.stderr
    exit_code = result.returncode

    print("--- stdout ---")
    print(stdout)
    if stderr:
        print("--- stderr ---")
        print(stderr)
    print(f"--- exit code: {exit_code} ---")
    print()

    # Check 1: exit code 0
    if exit_code != 0:
        errors.append(f"FAIL: exit code was {exit_code}, expected 0")
    else:
        print("PASS: exit code 0")

    # Check 2: PULSE-13 appears in stdout
    if "PULSE-13" not in stdout:
        errors.append("FAIL: 'PULSE-13' not found in stdout")
    else:
        print("PASS: PULSE-13 found in output")

    # Check 3: key fields present
    for field in ["Status", "Sprint", "GitLab Path", "DRY RUN"]:
        if field not in stdout:
            errors.append(f"FAIL: expected field '{field}' not found in stdout")
        else:
            print(f"PASS: '{field}' present in output")

    # Check 4: output is not empty
    if len(stdout.strip()) < 10:
        errors.append("FAIL: stdout suspiciously short — likely empty output")
    else:
        print("PASS: stdout has content")

    print()
    if errors:
        print(f"RESULT: FAIL — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("RESULT: PASS — validate_PULSE-18.py all checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
