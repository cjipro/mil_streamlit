"""
validate_KAN-1G.py
Validates manifests/graduated_trust_tiers.yaml against KAN-1G acceptance criteria.

Pre-flight enhancements:
  1. TELEMETRY INTEGRATION — loads telemetry_spec.yaml, validates that
     privilege_escalation_event conforms to the telemetry spec field schema,
     and checks that GOVERNANCE-TRUST-001 (error_code GOVERNANCE-004,
     error_class GOVERNANCE) is correctly structured.
  2. IDENTITY MAPPING — validates identity_model section with principal_id as
     the generic key (identity-agnostic), and component_scope on every operator tier.
  3. TRACEABILITY LAW — validates law_for field lists required agent manifests
     (narrative-agent, governance-agent).

Core checks:
  - Operator tiers 1-4 present with required fields + component_scope
  - Phase 1 maximum constraints enforced in spec
  - Finding trust tiers: UNVERIFIED / PROVISIONAL / VALIDATED / TRUSTED
  - response_mode_definitions cover all 5 modes
  - Demotion rules present and each has required fields
  - Interaction matrix covers all 4 operator tiers
  - usage_contract present, mandatory=true, applies to ALL

Run: python scripts/validate_KAN-1G.py
"""

import re
import yaml
import sys
from pathlib import Path

SPEC_PATH = "manifests/graduated_trust_tiers.yaml"
TELEMETRY_SPEC_PATH = "manifests/telemetry_spec.yaml"

REQUIRED_OPERATOR_TIERS = [1, 2, 3, 4]
REQUIRED_OPERATOR_FIELDS = [
    "tier", "name", "label", "description", "permissions",
    "restricted_from", "how_to_earn", "phase_1_maximum_for",
    "approval_required_from", "component_scope",
]

REQUIRED_FINDING_TIERS = ["UNVERIFIED", "PROVISIONAL", "VALIDATED", "TRUSTED"]
REQUIRED_FINDING_FIELDS = [
    "tier", "ordinal", "description", "response_mode_link", "display_label",
    "permitted_actions", "blocked_actions", "promotion_conditions",
]

REQUIRED_RESPONSE_MODES = {"EVIDENCED", "DIRECTIONAL", "UNKNOWN", "GUARDED", "CONTRADICTED"}
REQUIRED_RESPONSE_FIELDS = ["description", "permitted_finding_tiers", "display_colour"]

REQUIRED_DEMOTION_FIELDS = [
    "id", "trigger", "from_tiers", "demoted_to", "automatic",
    "override_permitted", "action_on_demotion",
]

REQUIRED_MATRIX_OPERATOR_TIERS = [1, 2, 3, 4]
REQUIRED_MATRIX_FIELDS = ["operator_tier", "can_view", "can_approve", "can_promote", "can_demote"]

VALID_FINDING_TIERS = set(REQUIRED_FINDING_TIERS)
PHASE_1_TIER_3_KEYWORDS = ["journey owner", "journey owners"]
PHASE_1_TIER_4_KEYWORDS = ["analytics lead"]

# Telemetry spec required fields that privilege_escalation_event must populate
TELEMETRY_REQUIRED_FIELDS = [
    "step_id", "input_reference", "output_summary", "error_code",
    "error_class", "retryability", "business_impact_tier",
    "downstream_dependency_impact", "manifest_spec_reference",
    "recovery_strategy_reference",
]

# Expected values for GOVERNANCE-TRUST-001
ESCALATION_EXPECTED_ERROR_CLASS = "GOVERNANCE"
ESCALATION_EXPECTED_ERROR_CODE = "GOVERNANCE-004"
ESCALATION_EXPECTED_RETRYABILITY = "no"
ESCALATION_EXPECTED_IMPACT_TIER = "P1"
ESCALATION_LOGICAL_ID = "GOVERNANCE-TRUST-001"

