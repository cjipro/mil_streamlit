"""Doctor — preflight environment check.

Runs before any cerno code to confirm the runtime is sane:
- Python 3.11.x (the lock; doctor warns on mismatch but does not raise)
- Approved libs importable
- Output directories writable

Exits 0 on green, 1 on red. Operators chain `make doctor && make test`
on the edge node.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Make sure src/ is reachable for the safety import. Doctor runs from
# the repo root.
_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

REQUIRED_PY = (3, 11)
APPROVED_LIBS: tuple[tuple[str, str], ...] = (
    # (display name, import name)
    ("duckdb", "duckdb"),
    ("pyarrow", "pyarrow"),
    ("numpy", "numpy"),
    ("scikit-learn", "sklearn"),
    ("statsmodels", "statsmodels"),
    ("pyspark", "pyspark"),
    ("pyodbc", "pyodbc"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("PyYAML", "yaml"),
    ("joblib", "joblib"),
)
LAYER_DIRS = (
    "data/extract",
    "data/ma_d",
    "data/ma_s",
    "data/marts",
    "manifests",
    "findings",
)


def _mark(ok: bool) -> str:
    return "OK  " if ok else "FAIL"


def _check_python() -> tuple[bool, str]:
    actual = sys.version_info[:3]
    ok = actual[:2] == REQUIRED_PY
    return ok, f"Python {actual[0]}.{actual[1]}.{actual[2]}  (need 3.11.x)"


def _check_libs() -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    for name, import_name in APPROVED_LIBS:
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "(no __version__)")
            out.append((name, True, version))
        except ImportError as exc:
            out.append((name, False, str(exc)))
    return out


def _check_dirs() -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for d in LAYER_DIRS:
        p = _REPO / d
        try:
            p.mkdir(parents=True, exist_ok=True)
            # write probe
            probe = p / ".doctor_probe"
            probe.write_text("ok")
            probe.unlink()
            out.append((str(d), True))
        except OSError:
            out.append((str(d), False))
    return out


def _check_safety_gate() -> tuple[bool, str]:
    try:
        from cerno.safety import assert_safe

        assert_safe()
        return True, "import-time gate clean"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    print("=== cerno doctor ===\n")

    py_ok, py_msg = _check_python()
    print(f"  {_mark(py_ok)} {py_msg}")

    print("\n  libs:")
    libs = _check_libs()
    for name, ok, info in libs:
        print(f"    {_mark(ok)} {name:<14} {info}")

    print("\n  dirs:")
    dirs = _check_dirs()
    for path, ok in dirs:
        print(f"    {_mark(ok)} {path}")

    print("\n  safety:")
    safety_ok, safety_msg = _check_safety_gate()
    print(f"    {_mark(safety_ok)} {safety_msg}")

    all_ok = (
        py_ok
        and all(ok for _, ok, _ in libs)
        and all(ok for _, ok in dirs)
        and safety_ok
    )
    print()
    print("doctor:", "GREEN — all checks passed" if all_ok else "RED — failures present")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
