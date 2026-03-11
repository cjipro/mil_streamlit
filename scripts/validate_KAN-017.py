"""
validate_KAN-017.py
Validates system_manifest.yaml against the v5 schema.
Every component must have all required fields.
Run: python scripts/validate_KAN-017.py
"""

import yaml
import sys
from pathlib import Path

REQUIRED_CORE_FIELDS = [
    "id", "name", "sprint", "days", "type", "owner", "status", "priority",
    "estimated_effort_hours", "tool", "jira_id", "gitlab_branch",
    "manifest_path", "gitlab_path", "purpose", "inputs", "outputs",
    "dependencies", "acceptance_criteria", "validation_command",
    "graduated_trust_tier", "runtime_permissions", "recovery_patterns",
    "interfaces", "traceability"
]

REQUIRED_RECOVERY_FIELDS = ["failure_modes", "retry_logic", "fallback_strategy", "escalation_criteria"]
REQUIRED_INTERFACE_FIELDS = ["inputs_expected", "outputs_promised", "breaking_change_protocol"]

VALID_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "BUILT", "PARTIAL-P1", "PARTIAL-P2",
                  "PARTIAL-P3", "BLOCKED", "MANUAL-BUILT", "DEGRADED"]
VALID_PRIORITIES = ["P1", "P2", "P3"]
VALID_TIERS = [1, 2, 3, 4]
VALID_TYPES = [
    "Deployment Config", "Control Artefact", "Data Contract",
    "Pipeline", "Agent", "UI Component"
]

VALID_SPRINTS = list(range(1, 14))

# Tickets that should have prompt_breakdown (>4h complex tickets)
COMPLEX_TICKET_IDS = [
    "KAN-14", "KAN-17", "KAN-18", "KAN-23", "KAN-30", "KAN-40",
    "KAN-42", "KAN-50", "KAN-61", "KAN-71", "KAN-74", "KAN-90",
    "KAN-104"
]

DATA_CONTRACT_TYPES = ["Data Contract"]


