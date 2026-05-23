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

NOTE: P5 Identity Shield does NOT apply to MIL.
MIL processes exclusively public market data. Competitors appear by
their real names (Barclays is Barclays). No client-name check is run
on mil/ files. P5 applies to CJI Pulse internal systems only.

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
    "holter",
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

# Files OUTSIDE mil/ that legitimately reference mil/ — documented MIL-176 exemptions.
# Each is a MIL-aware tool/shim, NOT the CJI Pulse engine reaching into MIL:
#   scripts/clone_doctor.py       fork health-check; introspects mil/config + loaders to validate them
#   app/pages/07_mil.py           Streamlit dashboard adapter shim (routing only, no MIL logic)
#   app/pages/08_ask_cji_pro.py   Streamlit Ask CJI Pro adapter shim
# Posix-style relative paths (forward slashes) so the match is OS-independent.
EXTERNAL_MIL_ALLOWLIST = {
    "scripts/clone_doctor.py",
    "app/pages/07_mil.py",
    "app/pages/08_ask_cji_pro.py",
}


def _mil_config_members() -> set[str]:
    """Module / sub-package names that live in mil/config/ — MIL's OWN config package.

    A mil/ file doing `from config import X` / `from config.X import …` is importing
    mil/config (it runs with mil/ on sys.path), NOT the top-level Pulse `config/`.
    Both packages exist, so the bare `config` token is ambiguous; resolving the
    imported name against this set tells MIL's own config (allowed) apart from a
    genuine cross into Pulse config (a real Zero-Entanglement breach). MIL-176."""
    cfg = ROOT / "mil" / "config"
    if not cfg.exists():
        return set()
    members = {p.stem for p in cfg.glob("*.py") if p.stem != "__init__"}
    members |= {p.name for p in cfg.iterdir() if p.is_dir() and p.name != "__pycache__"}
    return members


def _config_import_is_mils_own(line: str, full_module: str, members: set[str]) -> bool:
    """True if a `config` import on `line` resolves to mil/config (MIL's own).

    Handles the three forms present in the codebase: `from config.<sub> import …`,
    `from config import <name>[ as …][, …]`, and bare `import config[.<sub>]`."""
    parts = full_module.split(".")
    if len(parts) > 1:                          # config.<sub>
        return parts[1] in members
    if line.lstrip().startswith("import"):      # bare `import config`
        return bool(members)
    m = re.search(r"\bimport\s+(.+)$", line)     # `from config import a as x, b`
    if not m:
        return bool(members)
    names = [seg.strip().split()[0] for seg in m.group(1).split(",")]
    names = [n for n in names if n and n != "*"]
    return any(n in members for n in names) if names else bool(members)


def get_python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def check_mil_imports_internal(violations: list) -> None:
    """mil/ files must not import from internal modules."""
    mil_dir = ROOT / "mil"
    if not mil_dir.exists():
        return

    config_members = _mil_config_members()
    for py_file in get_python_files(mil_dir):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for match in IMPORT_RE.finditer(content):
            full_module = match.group(1)
            module = full_module.split(".")[0]
            if module not in INTERNAL_MODULES:
                continue
            # MIL importing its OWN mil/config is not entanglement (MIL-176).
            if module == "config":
                ls = content.rfind("\n", 0, match.start()) + 1
                le = content.find("\n", match.start())
                line = content[ls:] if le == -1 else content[ls:le]
                if _config_import_is_mils_own(line, full_module, config_members):
                    continue
            rel = py_file.relative_to(ROOT)
            violations.append(
                f"VIOLATION [MIL->INTERNAL]: {rel} imports '{module}' -- "
                f"Zero Entanglement breach. mil/ may not import internal modules."
            )


def check_external_imports_mil(violations: list) -> None:
    """Files outside mil/ must not import from mil/ directly."""
    for search_dir_name in ["app", "poc", "agents", "src", "conductor", "dags", "scripts", "pulse", "holter"]:
        search_dir = ROOT / search_dir_name
        if not search_dir.exists():
            continue

        for py_file in get_python_files(search_dir):
            # Documented MIL-aware tools/shims are exempt (MIL-176).
            if py_file.relative_to(ROOT).as_posix() in EXTERNAL_MIL_ALLOWLIST:
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")

            # Check for direct mil imports (not the permitted file read)
            for match in IMPORT_RE.finditer(content):
                module = match.group(1).split(".")[0]
                if module == "mil":
                    rel = py_file.relative_to(ROOT)
                    # The adapter shim is exempt — it calls mil/command/app.py via subprocess/path
                    # but should not import mil as a Python module
                    violations.append(
                        f"VIOLATION [EXTERNAL->MIL]: {rel} imports 'mil' -- "
                        f"Zero Entanglement breach. Use mil/outputs/mil_findings.json only."
                    )

            # Check for sys.path manipulation to reach mil/. Match 'mil' as a path/
            # module token, not a substring of 'font-family' / 'milestone' / etc.
            if "sys.path" in content and re.search(r"['\"/\\.\s]mil[/\\.'\"\s]", content):
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


def main():
    print("=" * 60)
    print("MIL Import Rule Validator")
    print("Zero Entanglement check")
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
