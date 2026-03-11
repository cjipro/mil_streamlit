import sys
import argparse
import yaml
import json

MANIFEST_PATH = "manifests/system_manifest.yaml"


def emit_telemetry(step_id, input_reference, output_summary, error_code, error_class,
                   retryability, business_impact_tier, downstream_dependency_impact,
                   manifest_spec_reference, recovery_strategy_reference):
    telemetry = {
        "step_id": step_id,
        "input_reference": input_reference,
        "output_summary": output_summary,
        "error_code": error_code,
        "error_class": error_class,
        "retryability": retryability,
        "business_impact_tier": business_impact_tier,
        "downstream_dependency_impact": downstream_dependency_impact,
        "manifest_spec_reference": manifest_spec_reference,
        "recovery_strategy_reference": recovery_strategy_reference,
    }
    print(json.dumps(telemetry, indent=2), file=sys.stderr)


def load_manifest():
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        emit_telemetry(
            step_id="build_from_manifest.load_manifest",
            input_reference=MANIFEST_PATH,
            output_summary=f"Manifest file not found at {MANIFEST_PATH} — cannot load components",
            error_code="PIPELINE-001",
            error_class="PIPELINE",
            retryability="yes",
            business_impact_tier="P1",
            downstream_dependency_impact="All builds blocked — manifest is required",
            manifest_spec_reference="manifests/system_manifest.yaml#KAN-17",
            recovery_strategy_reference="manifests/system_manifest.yaml#KAN-18.recovery_patterns",
        )
        print(f"ERROR: Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        emit_telemetry(
            step_id="build_from_manifest.parse_manifest",
            input_reference=MANIFEST_PATH,
            output_summary=f"YAML parse error in manifest — {e}",
            error_code="SCHEMA-001",
            error_class="SCHEMA",
            retryability="no",
            business_impact_tier="P1",
            downstream_dependency_impact="All builds blocked — manifest is unparseable",
            manifest_spec_reference="manifests/system_manifest.yaml#KAN-17",
            recovery_strategy_reference="manifests/system_manifest.yaml#KAN-18.recovery_patterns",
        )
        print(f"ERROR: YAML parse error: {e}", file=sys.stderr)
        sys.exit(1)


def print_component_detail(component):
    print()
    print(f"  ID              : {component.get('id', '')}")
    print(f"  Name            : {component.get('name', '')}")
    print(f"  Status          : {component.get('status', '')}")
    print(f"  Sprint          : {component.get('sprint', '')}")
    print(f"  Type            : {component.get('type', '')}")
    print(f"  Priority        : {component.get('priority', '')}")
    print(f"  GitLab Path     : {component.get('gitlab_path', '')}")
    print(f"  Validation Cmd  : {component.get('validation_command', '')}")
    deps = component.get("dependencies", [])
    print(f"  Dependencies    : {', '.join(deps) if deps else 'none'}")
    criteria = component.get("acceptance_criteria", [])
    if criteria:
        print("  Acceptance Criteria:")
        for c in criteria:
            print(f"    - {c}")
    print()


def print_summary_table(components, dry_run=False):
    header = "DRY RUN — no changes will be made" if dry_run else "Build summary"
    print()
    print(f"  {header}")
    print()
    col_id   = 10
    col_name = 52
    col_stat = 16
    col_spr  = 6
    print(f"  {'ID':<{col_id}} {'Name':<{col_name}} {'Status':<{col_stat}} {'Sprint':<{col_spr}}")
    print(f"  {'-'*col_id} {'-'*col_name} {'-'*col_stat} {'-'*col_spr}")
    for c in components:
        cid   = str(c.get("id", ""))[:col_id]
        cname = str(c.get("name", ""))[:col_name]
        cstat = str(c.get("status", ""))[:col_stat]
        cspr  = str(c.get("sprint", ""))[:col_spr]
        print(f"  {cid:<{col_id}} {cname:<{col_name}} {cstat:<{col_stat}} {cspr:<{col_spr}}")
    print()
    print(f"  Total: {len(components)} component(s)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="CJI Pulse — build_from_manifest.py — executable manifest runner"
    )
    parser.add_argument("--component", type=str, help="Target a specific component by ID (e.g. KAN-013)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be built without executing")
    parser.add_argument("--status", type=str, help="Filter components by status (e.g. BUILT, NOT_STARTED)")
    parser.add_argument("--sprint", type=int, help="Filter components by sprint number (e.g. 1)")
    args = parser.parse_args()

    manifest = load_manifest()
    components = manifest.get("components", [])

    if not components:
        emit_telemetry(
            step_id="build_from_manifest.load_components",
            input_reference=MANIFEST_PATH,
            output_summary="No components found in manifest — components list is empty or missing",
            error_code="SCHEMA-002",
            error_class="SCHEMA",
            retryability="no",
            business_impact_tier="P1",
            downstream_dependency_impact="All builds blocked — no components to process",
            manifest_spec_reference="manifests/system_manifest.yaml#KAN-17",
            recovery_strategy_reference="manifests/system_manifest.yaml#KAN-18.recovery_patterns",
        )
        print("ERROR: No components found in manifest.", file=sys.stderr)
        sys.exit(1)

    # Apply filters
    filtered = list(components)

    if args.component:
        filtered = [c for c in filtered if c.get("id") == args.component]
        if not filtered:
            emit_telemetry(
                step_id="build_from_manifest.find_component",
                input_reference=MANIFEST_PATH,
                output_summary=f"Component {args.component} not found in manifest",
                error_code="DEPENDENCY-001",
                error_class="DEPENDENCY",
                retryability="no",
                business_impact_tier="P2",
                downstream_dependency_impact=f"Build of {args.component} cannot proceed",
                manifest_spec_reference=f"manifests/system_manifest.yaml#{args.component}",
                recovery_strategy_reference="manifests/system_manifest.yaml#KAN-18.recovery_patterns",
            )
            print(f"ERROR: Component '{args.component}' not found in manifest.", file=sys.stderr)
            sys.exit(1)

    if args.status:
        filtered = [c for c in filtered if c.get("status") == args.status]

    if args.sprint is not None:
        filtered = [c for c in filtered if c.get("sprint") == args.sprint]

    # Output
    if args.dry_run:
        if args.component and len(filtered) == 1:
            print(f"\n[DRY RUN] Component detail for {args.component}:")
            print_component_detail(filtered[0])
        print_summary_table(filtered, dry_run=True)
    else:
        print_summary_table(filtered, dry_run=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
