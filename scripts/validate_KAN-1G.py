"""
validate_KAN-1G.py
Validates manifests/graduated_trust_tiers.yaml against KAN-1G acceptance criteria.

Checks:
  - Operator tiers 1-4 present with required fields
  - Phase 1 maximum constraints enforced in spec
  - Each tier has: permissions, restricted_from, how_to_earn, approval_required_from
  - Finding trust tiers: UNVERIFIED / PROVISIONAL / VALIDATED / TRUSTED
  - Each finding tier has: response_mode_link, promotion_conditions, approval_from
  - response_mode_definitions cover: EVIDENCED / DIRECTIONAL / UNKNOWN / GUARDED / CONTRADICTED
  - Demotion rules present and each has required fields
  - Interaction matrix covers all 4 operator tiers
  - usage_contract present, mandatory=true, applies to ALL

Run: python scripts/validate_KAN-1G.py
"""

import yaml
import sys
from pathlib import Path

SPEC_PATH = "manifests/graduated_trust_tiers.yaml"

REQUIRED_OPERATOR_TIERS = [1, 2, 3, 4]
REQUIRED_OPERATOR_FIELDS = [
    "tier", "name", "label", "description", "permissions",
    "restricted_from", "how_to_earn", "phase_1_maximum_for", "approval_required_from"
]

REQUIRED_FINDING_TIERS = ["UNVERIFIED", "PROVISIONAL", "VALIDATED", "TRUSTED"]
REQUIRED_FINDING_FIELDS = [
    "tier", "ordinal", "description", "response_mode_link", "display_label",
    "permitted_actions", "blocked_actions", "promotion_conditions"
]

REQUIRED_RESPONSE_MODES = {"EVIDENCED", "DIRECTIONAL", "UNKNOWN", "GUARDED", "CONTRADICTED"}
REQUIRED_RESPONSE_FIELDS = ["description", "permitted_finding_tiers", "display_colour"]

REQUIRED_DEMOTION_FIELDS = [
    "id", "trigger", "from_tiers", "demoted_to", "automatic",
    "override_permitted", "action_on_demotion"
]

REQUIRED_MATRIX_OPERATOR_TIERS = [1, 2, 3, 4]
REQUIRED_MATRIX_FIELDS = ["operator_tier", "can_view", "can_approve", "can_promote", "can_demote"]

VALID_FINDING_TIERS = set(REQUIRED_FINDING_TIERS)
PHASE_1_TIER_3_KEYWORDS = ["journey owner", "journey owners"]
PHASE_1_TIER_4_KEYWORDS = ["analytics lead"]


