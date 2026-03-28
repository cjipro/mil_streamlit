"""
validate_mil_import_rule.py — MIL Zero Entanglement build validator

Enforces the MIL Import Rule from MIL_SCHEMA.yaml:

  No file under mil/ may import from pulse/, poc/, app/, dags/,
  or any internal data module.

  No file outside mil/ may import from mil/ directly.

  Permitted data exchange: read mil/outputs/mil_findings.json only.

This validator is a HARD FAILURE — not a warning.
Exit code 1 if any violation is found.
Exit code 0 if clean.

Run: py scripts/validate_mil_import_rule.py
"""
import sys
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Internal modules that mil/ files must never import
INTERNAL_MODULES = [
    "pulse",
    "poc",
    "app",
    "dags",
    "twin_refinery",
    "agents",
    "conductor",
    "config",          # shared config is fine via yaml reads, not imports
    "src",
]

# The one permitted crossing — reading mil_findings.json is fine,
# but importing from mil/ is not.
PERMITTED_READ = "mil/outputs/mil_findings.json"

# Import pattern — matches: import X, from X import, from X.Y import
IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE)


def get_python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def check_mil_imports_internal(violations: list) -> None:
    """mil/ files must not import from internal modules."""
    mil_dir = ROOT / "mil"
    if not mil_dir.exists():
        return

    for py_file in get_python_files(mil_dir):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for match in IMPORT_RE.finditer(content):
            module = match.group(1).split(".")[0]
            if module in INTERNAL_MODULES:
                rel = py_file.relative_to(ROOT)
                violations.append(
                    f"VIOLATION [MIL→INTERNAL]: {rel} imports '{module}' — "
                    f"Zero Entanglement breach. mil/ may not import internal modules."
                )


def check_external_imports_mil(violations: list) -> None:
    """Files outside mil/ must not import from mil/ directly."""
    for search_dir_name in ["app", "poc", "agents", "src", "conductor", "dags", "scripts"]:
        search_dir = ROOT / search_dir_name
        if not search_dir.exists():
            continue

        for py_file in get_python_files(search_dir):
            content = py_file.read_text(encoding="utf-8", errors="ignore")

            # Check for direct mil imports (not the permitted file read)
            for match in IMPORT_RE.finditer(content):
                module = match.group(1).split(".")[0]
                if module == "mil":
                    rel = py_file.relative_to(ROOT)
                    # The adapter shim is exempt — it calls mil/command/app.py via subprocess/path
                    # but should not import mil as a Python module
                    violations.append(
                        f"VIOLATION [EXTERNAL→MIL]: {rel} imports 'mil' — "
                        f"Zero Entanglement breach. Use mil/outputs/mil_findings.json only."
                    )

            # Check for sys.path manipulation to reach mil/
            if "sys.path" in content and "mil" in content:
                rel = py_file.relative_to(ROOT)
                # Heuristic only — flag for human review
                violations.append(
                    f"WARNING [REVIEW REQUIRED]: {rel} contains sys.path manipulation "
                    f"near 'mil' reference — verify Zero Entanglement is preserved."
                )


def check_mil_schema_exists(violations: list) -> None:
    """MIL_SCHEMA.yaml must exist."""
    schema = ROOT / "mil" / "MIL_SCHEMA.yaml"
    if not schema.exists():
        violations.append("VIOLATION: mil/MIL_SCHEMA.yaml does not exist.")


def check_chronicle_exists(violations: list) -> None:
    """mil/CHRONICLE.md must exist (separate from root CHRONICLE.md)."""
    chronicle = ROOT / "mil" / "CHRONICLE.md"
    if not chronicle.exists():
        violations.append("VIOLATION: mil/CHRONICLE.md does not exist.")


def check_sovereign_brief_exists(violations: list) -> None:
    """SOVEREIGN_BRIEF.md must exist."""
    brief = ROOT / "mil" / "SOVEREIGN_BRIEF.md"
    if not brief.exists():
        violations.append("VIOLATION: mil/SOVEREIGN_BRIEF.md does not exist.")


def check_outputs_exit_point(violations: list) -> None:
    """mil/outputs/mil_findings.json must exist."""
    findings = ROOT / "mil" / "outputs" / "mil_findings.json"
    if not findings.exists():
        violations.append("VIOLATION: mil/outputs/mil_findings.json does not exist — the exit point is missing.")


def check_barclays_not_present(violations: list) -> None:
    """
    P5 Identity Shield — TAQ Bank (client) must never appear in mil/ files.
    Barclays is the client identifier to check.
    This check is intentionally case-insensitive.
    """
    mil_dir = ROOT / "mil"
    if not mil_dir.exists():
        return

    # Check all text files in mil/
    extensions = [".py", ".yaml", ".yml", ".json", ".md", ".txt"]
    for ext in extensions:
        for f in mil_dir.rglob(f"*{ext}"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "barclays" in content.lower():
                    rel = f.relative_to(ROOT)
                    violations.append(
                        f"VIOLATION [P5 IDENTITY SHIELD]: {rel} contains 'Barclays' — "
                        f"client name must never appear in MIL files. "
                        f"Substitute with TAQ Bank if internal reference required."
                    )
            except Exception:
                pass


def main():
    print("=" * 60)
    print("MIL Import Rule Validator")
    print("Zero Entanglement + P5 Identity Shield check")
    print("=" * 60)
    print()

    violations = []

    print("Checking mil/ files do not import internal modules...")
    check_mil_imports_internal(violations)

    print("Checking external files do not import mil/ directly...")
    check_external_imports_mil(violations)

    print("Checking constitutional documents exist...")
    check_mil_schema_exists(violations)
    check_chronicle_exists(violations)
    check_sovereign_brief_exists(violations)
    check_outputs_exit_point(violations)

    print("Checking P5 Identity Shield (client name not in mil/ files)...")
    check_barclays_not_present(violations)

    print()

    if not violations:
        print("PASS: All MIL Import Rule checks passed.")
        print("PASS: Zero Entanglement preserved.")
        print("PASS: P5 Identity Shield — no client references in mil/ files.")
        print()
        print("Exit code: 0")
        sys.exit(0)
    else:
        hard_failures = [v for v in violations if v.startswith("VIOLATION")]
        warnings = [v for v in violations if v.startswith("WARNING")]

        if warnings:
            print("WARNINGS (human review required):")
            for w in warnings:
                print(f"  {w}")
            print()

        if hard_failures:
            print(f"HARD FAILURES: {len(hard_failures)} Zero Entanglement violation(s):")
            for f in hard_failures:
                print(f"  {f}")
            print()
            print("Build FAILED. Resolve all violations before committing.")
            print("Exit code: 1")
            sys.exit(1)
        else:
            # Warnings only
            print("PASS with warnings. Review items above.")
            print("Exit code: 0")
            sys.exit(0)


if __name__ == "__main__":
    main()
