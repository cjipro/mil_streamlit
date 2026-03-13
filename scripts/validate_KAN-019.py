"""
validate_PULSE-19.py
Validates manifests/telemetry_spec.yaml against the PULSE-19 acceptance criteria.

Checks:
  - Required fields present: step_id, input_reference, output_summary,
    error_code, error_class, retryability, business_impact_tier,
    downstream_dependency_impact, manifest_spec_reference, recovery_strategy_reference
  - error_class enum: DATA_QUALITY / PIPELINE / SCHEMA / DEPENDENCY / GOVERNANCE
  - retryability values: yes / no / backoff
  - business_impact_tier values: P1 / P2 / P3
  - error_code_registry present and non-empty for each class
  - usage_contract section present and mandatory=true
  - usage_contract applies to ALL pipelines

Run: python scripts/validate_PULSE-19.py
"""

import yaml
import sys
from pathlib import Path

SPEC_PATH = "manifests/telemetry_spec.yaml"

REQUIRED_FIELDS = [
    "step_id",
    "input_reference",
    "output_summary",
    "error_code",
    "error_class",
    "retryability",
    "business_impact_tier",
    "downstream_dependency_impact",
    "manifest_spec_reference",
    "recovery_strategy_reference",
]

VALID_ERROR_CLASSES = {"DATA_QUALITY", "PIPELINE", "SCHEMA", "DEPENDENCY", "GOVERNANCE"}
VALID_RETRYABILITY = {"yes", "no", "backoff"}
VALID_IMPACT_TIERS = {"P1", "P2", "P3"}

REQUIRED_FIELD_KEYS = ["type", "required", "description"]