def validate_spec(spec_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"CJI Pulse — validate_KAN-1G.py")
    print(f"Validating: {spec_path}")
    print(f"{'='*60}\n")

    path = Path(spec_path)
    if not path.exists():
        print(f"ERROR: Spec not found at '{spec_path}'")
        print("RESULT: FAILED\n")
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error: {e}")
        print("RESULT: FAILED\n")
        return False

    errors = []
    warnings = []

    # --- Top-level metadata ---
    print("Checking top-level metadata...")
    for meta in ["schema_version", "spec_id", "name", "description", "owner",
                  "created", "last_updated", "manifest_reference"]:
        if meta not in spec:
            errors.append(f"MISSING top-level field: '{meta}'")
        else:
            print(f"  [OK] {meta}")

    # --------------------------------------------------------
    # PART A — Operator Tiers
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

            for field in REQUIRED_OPERATOR_FIELDS:
                if field not in entry:
                    errors.append(f"{label}: MISSING field '{field}'")

            # permissions must be non-empty list
            perms = entry.get("permissions", [])
            if not isinstance(perms, list) or len(perms) == 0:
                errors.append(f"{label}: 'permissions' must be a non-empty list")

            # restricted_from must be non-empty list
            restricted = entry.get("restricted_from", [])
            if not isinstance(restricted, list) or len(restricted) == 0:
                errors.append(f"{label}: 'restricted_from' must be a non-empty list")

            # how_to_earn must be non-empty list
            how = entry.get("how_to_earn", [])
            if not isinstance(how, list) or len(how) == 0:
                errors.append(f"{label}: 'how_to_earn' must be a non-empty list")

            # Phase 1 constraints
            if tier_num == 3:
                max_for = [s.lower() for s in entry.get("phase_1_maximum_for", [])]
                if not any(kw in " ".join(max_for) for kw in PHASE_1_TIER_3_KEYWORDS):
                    errors.append(
                        f"{label}: phase_1_maximum_for must reference 'journey owners' "
                        f"(programme constraint)"
                    )
            if tier_num == 4:
                max_for = [s.lower() for s in entry.get("phase_1_maximum_for", [])]
                if not any(kw in " ".join(max_for) for kw in PHASE_1_TIER_4_KEYWORDS):
                    errors.append(
                        f"{label}: phase_1_maximum_for must reference 'analytics lead' "
                        f"(programme constraint)"
                    )

            if not errors or all(label not in e for e in errors):
                print(f"  [OK] Tier {tier_num} — {entry.get('name', 'UNNAMED')}")

    # --------------------------------------------------------
    # PART B — Finding Trust Tiers
    # --------------------------------------------------------
    print("\nChecking finding_trust_tiers (UNVERIFIED/PROVISIONAL/VALIDATED/TRUSTED)...")
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

            # response_mode_link must be a valid response mode
            rml = entry.get("response_mode_link", "")
            if rml not in REQUIRED_RESPONSE_MODES:
                errors.append(
                    f"{label}: response_mode_link '{rml}' not in {REQUIRED_RESPONSE_MODES}"
                )

            # promotion_conditions must have approval_from
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
        found_modes = set(rmd.keys())
        missing_modes = REQUIRED_RESPONSE_MODES - found_modes
        if missing_modes:
            errors.append(f"response_mode_definitions missing modes: {missing_modes}")
        else:
            for mode_name, mode_def in rmd.items():
                for field in REQUIRED_RESPONSE_FIELDS:
                    if field not in mode_def:
                        errors.append(
                            f"response_mode '{mode_name}' MISSING field '{field}'"
                        )
                # permitted_finding_tiers must reference valid tiers
                pft = mode_def.get("permitted_finding_tiers", [])
                for t in pft:
                    if t not in VALID_FINDING_TIERS:
                        errors.append(
                            f"response_mode '{mode_name}': permitted_finding_tiers "
                            f"contains unknown tier '{t}'"
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
        warnings.append(f"Only {len(demotion_rules)} demotion rule(s) defined — expected at least 3")
    else:
        for rule in demotion_rules:
            rule_id = rule.get("id", "?")
            for field in REQUIRED_DEMOTION_FIELDS:
                if field not in rule:
                    errors.append(f"demotion_rule '{rule_id}': MISSING field '{field}'")
            # from_tiers must reference valid finding tiers
            for t in rule.get("from_tiers", []):
                if t not in VALID_FINDING_TIERS:
                    errors.append(
                        f"demotion_rule '{rule_id}': from_tiers contains unknown tier '{t}'"
                    )
            # demoted_to must be a valid finding tier
            dt = rule.get("demoted_to", "")
            if dt not in VALID_FINDING_TIERS:
                errors.append(
                    f"demotion_rule '{rule_id}': demoted_to '{dt}' is not a valid finding tier"
                )
            print(f"  [OK] {rule_id} — {rule.get('trigger', '')[:60]}")

    # --------------------------------------------------------
    # Interaction Matrix
    # --------------------------------------------------------
    print("\nChecking interaction_matrix...")
    matrix = spec.get("interaction_matrix", {})
    rules_list = matrix.get("rules", [])
    if not rules_list:
        errors.append("MISSING or empty 'interaction_matrix.rules' section")
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
            errors.append(
                f"usage_contract.applies_to must reference ALL outputs. Got: '{applies}'"
            )
        else:
            print(f"  [OK] usage_contract.applies_to: '{applies}'")

        rules = uc.get("rules", [])
        if not rules or not isinstance(rules, list) or len(rules) == 0:
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
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")

    op_count = len(spec.get("operator_tiers", []))
    ft_count = len(spec.get("finding_trust_tiers", []))
    dm_count = len(spec.get("demotion_rules", []))
    rm_count = len(spec.get("response_mode_definitions", {}))
    uc_rules = len(spec.get("usage_contract", {}).get("rules", []))

    print(f"Operator tiers:        {op_count}")
    print(f"Finding trust tiers:   {ft_count}")
    print(f"Response modes:        {rm_count}")
    print(f"Demotion rules:        {dm_count}")
    print(f"Usage contract rules:  {uc_rules}")
    print(f"Errors:                {len(errors)}")
    print(f"Warnings:              {len(warnings)}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ERROR: {e}")
        print(f"\n{'='*60}")
        print("RESULT: FAILED — graduated_trust_tiers.yaml does not meet KAN-1G acceptance criteria.")
        print(f"{'='*60}\n")
        return False
    else:
        print(f"\n{'='*60}")
        print("RESULT: PASSED — graduated_trust_tiers.yaml meets all KAN-1G acceptance criteria.")
        print("Governance is a ramp, not a wall.")
        print(f"{'='*60}\n")
        return True


if __name__ == "__main__":
    spec_path = sys.argv[1] if len(sys.argv) > 1 else SPEC_PATH
    success = validate_spec(spec_path)
    sys.exit(0 if success else 1)
