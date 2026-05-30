"""Settings — the bindings layer.

Carries every binding the rest of the package uses: source column names,
sessionise parameters, layer paths, run id. Loaded from env or YAML.
Validates that required source bindings are not still placeholders.

Per D-001: bindings can come from either env (CERNO_*) or YAML, with
YAML preferred where present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path


_REQUIRED_SOURCE_BINDINGS = (
    "identity_col",
    "timestamp_col",
    "opcode_col",
    "status_col",
    "success_sentinel",
)


@dataclass
class Settings:
    """All bindings consumed by the cerno package."""

    # ── source column bindings (operator binds locally per source) ──
    identity_col: str = "[identity_col]"
    timestamp_col: str = "[timestamp_col]"
    opcode_col: str = "[opcode_col]"
    status_col: str = "[status_col]"
    success_sentinel: str = "[success_sentinel]"
    payload_col: str = "[payload_col]"

    # ── sessionise parameters (calibrated from §3 recon, locked as D-NNN) ──
    idle_threshold_min: int = 30
    dwell_cap_s: int = 300

    # ── output layer paths ──
    extract_dir: str = "data/extract"
    ma_d_dir: str = "data/ma_d"
    ma_s_dir: str = "data/ma_s"
    marts_dir: str = "data/marts"
    manifests_dir: str = "manifests"
    findings_dir: str = "findings"

    # ── run identity ──
    run_id: str = ""

    # ────────────────────────────────────────────────────────────────
    # Loaders
    # ────────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "Settings":
        """Load from CERNO_<UPPERCASE_FIELD> environment variables.

        Strings stay as strings; int fields are coerced. Missing env vars
        leave the field at its default (which for source bindings is the
        placeholder — validate() will catch that).
        """
        kwargs: dict[str, object] = {}
        for f in fields(cls):
            env_key = f"CERNO_{f.name.upper()}"
            if env_key in os.environ:
                raw = os.environ[env_key]
                kwargs[f.name] = int(raw) if f.type == "int" else raw
        return cls(**kwargs)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        """Load from a YAML file. Unknown keys raise."""
        import yaml  # local import — PyYAML is approved but optional in some paths

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown settings keys in {path}: {sorted(unknown)}")
        return cls(**data)

    # ────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise ValueError if any required binding is still a placeholder.

        A placeholder is the literal `[name]` string left from defaults.
        Operator must bind these via YAML or env before runtime use.
        """
        unset: list[str] = []
        for name in _REQUIRED_SOURCE_BINDINGS:
            val = getattr(self, name)
            if not val or (isinstance(val, str) and val.startswith("[") and val.endswith("]")):
                unset.append(name)
        if unset:
            raise ValueError(
                f"Required source bindings not bound (still placeholders): {unset}. "
                "Set them in your YAML or via CERNO_* env vars."
            )

    def ensure_dirs(self) -> None:
        """Create all output directories if they don't exist."""
        for d in (
            self.extract_dir,
            self.ma_d_dir,
            self.ma_s_dir,
            self.marts_dir,
            self.manifests_dir,
            self.findings_dir,
        ):
            Path(d).mkdir(parents=True, exist_ok=True)