def validate_spec(spec_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"CJI Pulse — validate_PULSE-19.py")
    print(f"Validating: {spec_path}")
    print(f"{'='*60}\n")

    path = Path(spec_path)
    if not path.exists():
        print(f"ERROR: Telemetry spec not found at '{spec_path}'")
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
    for meta_field in ["schema_version", "spec_id", "name", "description", "owner",
                        "created", "last_updated", "manifest_reference"]:
        if meta_field not in spec:
            errors.append(f"MISSING top-level field: '{meta_field}'")
        else:
            print(f"  [OK] {meta_field}: {str(spec[meta_field])[:60]}")

    # --- Fields section ---
    print("\nChecking fields section...")
    fields = spec.get("fields")
    if not fields or not isinstance(fields, dict):
        errors.append("MISSING or empty 'fields' section")
    else:
        # Check all required fields are defined
        for req in REQUIRED_FIELDS:
            if req not in fields:
                errors.append(f"MISSING required field definition: '{req}'")
            else:
                field_def = fields[req]
                if not isinstance(field_def, dict):
                    errors.append(f"Field '{req}' definition must be a dict")
                else:
                    for fk in REQUIRED_FIELD_KEYS:
                        if fk not in field_def:
                            errors.append(f"Field '{req}' missing sub-key: '{fk}'")
                    print(f"  [OK] field '{req}' defined")

        # --- error_class enum validation ---
        print("\nChecking error_class enum values...")
        ec_def = fields.get("error_class", {})
        allowed = ec_def.get("allowed_values", [])
        if not allowed:
            errors.append("error_class field missing 'allowed_values'")
        else:
            actual_set = set(allowed)
            missing = VALID_ERROR_CLASSES - actual_set
            extra = actual_set - VALID_ERROR_CLASSES
            if missing:
                errors.append(f"error_class missing required enum values: {missing}")
            if extra:
                warnings.append(f"error_class has extra enum values not in spec: {extra}")
            if not missing:
                print(f"  [OK] error_class enum: {sorted(actual_set)}")

        # --- retryability enum validation ---
        print("\nChecking retryability enum values...")
        rt_def = fields.get("retryability", {})
        rt_allowed = set(rt_def.get("allowed_values", []))
        missing_rt = VALID_RETRYABILITY - rt_allowed
        if missing_rt:
            errors.append(f"retryability missing required values: {missing_rt}")
        else:
            print(f"  [OK] retryability values: {sorted(rt_allowed)}")

        # --- business_impact_tier enum validation ---
        print("\nChecking business_impact_tier enum values...")
        bit_def = fields.get("business_impact_tier", {})
        bit_allowed = set(bit_def.get("allowed_values", []))
        missing_bit = VALID_IMPACT_TIERS - bit_allowed
        if missing_bit:
            errors.append(f"business_impact_tier missing required values: {missing_bit}")
        else:
            print(f"  [OK] business_impact_tier values: {sorted(bit_allowed)}")

    # --- error_code_registry ---
    print("\nChecking error_code_registry...")
    registry = spec.get("error_code_registry")
    if not registry or not isinstance(registry, dict):
        errors.append("MISSING or empty 'error_code_registry' section")
    else:
        for ec in VALID_ERROR_CLASSES:
            if ec not in registry:
                errors.append(f"error_code_registry missing class: '{ec}'")
            else:
                entries = registry[ec]
                if not isinstance(entries, list) or len(entries) == 0:
                    errors.append(f"error_code_registry['{ec}'] must be a non-empty list")
                else:
                    # Validate each entry has required keys
                    for entry in entries:
                        for key in ["code", "description", "retryability",
                                    "default_business_impact_tier"]:
                            if key not in entry:
                                errors.append(
                                    f"error_code_registry['{ec}'] entry missing key: '{key}'"
                                )
                        # Validate code format
                        code = entry.get("code", "")
                        if not code.startswith(f"{ec}-"):
                            errors.append(
                                f"error_code '{code}' does not match class prefix '{ec}-'"
                            )
                        # Validate retryability value
                        rt_val = entry.get("retryability", "")
                        if rt_val not in VALID_RETRYABILITY:
                            errors.append(
                                f"error_code_registry['{ec}'] entry '{code}' "
                                f"has invalid retryability '{rt_val}'"
                            )
                        # Validate business_impact_tier
                        bit_val = entry.get("default_business_impact_tier", "")
                        if bit_val not in VALID_IMPACT_TIERS:
                            errors.append(
                                f"error_code_registry['{ec}'] entry '{code}' "
                                f"has invalid default_business_impact_tier '{bit_val}'"
                            )
                    print(f"  [OK] {ec}: {len(entries)} code(s) registered")

    # --- usage_contract ---
    print("\nChecking usage_contract section...")
    uc = spec.get("usage_contract")
    if not uc or not isinstance(uc, dict):
        errors.append("MISSING or empty 'usage_contract' section")
    else:
        # mandatory must be true
        if uc.get("mandatory") is not True:
            errors.append("usage_contract.mandatory must be true")
        else:
            print("  [OK] usage_contract.mandatory = true")

        # must apply to ALL pipelines
        applies = uc.get("applies_to", "")
        if "ALL" not in str(applies).upper():
            errors.append(
                f"usage_contract.applies_to must reference ALL pipelines. Got: '{applies}'"
            )
        else:
            print(f"  [OK] usage_contract.applies_to: '{applies}'")

        # rules must be non-empty list
        rules = uc.get("rules", [])
        if not rules or not isinstance(rules, list) or len(rules) == 0:
            errors.append("usage_contract.rules must be a non-empty list")
        else:
            for rule in rules:
                if "id" not in rule or "rule" not in rule:
                    errors.append("usage_contract rule entry missing 'id' or 'rule' key")
            print(f"  [OK] usage_contract.rules: {len(rules)} rule(s) defined")

        # enforcement block
        enforcement = uc.get("enforcement", {})
        if not enforcement:
            warnings.append("usage_contract missing 'enforcement' block")
        else:
            if "validation_command" not in enforcement:
                warnings.append("usage_contract.enforcement missing 'validation_command'")
            if "non_compliance_action" not in enforcement:
                warnings.append("usage_contract.enforcement missing 'non_compliance_action'")
            print("  [OK] usage_contract.enforcement defined")

    # --- Summary ---
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
        print(f"\n{'='*60}")
        print("RESULT: FAILED — telemetry_spec.yaml does not meet PULSE-19 acceptance criteria.")
        print(f"{'='*60}\n")
        return False
    else:
        print(f"\n{'='*60}")
        print("RESULT: PASSED — telemetry_spec.yaml meets all PULSE-19 acceptance criteria.")
        print("Every pipeline in the programme must import and use this spec.")
        print(f"{'='*60}\n")
        return True


if __name__ == "__main__":
    spec_path = sys.argv[1] if len(sys.argv) > 1 else SPEC_PATH
    success = validate_spec(spec_path)
    sys.exit(0 if success else 1)