# law_for: agent manifests required to reference this config
REQUIRED_LAW_FOR_AGENTS = {"narrative-agent", "governance-agent"}

ERROR_CODE_PATTERN = re.compile(
    r"^(DATA_QUALITY|PIPELINE|SCHEMA|DEPENDENCY|GOVERNANCE)-[0-9]{3}$"
)


def load_yaml(path: str):
    p = Path(path)
    if not p.exists():
        return None, f"File not found: '{path}'"
    try:
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except yaml.YAMLError as e:
        return None, f"YAML parse error in '{path}': {e}"


def validate_spec(spec_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"CJI Pulse — validate_KAN-1G.py")
    print(f"Validating: {spec_path}")
    print(f"{'='*60}\n")

    spec, err = load_yaml(spec_path)
    if err:
        print(f"ERROR: {err}")
        print("RESULT: FAILED\n")
        return False

    errors = []
    warnings = []

    # --------------------------------------------------------
    # ENHANCEMENT 1 — TELEMETRY INTEGRATION
    # Load telemetry_spec.yaml and validate privilege_escalation_event
    # --------------------------------------------------------
    print("[ Enhancement 1 ] Telemetry Integration")
    print(f"  Loading: {TELEMETRY_SPEC_PATH}")

    telemetry_spec, t_err = load_yaml(TELEMETRY_SPEC_PATH)
    if t_err:
        errors.append(f"TELEMETRY INTEGRATION: {t_err}")
        print(f"  ERROR: {t_err}")
    else:
        print(f"  [OK] telemetry_spec.yaml loaded (spec_id: {telemetry_spec.get('spec_id', '?')})")

        # Derive valid error classes from telemetry spec
        telemetry_error_classes = set(
            telemetry_spec.get("fields", {})
            .get("error_class", {})
            .get("allowed_values", [])
        )
        telemetry_retryability = set(
            telemetry_spec.get("fields", {})
            .get("retryability", {})
            .get("allowed_values", [])
        )
        telemetry_impact_tiers = set(
            telemetry_spec.get("fields", {})
            .get("business_impact_tier", {})
            .get("allowed_values", [])
        )

        print(f"  [OK] telemetry error_classes: {sorted(telemetry_error_classes)}")
        print(f"  [OK] telemetry retryability:  {sorted(telemetry_retryability)}")
        print(f"  [OK] telemetry impact_tiers:  {sorted(telemetry_impact_tiers)}")

        # Validate privilege_escalation_event section
        pse = spec.get("privilege_escalation_event")
        if not pse or not isinstance(pse, dict):
            errors.append(
                "TELEMETRY: MISSING 'privilege_escalation_event' section — "
                "GOVERNANCE-TRUST-001 event not defined"
            )
        else:
            print(f"\n  Checking privilege_escalation_event (GOVERNANCE-TRUST-001)...")

            # logical_id must be GOVERNANCE-TRUST-001
            lid = pse.get("logical_id", "")
            if lid != ESCALATION_LOGICAL_ID:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.logical_id must be "
                    f"'{ESCALATION_LOGICAL_ID}', got '{lid}'"
                )
            else:
                print(f"  [OK] logical_id: {lid}")

            # telemetry_spec_reference must be present
            tsr = pse.get("telemetry_spec_reference", "")
            if not tsr:
                errors.append(
                    "TELEMETRY: privilege_escalation_event missing 'telemetry_spec_reference'"
                )
            else:
                print(f"  [OK] telemetry_spec_reference: {tsr}")

            # All required telemetry fields must be present
            for tf in TELEMETRY_REQUIRED_FIELDS:
                if tf not in pse:
                    errors.append(
                        f"TELEMETRY: privilege_escalation_event MISSING required "
                        f"telemetry field '{tf}'"
                    )
                else:
                    print(f"  [OK] telemetry field '{tf}' present")

            # error_class must be GOVERNANCE (from telemetry spec)
            ec = pse.get("error_class", "")
            if telemetry_error_classes and ec not in telemetry_error_classes:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.error_class '{ec}' "
                    f"not in telemetry spec allowed_values {telemetry_error_classes}"
                )
            elif ec != ESCALATION_EXPECTED_ERROR_CLASS:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.error_class must be "
                    f"'{ESCALATION_EXPECTED_ERROR_CLASS}' for privilege escalation, got '{ec}'"
                )
            else:
                print(f"  [OK] error_class: {ec}")

            # error_code must match telemetry pattern and be GOVERNANCE class
            code = pse.get("error_code", "")
            if not ERROR_CODE_PATTERN.match(str(code)):
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.error_code '{code}' "
                    f"does not match telemetry pattern GOVERNANCE-[0-9]{{3}}"
                )
            elif code != ESCALATION_EXPECTED_ERROR_CODE:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.error_code must be "
                    f"'{ESCALATION_EXPECTED_ERROR_CODE}', got '{code}'"
                )
            else:
                print(f"  [OK] error_code: {code}")

            # retryability must be 'no' (escalation must not be auto-retried)
            rt = pse.get("retryability", "")
            if telemetry_retryability and str(rt) not in telemetry_retryability:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.retryability '{rt}' "
                    f"not in telemetry spec allowed_values {telemetry_retryability}"
                )
            elif str(rt) != ESCALATION_EXPECTED_RETRYABILITY:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.retryability must be "
                    f"'{ESCALATION_EXPECTED_RETRYABILITY}' (escalation is never auto-retried), "
                    f"got '{rt}'"
                )
            else:
                print(f"  [OK] retryability: {rt}")

            # business_impact_tier must be P1
            bit = pse.get("business_impact_tier", "")
            if telemetry_impact_tiers and str(bit) not in telemetry_impact_tiers:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.business_impact_tier '{bit}' "
                    f"not in telemetry spec allowed_values {telemetry_impact_tiers}"
                )
            elif str(bit) != ESCALATION_EXPECTED_IMPACT_TIER:
                errors.append(
                    f"TELEMETRY: privilege_escalation_event.business_impact_tier must be "
                    f"'{ESCALATION_EXPECTED_IMPACT_TIER}' (escalation is always P1), got '{bit}'"
                )
            else:
                print(f"  [OK] business_impact_tier: {bit}")

    # --------------------------------------------------------
    # ENHANCEMENT 2 — IDENTITY MAPPING
    # Validate identity_model section and component_scope on every operator tier
    # --------------------------------------------------------
    print(f"\n[ Enhancement 2 ] Identity Mapping")

    identity_model = spec.get("identity_model")
    if not identity_model or not isinstance(identity_model, dict):
        errors.append("IDENTITY: MISSING 'identity_model' section")
    else:
        pid_key = identity_model.get("principal_id_key", "")
        if pid_key != "principal_id":
            errors.append(
                f"IDENTITY: identity_model.principal_id_key must be 'principal_id', got '{pid_key}'"
            )
        else:
            print(f"  [OK] principal_id_key: {pid_key}")

        for field in ["description", "format", "examples", "privilege_escalation_policy",
                       "component_scope_key", "component_scope_description"]:
            if field not in identity_model:
                errors.append(f"IDENTITY: identity_model missing field '{field}'")
            else:
                print(f"  [OK] identity_model.{field} present")

        examples = identity_model.get("examples", [])
        if not isinstance(examples, list) or len(examples) < 2:
            errors.append("IDENTITY: identity_model.examples must have at least 2 entries")
        else:
            # At least one service account example (to prove identity-agnostic)
            if not any("service:" in str(e) for e in examples):
                errors.append(
                    "IDENTITY: identity_model.examples must include at least one "
                    "service account example (e.g. 'service:agent-name') to confirm "
                    "identity-agnostic design"
                )
            else:
                print(f"  [OK] identity_model.examples includes service account — identity-agnostic confirmed")

    # --------------------------------------------------------
    # ENHANCEMENT 3 — TRACEABILITY LAW
    # --------------------------------------------------------
    print(f"\n[ Enhancement 3 ] Traceability Law")

    law_for = spec.get("law_for")
    if not law_for or not isinstance(law_for, list) or len(law_for) == 0:
        errors.append("TRACEABILITY: MISSING 'law_for' field — agent manifests not specified")
    else:
        found_agents = set(law_for)
        missing_agents = REQUIRED_LAW_FOR_AGENTS - found_agents
        if missing_agents:
            errors.append(
                f"TRACEABILITY: law_for is missing required agent(s): {missing_agents}"
            )
        else:
            print(f"  [OK] law_for agents: {sorted(found_agents)}")
            for agent in sorted(found_agents):
                print(f"  [OK] {agent} must reference this config before acting")

    # --------------------------------------------------------
    # Top-level metadata
    # --------------------------------------------------------
    print(f"\nChecking top-level metadata...")
    for meta in ["schema_version", "spec_id", "name", "description", "owner",
                  "created", "last_updated", "manifest_reference"]:
        if meta not in spec:
            errors.append(f"MISSING top-level field: '{meta}'")
        else:
            print(f"  [OK] {meta}")

    # --------------------------------------------------------
    # PART A — Operator Tiers (includes component_scope check)
    # --------------------------------------------------------
    print("\nChecking operator_tiers (Tiers 1-4)...")
    operator_tiers = spec.get("operator_tiers")
    if not operator_tiers or not isinstance(operator_tiers, list):
        errors.append("MISSING or empty 'operator_tiers' section")
    else:
        found_tiers = [t.get("tier") for t in operator_tiers]
        for required_tier in REQUIRED_OPERATOR_TIERS:
            if required_tier not in found_tiers:
                errors.append(f"MISSING operator tier {required_tier}")

        for entry in operator_tiers:
            tier_num = entry.get("tier", "?")
            label = f"operator_tier {tier_num}"
            tier_errors_before = len(errors)

            for field in REQUIRED_OPERATOR_FIELDS:
                if field not in entry:
                    errors.append(f"{label}: MISSING field '{field}'")

            for list_field in ["permissions", "restricted_from", "how_to_earn"]:
                val = entry.get(list_field, [])
                if not isinstance(val, list) or len(val) == 0:
                    errors.append(f"{label}: '{list_field}' must be a non-empty list")

            # component_scope must be a non-empty list
            cs = entry.get("component_scope", [])
            if not isinstance(cs, list) or len(cs) == 0:
                errors.append(f"{label}: 'component_scope' must be a non-empty list")
            else:
                # Each entry must be in format "<component>:<action>"
                for scope_entry in cs:
                    if ":" not in str(scope_entry):
                        errors.append(
                            f"{label}: component_scope entry '{scope_entry}' must be "
                            f"in format '<component_id>:<action>'"
                        )

            # Phase 1 constraints
            if tier_num == 3:
                max_for = [s.lower() for s in entry.get("phase_1_maximum_for", [])]
                if not any(kw in " ".join(max_for) for kw in PHASE_1_TIER_3_KEYWORDS):
                    errors.append(
                        f"{label}: phase_1_maximum_for must reference 'journey owners'"
                    )
            if tier_num == 4:
                max_for = [s.lower() for s in entry.get("phase_1_maximum_for", [])]
                if not any(kw in " ".join(max_for) for kw in PHASE_1_TIER_4_KEYWORDS):
                    errors.append(
                        f"{label}: phase_1_maximum_for must reference 'analytics lead'"
                    )

            if len(errors) == tier_errors_before:
                print(f"  [OK] Tier {tier_num} — {entry.get('name', 'UNNAMED')} "
                      f"(scope: {len(cs)} rule(s))")

    # --------------------------------------------------------
    # PART B — Finding Trust Tiers
    # --------------------------------------------------------
    print("\nChecking finding_trust_tiers...")
    finding_tiers = spec.get("finding_trust_tiers")
    if not finding_tiers or not isinstance(finding_tiers, list):
        errors.append("MISSING or empty 'finding_trust_tiers' section")
    else:
        found_finding_tiers = [t.get("tier") for t in finding_tiers]
        for req in REQUIRED_FINDING_TIERS:
            if req not in found_finding_tiers:
                errors.append(f"MISSING finding tier: '{req}'")

        for entry in finding_tiers:
            tier_name = entry.get("tier", "?")
            label = f"finding_tier {tier_name}"
            for field in REQUIRED_FINDING_FIELDS:
                if field not in entry:
                    errors.append(f"{label}: MISSING field '{field}'")
            rml = entry.get("response_mode_link", "")
            if rml not in REQUIRED_RESPONSE_MODES:
                errors.append(f"{label}: response_mode_link '{rml}' not in {REQUIRED_RESPONSE_MODES}")
            pc = entry.get("promotion_conditions", {})
            if isinstance(pc, dict):
                if "approval_from" not in pc:
                    errors.append(f"{label}: promotion_conditions missing 'approval_from'")
            else:
                errors.append(f"{label}: promotion_conditions must be a dict")
            print(f"  [OK] {tier_name} — response_mode: {rml}")

    # --------------------------------------------------------
    # Response Mode Definitions
    # --------------------------------------------------------
    print("\nChecking response_mode_definitions...")
    rmd = spec.get("response_mode_definitions")
    if not rmd or not isinstance(rmd, dict):
        errors.append("MISSING or empty 'response_mode_definitions' section")
    else:
        missing_modes = REQUIRED_RESPONSE_MODES - set(rmd.keys())
        if missing_modes:
            errors.append(f"response_mode_definitions missing modes: {missing_modes}")
        else:
            for mode_name, mode_def in rmd.items():
                for field in REQUIRED_RESPONSE_FIELDS:
                    if field not in mode_def:
                        errors.append(f"response_mode '{mode_name}' MISSING field '{field}'")
                for t in mode_def.get("permitted_finding_tiers", []):
                    if t not in VALID_FINDING_TIERS:
                        errors.append(
                            f"response_mode '{mode_name}': unknown finding tier '{t}'"
                        )
                print(f"  [OK] {mode_name}")

    # --------------------------------------------------------
    # Demotion Rules
    # --------------------------------------------------------
    print("\nChecking demotion_rules...")
    demotion_rules = spec.get("demotion_rules")
    if not demotion_rules or not isinstance(demotion_rules, list):
        errors.append("MISSING or empty 'demotion_rules' section")
    elif len(demotion_rules) < 3:
        warnings.append(f"Only {len(demotion_rules)} demotion rule(s) — expected ≥3")
    else:
        for rule in demotion_rules:
            rule_id = rule.get("id", "?")
            for field in REQUIRED_DEMOTION_FIELDS:
                if field not in rule:
                    errors.append(f"demotion_rule '{rule_id}': MISSING field '{field}'")
            for t in rule.get("from_tiers", []):
                if t not in VALID_FINDING_TIERS:
                    errors.append(f"demotion_rule '{rule_id}': unknown from_tier '{t}'")
            dt = rule.get("demoted_to", "")
            if dt not in VALID_FINDING_TIERS:
                errors.append(f"demotion_rule '{rule_id}': demoted_to '{dt}' not a valid tier")
            print(f"  [OK] {rule_id} — {rule.get('trigger', '')[:58]}")

    # --------------------------------------------------------
    # Interaction Matrix
    # --------------------------------------------------------
    print("\nChecking interaction_matrix...")
    matrix = spec.get("interaction_matrix", {})
    rules_list = matrix.get("rules", [])
    if not rules_list:
        errors.append("MISSING or empty 'interaction_matrix.rules'")
    else:
        found_matrix_tiers = [r.get("operator_tier") for r in rules_list]
        for req in REQUIRED_MATRIX_OPERATOR_TIERS:
            if req not in found_matrix_tiers:
                errors.append(f"interaction_matrix missing operator_tier {req}")
        for row in rules_list:
            ot = row.get("operator_tier", "?")
            for field in REQUIRED_MATRIX_FIELDS:
                if field not in row:
                    errors.append(f"interaction_matrix operator_tier {ot}: MISSING '{field}'")
            print(f"  [OK] Operator Tier {ot} matrix row defined")

    # --------------------------------------------------------
    # Usage Contract
    # --------------------------------------------------------
    print("\nChecking usage_contract...")
    uc = spec.get("usage_contract")
    if not uc or not isinstance(uc, dict):
        errors.append("MISSING or empty 'usage_contract' section")
    else:
        if uc.get("mandatory") is not True:
            errors.append("usage_contract.mandatory must be true")
        else:
            print("  [OK] usage_contract.mandatory = true")

        applies = uc.get("applies_to", "")
        if "ALL" not in str(applies).upper():
            errors.append(f"usage_contract.applies_to must reference ALL. Got: '{applies}'")
        else:
            print(f"  [OK] usage_contract.applies_to confirmed")

        rules = uc.get("rules", [])
        if not rules or not isinstance(rules, list):
            errors.append("usage_contract.rules must be a non-empty list")
        else:
            for r in rules:
                if "id" not in r or "rule" not in r:
                    errors.append("usage_contract rule entry missing 'id' or 'rule'")
            print(f"  [OK] usage_contract.rules: {len(rules)} rule(s)")

        enforcement = uc.get("enforcement", {})
        if not enforcement:
            warnings.append("usage_contract missing 'enforcement' block")
        else:
            print("  [OK] usage_contract.enforcement defined")

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------
    op_count  = len(spec.get("operator_tiers", []))
    ft_count  = len(spec.get("finding_trust_tiers", []))
    dm_count  = len(spec.get("demotion_rules", []))
    rm_count  = len(spec.get("response_mode_definitions", {}))
    uc_rules  = len(spec.get("usage_contract", {}).get("rules", []))
    lf_count  = len(spec.get("law_for", []))

    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Operator tiers:            {op_count}")
    print(f"Finding trust tiers:       {ft_count}")
    print(f"Response modes:            {rm_count}")
    print(f"Demotion rules:            {dm_count}")
    print(f"Usage contract rules:      {uc_rules}")
    print(f"law_for agents:            {lf_count}")
    print(f"Telemetry spec validated:  {'yes' if not any('TELEMETRY' in e for e in errors) else 'FAILED'}")
    print(f"Identity model validated:  {'yes' if not any('IDENTITY' in e for e in errors) else 'FAILED'}")
    print(f"Traceability law present:  {'yes' if not any('TRACEABILITY' in e for e in errors) else 'FAILED'}")
    print(f"Errors:                    {len(errors)}")
    print(f"Warnings:                  {len(warnings)}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ERROR: {e}")
        print(f"\n{'='*60}")
        print("RESULT: FAILED")
        print(f"{'='*60}\n")
        return False
    else:
        print(f"\n{'='*60}")
        print("RESULT: PASSED — graduated_trust_tiers.yaml meets all KAN-1G acceptance criteria.")
        print("Pre-flight enhancements: telemetry integration, identity mapping, traceability law — all clear.")
        print("Governance is a ramp, not a wall.")
        print(f"{'='*60}\n")
        return True


if __name__ == "__main__":
    spec_path = sys.argv[1] if len(sys.argv) > 1 else SPEC_PATH
    success = validate_spec(spec_path)
    sys.exit(0 if success else 1)
