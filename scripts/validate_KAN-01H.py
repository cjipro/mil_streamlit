"""
validate_PULSE-1H.py
Validates manifests/hypothesis_library.yaml against PULSE-1H acceptance criteria.

Checks:
  - Minimum 10 entries present (task: 22 total)
  - All 15 Phase 1 Refresh Pack IDs present (H_PERF_001-005, H_PERF_012-014,
    H_BEH_001-005, H_XCH_001, H_XCH_003, H_VoI_001)
  - All 7 research-derived IDs present (H_RES_001-007)
  - Each entry has all required fields
  - source_tier enum valid
  - status enum valid
  - evidence_tier enum valid
  - response_mode valid
  - Refresh Pack hypotheses are APPROVED
  - H_RES hypotheses are PENDING and have adversarial_challenger_required: true
  - half_life_days correct per domain
  - recommended_action has three required parts
  - No duplicate IDs

Run: python scripts/validate_PULSE-1H.py
"""

import yaml
import sys
from pathlib import Path

SPEC_PATH = "manifests/hypothesis_library.yaml"

# Required IDs
REFRESH_PACK_IDS = [
    "H_PERF_001", "H_PERF_002", "H_PERF_003", "H_PERF_004", "H_PERF_005",
    "H_PERF_012", "H_PERF_013", "H_PERF_014",
    "H_BEH_001", "H_BEH_002", "H_BEH_003", "H_BEH_004", "H_BEH_005",
    "H_XCH_001", "H_XCH_003",
    "H_VoI_001",
]
RESEARCH_IDS = [f"H_RES_{i:03d}" for i in range(1, 8)]  # H_RES_001 through H_RES_007

REQUIRED_ENTRY_FIELDS = [
    "id", "name", "domain", "source_tier", "status",
    "journey_type", "hypothesis_text", "description",
    "evidence_tier", "response_mode", "supporting_metrics",
    "evidence_requirements", "minimum_effect_size",
    "half_life_days", "adversarial_challenger_required",
    "recommended_action", "date_added",
]

REQUIRED_RECOMMENDED_ACTION_PARTS = [
    "what_is_happening", "why_it_matters", "suggested_first_action"
]

VALID_SOURCE_TIERS = {
    "TELEMETRY_DERIVED", "RESEARCH_DERIVED", "COMPLAINT_DERIVED",
    "MIXED_EVIDENCE", "HISTORICAL_RETROSPECTIVE"
}
VALID_STATUSES = {"APPROVED", "PENDING", "CANDIDATE", "RETIRED"}
VALID_EVIDENCE_TIERS = {"EVIDENCED", "DIRECTIONAL", "UNKNOWN"}
VALID_RESPONSE_MODES = {"EVIDENCED", "DIRECTIONAL", "UNKNOWN", "GUARDED", "CONTRADICTED"}

# Expected half-life by domain keyword
HALF_LIFE_BY_DOMAIN = {
    "performance":      60,
    "behavioural":      90,
    "cross_channel":    120,
    "voice_of_intent":  90,
}
RESEARCH_HALF_LIFE = 180

MIN_ENTRIES = 10


