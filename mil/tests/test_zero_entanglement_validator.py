"""Regression tests for the Zero-Entanglement validator (MIL-176).

Guards two things the MIL-176 fix established:
  - the live tree is GREEN (no hard VIOLATIONs) — the gate is meaningful again
  - the validator still distinguishes MIL's own mil/config from a genuine cross
    into the top-level Pulse config/, and only the documented tools are exempt

The validator lives in scripts/ (not a package), so it's loaded by file path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATOR_PATH = _REPO_ROOT / "scripts" / "validate_mil_import_rule.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_mil_import_rule", _VALIDATOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V = _load_validator()


def test_live_tree_has_no_hard_violations():
    """The whole repo passes the import rule — only WARNINGs (review heuristics) allowed."""
    violations: list[str] = []
    V.check_mil_imports_internal(violations)
    V.check_external_imports_mil(violations)
    hard = [v for v in violations if v.startswith("VIOLATION")]
    assert hard == [], "Zero-Entanglement regressed:\n" + "\n".join(hard)


def test_mil_owns_its_config_imports():
    members = {"thresholds", "tenant_loader", "get_model"}
    # mil/ files importing their OWN mil/config — allowed.
    assert V._config_import_is_mils_own("from config.thresholds import T as _T", "config.thresholds", members)
    assert V._config_import_is_mils_own("from config import tenant_loader as _t", "config", members)
    assert V._config_import_is_mils_own("import config", "config", members)


def test_genuine_cross_into_pulse_config_is_not_exempted():
    """A submodule that exists only in the top-level Pulse config/ is NOT MIL's own."""
    members = {"thresholds", "tenant_loader", "get_model"}
    assert not V._config_import_is_mils_own(
        "from config.governance_principles import P", "config.governance_principles", members)
    assert not V._config_import_is_mils_own(
        "from config import data_dictionary_master", "config", members)


def test_external_allowlist_is_exactly_the_documented_tools():
    assert V.EXTERNAL_MIL_ALLOWLIST == {
        "scripts/clone_doctor.py",
        "app/pages/07_mil.py",
        "app/pages/08_ask_cji_pro.py",
    }


def test_mil_config_members_resolved_from_disk():
    members = V._mil_config_members()
    # The real mil/config package backs the resolver — these must be present.
    assert {"thresholds", "tenant_loader", "get_model"} <= members
    assert "__pycache__" not in members


@pytest.mark.parametrize("internal", ["pulse", "holter", "poc", "app", "dags"])
def test_internal_modules_still_denied(internal):
    """The deny-list is intact — a real engine module is not silently allowed."""
    assert internal in V.INTERNAL_MODULES