def validate_manifest(manifest_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"CJI Pulse — validate_KAN-017.py")
    print(f"Validating: {manifest_path}")
    print(f"{'='*60}\n")

    try:
        with open(manifest_path, "r") as f:
            manifest = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: manifest file not found at {manifest_path}")
        return False
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error: {e}")
        return False

    errors = []
    warnings = []

    # --- Top-level metadata ---
    required_meta = ["schema_version", "programme", "description", "day_90_vision",
                     "repo", "jira_project", "jira_url", "owner", "last_updated",
                     "programme_principles", "dual_closure_rule", "components"]
    for field in required_meta:
        if field not in manifest:
            errors.append(f"MISSING top-level field: '{field}'")

    if "components" not in manifest:
        print(f"FATAL: 'components' key missing from manifest. Cannot validate components.")
        for e in errors:
            print(f"  ERROR: {e}")
        return False

    components = manifest["components"]
    if not isinstance(components, list):
        print("FATAL: 'components' must be a list.")
        return False

    print(f"Found {len(components)} components to validate.\n")

    # --- Track IDs for dependency validation ---
    all_ids = {c.get("id") for c in components if "id" in c}
    id_counts = {}
    for c in components:
        cid = c.get("id", "MISSING_ID")
        id_counts[cid] = id_counts.get(cid, 0) + 1

    # --- Validate each component ---
    for i, component in enumerate(components):
        cid = component.get("id", f"COMPONENT_{i}")
        comp_errors = []
        comp_warnings = []

        # Check for duplicate IDs
        if id_counts.get(cid, 0) > 1:
            comp_errors.append(f"DUPLICATE component ID '{cid}'")

        # Core required fields
        for field in REQUIRED_CORE_FIELDS:
            if field not in component:
                comp_errors.append(f"MISSING required field: '{field}'")

        # Status validation
        status = component.get("status", "")
        if status not in VALID_STATUSES:
            comp_errors.append(f"INVALID status '{status}'. Must be one of: {VALID_STATUSES}")

        # Priority validation
        priority = component.get("priority", "")
        if priority not in VALID_PRIORITIES:
            comp_errors.append(f"INVALID priority '{priority}'. Must be one of: {VALID_PRIORITIES}")

        # Trust tier validation
        tier = component.get("graduated_trust_tier")
        if tier not in VALID_TIERS:
            comp_errors.append(f"INVALID graduated_trust_tier '{tier}'. Must be one of: {VALID_TIERS}")

        # Type validation
        comp_type = component.get("type", "")
        if comp_type not in VALID_TYPES:
            comp_errors.append(f"INVALID type '{comp_type}'. Must be one of: {VALID_TYPES}")

        # Sprint validation
        sprint = component.get("sprint")
        if sprint not in VALID_SPRINTS:
            comp_errors.append(f"INVALID sprint '{sprint}'. Must be 1-13.")

        # Effort validation
        effort = component.get("estimated_effort_hours")
        if not isinstance(effort, (int, float)) or effort <= 0:
            comp_errors.append(f"INVALID estimated_effort_hours '{effort}'. Must be a positive number.")

        # recovery_patterns validation
        rp = component.get("recovery_patterns", {})
        if isinstance(rp, dict):
            for rf in REQUIRED_RECOVERY_FIELDS:
                if rf not in rp:
                    comp_errors.append(f"MISSING recovery_patterns.{rf}")
        else:
            comp_errors.append("recovery_patterns must be a dict")

        # interfaces validation
        ifaces = component.get("interfaces", {})
        if isinstance(ifaces, dict):
            for iff in REQUIRED_INTERFACE_FIELDS:
                if iff not in ifaces:
                    comp_errors.append(f"MISSING interfaces.{iff}")
        else:
            comp_errors.append("interfaces must be a dict")

        # acceptance_criteria non-empty
        ac = component.get("acceptance_criteria", [])
        if not ac or not isinstance(ac, list) or len(ac) == 0:
            comp_errors.append("acceptance_criteria must be a non-empty list")

        # outputs non-empty
        outputs = component.get("outputs", [])
        if not outputs or not isinstance(outputs, list) or len(outputs) == 0:
            comp_errors.append("outputs must be a non-empty list")

        # validation_command non-empty
        vc = component.get("validation_command", "")
        if not vc or not isinstance(vc, str) or len(vc.strip()) == 0:
            comp_errors.append("validation_command must be a non-empty string")

        # jira_id can be blank (not yet created) but must exist as a field
        if "jira_id" not in component:
            comp_errors.append("MISSING jira_id field (can be blank but must exist)")

        # Complex tickets should have prompt_breakdown
        if cid in COMPLEX_TICKET_IDS:
            if "prompt_breakdown" not in component:
                comp_warnings.append(f"Complex ticket (>4h) MISSING prompt_breakdown")

        # Data contracts should have governance_attributes
        if comp_type in DATA_CONTRACT_TYPES:
            if "governance_attributes" not in component:
                comp_warnings.append("Data contract MISSING governance_attributes")

        # Dependency validation — check all listed dependencies exist
        deps = component.get("dependencies", [])
        for dep in deps:
            if dep not in all_ids:
                comp_errors.append(f"UNKNOWN dependency '{dep}' — not found in manifest")

        # Runtime permissions must be a list
        rperms = component.get("runtime_permissions", [])
        if not isinstance(rperms, list):
            comp_errors.append("runtime_permissions must be a list")

        # Print results for this component
        if comp_errors or comp_warnings:
            print(f"  [{cid}] {component.get('name', 'UNNAMED')}")
            for e in comp_errors:
                print(f"    ERROR: {e}")
                errors.append(f"[{cid}] {e}")
            for w in comp_warnings:
                print(f"    WARN:  {w}")
                warnings.append(f"[{cid}] {w}")
        else:
            print(f"  [{cid}] OK — {component.get('name', 'UNNAMED')}")

    # --- Dependency cycle detection (simple) ---
    print("\nChecking for dependency cycles...")
    dep_map = {c.get("id"): c.get("dependencies", []) for c in components}

    def has_cycle(node, visited, rec_stack):
        visited.add(node)
        rec_stack.add(node)
        for dep in dep_map.get(node, []):
            if dep not in visited:
                if has_cycle(dep, visited, rec_stack):
                    return True
            elif dep in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    visited = set()
    for node in dep_map:
        if node not in visited:
            if has_cycle(node, visited, set()):
                errors.append(f"DEPENDENCY CYCLE detected involving {node}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Components validated: {len(components)}")
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
        print("RESULT: FAILED — Fix all errors before proceeding.")
        print(f"{'='*60}\n")
        return False
    else:
        print(f"\n{'='*60}")
        print("RESULT: PASSED — system_manifest.yaml is valid.")
        print("An AI agent reading this manifest can build the entire system.")
        print(f"{'='*60}\n")
        return True


if __name__ == "__main__":
    manifest_path = sys.argv[1] if len(sys.argv) > 1 else "manifests/system_manifest.yaml"
    success = validate_manifest(manifest_path)
    sys.exit(0 if success else 1)
