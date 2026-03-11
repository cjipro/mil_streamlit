"""
validate_KAN-013.py
Validates manifests/audit_findings.yaml against the KAN-13 acceptance criteria.

Checks:
  - Required top-level metadata present: schema_version, generated_by, purpose, last_updated
  - findings is a non-empty list
  - Required findings present: FINDING-001, FINDING-002, FINDING-003
  - FINDING-002 severity is CRITICAL
  - Each finding has all required fields:
      id, severity, status, description, business_impact, action_required,
      owner, data_owner_signoff_required, resolution, fallback_if_unresolved
  - severity values: CRITICAL / HIGH / MEDIUM / LOW
  - status values: OPEN / RESOLVED / ACCEPTED-WITH-FALLBACK / BLOCKED
  - No finding is RESOLVED without data_owner_signoff_required = true

Run: py scripts/validate_KAN-013.py
"""

import yaml
import sys
from pathlib import Path

SPEC_PATH = "manifests/audit_findings.yaml"

REQUIRED_FINDING_FIELDS = [
    "id",
    "severity",
    "status",
    "description",
    "business_impact",
    "action_required",
    "owner",
    "data_owner_signoff_required",
    "resolution",
    "fallback_if_unresolved",
]

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_STATUSES = {"OPEN", "RESOLVED", "ACCEPTED-WITH-FALLBACK", "BLOCKED"}

REQUIRED_FINDING_IDS = {"FINDING-001", "FINDING-002", "FINDING-003"}


def validate(spec_path: str) -> bool:
    print(f"\n{'='*60}")
    print("CJI Pulse — validate_KAN-013.py")
    print(f"Validating: {spec_path}")
    print(f"{'='*60}\n")

    path = Path(spec_path)
    if not path.exists():
        print(f"ERROR: audit_findings.yaml not found at '{spec_path}'")
        print("RESULT: FAILED\n")
        return False

    try:
        with open(path, "r") as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error: {e}")
        print("RESULT: FAILED\n")
        return False

    errors = []
    warnings = []

    # --- Top-level metadata ---
    print("Checking top-level metadata...")
    for field in ["schema_version", "generated_by", "purpose", "last_updated"]:
        if field not in spec:
            errors.append(f"MISSING top-level field: '{field}'")
        else:
            print(f"  [OK] {field}: {str(spec[field])[:60]}")

    # --- findings list ---
    print("\nChecking findings list...")
    findings = spec.get("findings")
    if not findings or not isinstance(findings, list):
        errors.append("MISSING or empty 'findings' list")
        # Cannot continue without findings
        _print_summary(errors, warnings)
        return False

    print(f"  [OK] {len(findings)} finding(s) present")

    # --- Index findings by id ---
    findings_by_id = {}
    for entry in findings:
        fid = entry.get("id")
        if not fid:
            errors.append(f"Finding entry missing 'id' field: {entry}")
        else:
            findings_by_id[fid] = entry

    # --- Required findings present ---
    print("\nChecking required findings are present...")
    for required_id in sorted(REQUIRED_FINDING_IDS):
        if required_id not in findings_by_id:
            errors.append(f"MISSING required finding: '{required_id}'")
        else:
            print(f"  [OK] {required_id} present")

    # --- Validate each finding ---
    print("\nValidating finding fields...")
    for finding in findings:
        fid = finding.get("id", "<unknown>")

        # Required fields
        for field in REQUIRED_FINDING_FIELDS:
            if field not in finding:
                errors.append(f"{fid}: MISSING required field '{field}'")

        # severity enum
        severity = finding.get("severity", "")
        if severity not in VALID_SEVERITIES:
            errors.append(
                f"{fid}: invalid severity '{severity}'. Must be one of {sorted(VALID_SEVERITIES)}"
            )

        # status enum
        status = finding.get("status", "")
        if status not in VALID_STATUSES:
            errors.append(
                f"{fid}: invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}"
            )

        # RESOLVED requires data_owner_signoff_required = true
        if status == "RESOLVED":
            if finding.get("data_owner_signoff_required") is not True:
                errors.append(
                    f"{fid}: status is RESOLVED but data_owner_signoff_required is not true. "
                    "Data owner sign-off required before marking RESOLVED."
                )

        if fid not in [f"<unknown>"] and severity in VALID_SEVERITIES and status in VALID_STATUSES:
            print(f"  [OK] {fid}: severity={severity}, status={status}")

    # --- FINDING-002 must be CRITICAL ---
    print("\nChecking FINDING-002 is CRITICAL...")
    f002 = findings_by_id.get("FINDING-002")
    if f002:
        if f002.get("severity") != "CRITICAL":
            errors.append(
                f"FINDING-002 severity must be CRITICAL (blocks Phase 1 mission). "
                f"Got: '{f002.get('severity')}'"
            )
        else:
            print("  [OK] FINDING-002 severity = CRITICAL")
    else:
        # Already reported as missing above
        pass

    _print_summary(errors, warnings)

    if errors:
        print("RESULT: FAILED — audit_findings.yaml does not meet KAN-13 acceptance criteria.")
        print(f"{'='*60}\n")
        return False
    else:
        print("RESULT: PASSED — audit_findings.yaml meets all KAN-13 acceptance criteria.")
        print("No pipeline may be built against an affected table until all findings are RESOLVED")
        print("or ACCEPTED-WITH-FALLBACK.")
        print(f"{'='*60}\n")
        return True


def _print_summary(errors: list, warnings: list) -> None:
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ERROR: {e}")

    print(f"{'='*60}")


if __name__ == "__main__":
    spec_path = sys.argv[1] if len(sys.argv) > 1 else SPEC_PATH
    success = validate(spec_path)
    sys.exit(0 if success else 1)
