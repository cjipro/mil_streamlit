"""
validate_KAN-011.py — KAN-011 Living Data Dictionary v2.0 validator

Checks governance_principles.yaml v2.0 and data_dictionary_master.yaml.
Exit code is ALWAYS 0 — builds never fail on principle checks.
"""
import sys
import yaml
import os
from pathlib import Path
from datetime import datetime, timezone

PRINCIPLES_PATH = "manifests/governance_principles.yaml"
MASTER_DICT_PATH = "manifests/data_dictionary_master.yaml"
STRATEGY_PATH = "manifests/data_strategy_v2.md"
LOG_PATH = "logs/principle_warnings.log"

EXPECTED_PRINCIPLE_IDS = {f"P{i}" for i in range(1, 22)}
EXPECTED_TABLES = {
    "Mobile_App_Events_Raw", "Mobile_App_Events_Ref", "Operation_Codes_Ref",
    "Mobile_App_Events_Session", "Mobile_App_Events_Session_Bucketed",
    "Customer_Profile_Dim", "Call_Centre_Events_Raw", "Branch_Visit_Events_Raw",
    "Customer_Satisfaction_Raw", "Web_App_Events_Raw",
}
EXPECTED_REG_IDS = {"REG-001", "REG-002", "REG-003", "REG-004"}
EXPECTED_SUBSTITUTIONS = 3

CHECKS = []
WARNINGS = []


def check(label, result, detail=""):
    CHECKS.append((label, result, detail))
    status = "PASS" if result else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    return result


def warn(code, message):
    WARNINGS.append({"code": code, "message": message})
    print(f"  [{code}] {message}")


def write_log():
    Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n--- validate_KAN-011.py v2.0 run: {datetime.now(timezone.utc).isoformat()} ---\n")
        if not WARNINGS:
            f.write("  No WARN_P codes raised.\n")
        else:
            for w in WARNINGS:
                f.write(f"  [{w['code']}] {w['message']}\n")


