"""
validate_principles.py — WARN_NOT_FAIL principle checker

Loads manifests/governance_principles.yaml and optionally
manifests/data_dictionary_master.yaml. Checks fields against
dictionary_fields_required per principle. Emits WARN_P codes.

Exit code is ALWAYS 0 — builds never fail on principle checks.
Warnings written to logs/principle_warnings.log.
"""
import sys
import yaml
import os
from pathlib import Path
from datetime import datetime, timezone

PRINCIPLES_PATH = "manifests/governance_principles.yaml"
MASTER_DICT_PATH = "manifests/data_dictionary_master.yaml"
LOG_PATH = "logs/principle_warnings.log"

WARNINGS = []


def emit_warn(code, message, audit_logged=True):
    entry = f"[{code}] {message}"
    WARNINGS.append({"code": code, "message": message, "audit_logged": audit_logged})
    print(entry)
    return entry


def load_yaml_safe(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_master_dict_fields(principles, master_dict):
    """Check data_dictionary_master.yaml fields against principle requirements."""
    if not master_dict:
        return

    tables = master_dict.get("tables", {})
    if not tables:
        # Try flat list format
        fields = master_dict.get("fields", [])
        if not fields:
            return

    for principle in principles:
        pid = principle.get("id", "")
        required_fields = principle.get("dictionary_fields_required", [])
        violation_code = principle.get("violation_code", f"WARN_{pid}")

        if not required_fields:
            continue

        # Check across all tables
        for table_name, table_data in (tables.items() if isinstance(tables, dict) else {}):
            fields = table_data.get("fields", []) if isinstance(table_data, dict) else []
            for field in fields if isinstance(fields, list) else []:
                field_name = field.get("name", field.get("agent_name", "unknown"))
                for req in required_fields:
                    if req not in field and field.get(req) is None:
                        emit_warn(
                            violation_code,
                            f"Field '{field_name}' in table '{table_name}' — "
                            f"'{req}' declaration missing. Flag for review.",
                        )


def write_log(log_path, warnings):
    """Write all warnings to log file."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n--- validate_principles.py run: {datetime.now(timezone.utc).isoformat()} ---\n")
        if not warnings:
            f.write("  No principle violations detected.\n")
        else:
            for w in warnings:
                f.write(f"  [{w['code']}] {w['message']} (audit_logged={w['audit_logged']})\n")


def main():
    print()
    print("validate_principles.py — WARN_NOT_FAIL principle checker")
    print("=" * 58)
    print()

    # Step 1: Load governance_principles.yaml
    principles_path = Path(PRINCIPLES_PATH)
    if not principles_path.exists():
        emit_warn("WARN_SETUP", f"governance_principles.yaml not found at {PRINCIPLES_PATH}")
        write_log(LOG_PATH, WARNINGS)
        print()
        print("  RESULT: PASS_WITH_WARNINGS — governance_principles.yaml not yet created")
        print()
        sys.exit(0)

    try:
        principles_data = load_yaml_safe(PRINCIPLES_PATH)
    except yaml.YAMLError as e:
        emit_warn("WARN_SETUP", f"governance_principles.yaml parse error: {e}")
        write_log(LOG_PATH, WARNINGS)
        print()
        print("  RESULT: PASS_WITH_WARNINGS — governance_principles.yaml parse error")
        print()
        sys.exit(0)

    principles = principles_data.get("principles", [])
    print(f"  Loaded {len(principles)} principles from {PRINCIPLES_PATH}")

    # Step 2: Load data_dictionary_master.yaml (optional)
    master_dict = None
    master_path = Path(MASTER_DICT_PATH)
    if master_path.exists():
        try:
            master_dict = load_yaml_safe(MASTER_DICT_PATH)
            print(f"  Loaded master dictionary from {MASTER_DICT_PATH}")
        except yaml.YAMLError as e:
            emit_warn("WARN_P6", f"data_dictionary_master.yaml parse error: {e}")
    else:
        print(f"  {MASTER_DICT_PATH} not yet created — skipping field-level checks")

    print()

    # Step 3: Check fields against principle requirements
    if master_dict:
        check_master_dict_fields(principles, master_dict)

    # Step 4: Write log
    write_log(LOG_PATH, WARNINGS)

    # Step 5: Summary
    print()
    print("  " + "-" * 54)
    if not WARNINGS:
        print("  PASS -- no principle violations detected")
        print(f"  Log: {LOG_PATH}")
        print()
    else:
        n = len(WARNINGS)
        print(f"  PASS_WITH_WARNINGS -- {n} violation(s) detected. See {LOG_PATH}")
        print()

    # Always exit 0 — builds never fail on principle checks
    sys.exit(0)


if __name__ == "__main__":
    main()