def validate_spec(spec_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"CJI Pulse — validate_PULSE-1H.py")
    print(f"Validating: {spec_path}")
    print(f"{'='*60}\n")

    path = Path(spec_path)
    if not path.exists():
        print(f"ERROR: Spec not found at '{spec_path}'")
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error: {e}")
        return False

    errors = []
    warnings = []

    # --- Top-level metadata ---
    print("Checking top-level metadata...")
    for meta in ["schema_version", "spec_id", "name", "description", "owner",
                  "created", "last_updated", "manifest_reference",
                  "entry_schema", "source_tier_enum", "status_enum",
                  "evidence_tier_enum", "half_life_reference"]:
        if meta not in spec:
            errors.append(f"MISSING top-level field: '{meta}'")
        else:
            print(f"  [OK] {meta}")

    hypotheses = spec.get("hypotheses")
    if not hypotheses or not isinstance(hypotheses, list):
        errors.append("MISSING or empty 'hypotheses' list")
        print("\nFATAL: no hypotheses to validate.")
        _print_summary(errors, warnings, hypotheses or [])
        return False

    total = len(hypotheses)
    print(f"\nFound {total} hypotheses (minimum required: {MIN_ENTRIES})")
    if total < MIN_ENTRIES:
        errors.append(f"Insufficient entries: {total} found, {MIN_ENTRIES} required")

    # --- ID inventory ---
    found_ids = {}
    for h in hypotheses:
        hid = h.get("id", "MISSING_ID")
        found_ids[hid] = found_ids.get(hid, 0) + 1

    # Duplicate check
    for hid, count in found_ids.items():
        if count > 1:
            errors.append(f"DUPLICATE hypothesis ID: '{hid}'")

    # Refresh Pack completeness
    print("\nChecking Phase 1 Refresh Pack IDs...")
    for rid in REFRESH_PACK_IDS:
        if rid not in found_ids:
            errors.append(f"MISSING Refresh Pack hypothesis: '{rid}'")
        else:
            print(f"  [OK] {rid}")

    # Research-derived completeness
    print("\nChecking Research-derived IDs (H_RES_001-007)...")
    for rid in RESEARCH_IDS:
        if rid not in found_ids:
            errors.append(f"MISSING Research hypothesis: '{rid}'")
        else:
            print(f"  [OK] {rid}")

    # --- Per-entry validation ---
    print("\nValidating each hypothesis entry...")
    for h in hypotheses:
        hid = h.get("id", "MISSING_ID")
        entry_errors = []

        # Required fields
        for field in REQUIRED_ENTRY_FIELDS:
            if field not in h:
                entry_errors.append(f"MISSING field '{field}'")

        # source_tier
        st = h.get("source_tier", "")
        if st not in VALID_SOURCE_TIERS:
            entry_errors.append(f"INVALID source_tier '{st}'")

        # status
        status = h.get("status", "")
        if status not in VALID_STATUSES:
            entry_errors.append(f"INVALID status '{status}'")

        # evidence_tier
        et = h.get("evidence_tier", "")
        if et not in VALID_EVIDENCE_TIERS:
            entry_errors.append(f"INVALID evidence_tier '{et}'")

        # response_mode
        rm = h.get("response_mode", "")
        if rm not in VALID_RESPONSE_MODES:
            entry_errors.append(f"INVALID response_mode '{rm}'")

        # Refresh Pack must be APPROVED
        if hid in REFRESH_PACK_IDS and status != "APPROVED":
            entry_errors.append(f"Refresh Pack hypothesis must be APPROVED, got '{status}'")

        # H_RES must be PENDING and adversarial_challenger_required: true
        if hid in RESEARCH_IDS:
            if status != "PENDING":
                entry_errors.append(f"Research hypothesis must be PENDING, got '{status}'")
            if h.get("adversarial_challenger_required") is not True:
                entry_errors.append("adversarial_challenger_required must be true for H_RES entries")

        # half_life_days
        half_life = h.get("half_life_days")
        domain = h.get("domain", "")
        if hid in RESEARCH_IDS:
            expected_hl = RESEARCH_HALF_LIFE
        else:
            expected_hl = HALF_LIFE_BY_DOMAIN.get(domain)
        if expected_hl is not None and half_life != expected_hl:
            entry_errors.append(
                f"half_life_days={half_life}, expected {expected_hl} for domain '{domain}'"
            )

        # recommended_action three-part structure
        ra = h.get("recommended_action", {})
        if not isinstance(ra, dict):
            entry_errors.append("recommended_action must be a dict")
        else:
            for part in REQUIRED_RECOMMENDED_ACTION_PARTS:
                if part not in ra:
                    entry_errors.append(f"recommended_action missing '{part}'")

        # supporting_metrics non-empty list
        sm = h.get("supporting_metrics", [])
        if not isinstance(sm, list) or len(sm) == 0:
            entry_errors.append("supporting_metrics must be a non-empty list")

        # evidence_requirements non-empty list
        er = h.get("evidence_requirements", [])
        if not isinstance(er, list) or len(er) == 0:
            entry_errors.append("evidence_requirements must be a non-empty list")

        if entry_errors:
            print(f"  [FAIL] {hid}")
            for e in entry_errors:
                print(f"    ERROR: {e}")
                errors.append(f"[{hid}] {e}")
        else:
            print(f"  [OK]   {hid} — {h.get('name', '')[:55]}")

    _print_summary(errors, warnings, hypotheses)
    return len(errors) == 0


def _print_summary(errors, warnings, hypotheses):
    refresh_count = sum(1 for h in hypotheses if h.get("id") in set(REFRESH_PACK_IDS))
    research_count = sum(1 for h in hypotheses if h.get("id") in set(RESEARCH_IDS))

    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total hypotheses:          {len(hypotheses)}")
    print(f"Phase 1 Refresh Pack:      {refresh_count} / {len(REFRESH_PACK_IDS)}")
    print(f"Research-derived (H_RES):  {research_count} / {len(RESEARCH_IDS)}")
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
        print("RESULT: FAILED — hypothesis_library.yaml does not meet PULSE-1H acceptance criteria.")
        print(f"{'='*60}\n")
    else:
        print(f"\n{'='*60}")
        print("RESULT: PASSED — hypothesis_library.yaml meets all PULSE-1H acceptance criteria.")
        print("The Ask CJI intelligence engine has a validated seed library.")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    spec_path = sys.argv[1] if len(sys.argv) > 1 else SPEC_PATH
    success = validate_spec(spec_path)
    sys.exit(0 if success else 1)