def main():
    print()
    print("validate_KAN-011.py v2.0 -- Living Data Dictionary validator")
    print("=" * 62)
    print()

    # ----------------------------------------------------------------
    # CHECK 1: data_strategy_v2.md exists and is non-empty
    # ----------------------------------------------------------------
    strat = Path(STRATEGY_PATH)
    strat_ok = strat.exists() and strat.stat().st_size > 0
    check("data_strategy_v2.md exists and is non-empty", strat_ok, STRATEGY_PATH)

    # ----------------------------------------------------------------
    # CHECK 2: governance_principles.yaml exists and is valid YAML
    # ----------------------------------------------------------------
    gp_path = Path(PRINCIPLES_PATH)
    if not check("governance_principles.yaml exists", gp_path.exists(), PRINCIPLES_PATH):
        print()
        print("  RESULT: PASS_WITH_WARNINGS -- governance_principles.yaml missing")
        write_log()
        sys.exit(0)

    try:
        gp = yaml.safe_load(gp_path.read_text(encoding="utf-8"))
        check("governance_principles.yaml is valid YAML", True)
    except yaml.YAMLError as e:
        check("governance_principles.yaml is valid YAML", False, str(e))
        write_log()
        sys.exit(0)

    # ----------------------------------------------------------------
    # CHECK 3: All 21 principles present (P1-P21)
    # ----------------------------------------------------------------
    principles = gp.get("principles", [])
    found_ids = {p.get("id") for p in principles if isinstance(p, dict)}
    missing = sorted(EXPECTED_PRINCIPLE_IDS - found_ids)
    check(
        "All 21 principles present (P1-P21)",
        not missing,
        f"missing: {missing}" if missing else f"{len(found_ids)} found",
    )

    # ----------------------------------------------------------------
    # CHECK 4: All 21 agent_names present and non-empty
    # ----------------------------------------------------------------
    missing_agents = [
        p.get("id") for p in principles
        if isinstance(p, dict) and not p.get("agent_name")
    ]
    check(
        "All 21 agent_names present and non-empty",
        not missing_agents,
        f"missing agent_name: {missing_agents}" if missing_agents else "all present",
    )

    # ----------------------------------------------------------------
    # CHECK 5: violation_policy is WARN_NOT_FAIL
    # ----------------------------------------------------------------
    policy = gp.get("violation_policy", "")
    check(
        "violation_policy is WARN_NOT_FAIL",
        "WARN_NOT_FAIL" in str(policy),
        f"got: {policy!r}",
    )

    # ----------------------------------------------------------------
    # CHECK 6: All 10 tables in table_registry
    # ----------------------------------------------------------------
    table_reg = gp.get("table_registry", {}).get("tables", [])
    found_tables = {t.get("human_name") for t in table_reg if isinstance(t, dict)}
    missing_tables = sorted(EXPECTED_TABLES - found_tables)
    check(
        "All 10 tables in table_registry",
        not missing_tables,
        f"missing: {missing_tables}" if missing_tables else f"{len(found_tables)} found",
    )

    # ----------------------------------------------------------------
    # CHECK 7: All source_hashes are HASH_PENDING_ORIGINAL
    # ----------------------------------------------------------------
    bad_hashes = [
        t.get("human_name") for t in table_reg
        if isinstance(t, dict) and t.get("source_hash") != "HASH_PENDING_ORIGINAL"
    ]
    check(
        "All source_hashes are HASH_PENDING_ORIGINAL (never a real name)",
        not bad_hashes,
        f"bad: {bad_hashes}" if bad_hashes else "confirmed",
    )
    if bad_hashes:
        warn("WARN_P4", f"Non-standard source_hash detected in table_registry: {bad_hashes}")

    # ----------------------------------------------------------------
    # CHECK 8: substitution_registry has 3 entries
    # ----------------------------------------------------------------
    sub_reg = gp.get("substitution_registry", {}).get("entries", [])
    check(
        f"substitution_registry has {EXPECTED_SUBSTITUTIONS} entries",
        len(sub_reg) == EXPECTED_SUBSTITUTIONS,
        f"found: {len(sub_reg)}",
    )

    # ----------------------------------------------------------------
    # CHECK 9: data_dictionary_master.yaml exists and is valid YAML
    # ----------------------------------------------------------------
    md_path = Path(MASTER_DICT_PATH)
    if not check("data_dictionary_master.yaml exists", md_path.exists(), MASTER_DICT_PATH):
        warn("WARN_P3", "data_dictionary_master.yaml not yet created")
    else:
        try:
            md = yaml.safe_load(md_path.read_text(encoding="utf-8"))
            check("data_dictionary_master.yaml is valid YAML", True)

            # ----------------------------------------------------------------
            # CHECK 10: All 10 tables in master dictionary
            # ----------------------------------------------------------------
            master_tables = md.get("tables", [])
            found_master = {t.get("human_name") for t in master_tables if isinstance(t, dict)}
            missing_master = sorted(EXPECTED_TABLES - found_master)
            check(
                "All 10 tables in master dictionary",
                not missing_master,
                f"missing: {missing_master}" if missing_master else f"{len(found_master)} found",
            )

            # ----------------------------------------------------------------
            # CHECK 11: No table entry contains a real original name
            # ----------------------------------------------------------------
            # All source_hash fields should be HASH_PENDING_ORIGINAL
            bad_master_hashes = [
                t.get("human_name") for t in master_tables
                if isinstance(t, dict) and t.get("source_hash") != "HASH_PENDING_ORIGINAL"
            ]
            check(
                "No original names in master dictionary (all hashes HASH_PENDING_ORIGINAL)",
                not bad_master_hashes,
                f"bad: {bad_master_hashes}" if bad_master_hashes else "confirmed",
            )
            if not bad_master_hashes:
                warn("WARN_P4", "Check: no original names detected in master dictionary -- PASS")

        except yaml.YAMLError as e:
            check("data_dictionary_master.yaml is valid YAML", False, str(e))

    # ----------------------------------------------------------------
    # CHECK 12: REG-001 through REG-004 in regulatory_open_items
    # ----------------------------------------------------------------
    reg_items = gp.get("regulatory_open_items", [])
    found_reg = {r.get("id") for r in reg_items if isinstance(r, dict)}
    missing_reg = sorted(EXPECTED_REG_IDS - found_reg)
    check(
        "REG-001 through REG-004 present in regulatory_open_items",
        not missing_reg,
        f"missing: {missing_reg}" if missing_reg else "all 4 present",
    )

    # ----------------------------------------------------------------
    # CHECK 13: three_layer_governance present with all 3 layers
    # ----------------------------------------------------------------
    tlg = gp.get("three_layer_governance", {})
    layers = ["layer_1_marker_library", "layer_2_applicability_profiles", "layer_3_table_exceptions_register"]
    missing_layers = [l for l in layers if l not in (tlg or {})]
    check(
        "Three-layer governance present with all 3 layers",
        not missing_layers,
        f"missing: {missing_layers}" if missing_layers else "all 3 layers present",
    )

    # ----------------------------------------------------------------
    # CHECK 14: reassessment_triggers present with event_driven and scheduled
    # ----------------------------------------------------------------
    rt = gp.get("reassessment_triggers", {})
    rt_ok = (
        isinstance(rt, dict) and
        "event_driven" in rt and
        "scheduled" in rt
    )
    check(
        "Reassessment triggers present (event_driven + scheduled)",
        rt_ok,
        "both keys present" if rt_ok else f"found keys: {list((rt or {}).keys())}",
    )

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    write_log()
    print()
    passes = sum(1 for _, r, _ in CHECKS if r)
    fails = len(CHECKS) - passes
    print(f"  Checks: {passes} passed, {fails} failed")
    print(f"  WARN_P codes raised: {len(WARNINGS)}")
    print()
    print("  " + "-" * 58)

    if fails == 0 and not any(w["code"].startswith("WARN_P") and "PASS" not in w["message"] for w in WARNINGS):
        print("  RESULT: PASS -- all KAN-011 v2.0 checks passed")
    else:
        print(f"  RESULT: PASS_WITH_WARNINGS -- {fails} check(s) failed or warnings raised")
        print(f"  See {LOG_PATH}")

    print()
    # Always exit 0 — builds never fail on principle checks
    sys.exit(0)


if __name__ == "__main__":
    main()
