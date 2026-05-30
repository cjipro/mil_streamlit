"""Tests for cerno.settings — bindings loader + validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from cerno.settings import Settings


def test_from_yaml_loads_known_keys(sample_settings_yaml: Path) -> None:
    s = Settings.from_yaml(sample_settings_yaml)
    assert s.identity_col == "aid"
    assert s.timestamp_col == "event_ts"
    assert s.success_sentinel == "00000"
    assert s.idle_threshold_min == 20


def test_from_yaml_raises_on_unknown_key(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(
        "identity_col: aid\n"
        "some_nonsense_key: hello\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="some_nonsense_key"):
        Settings.from_yaml(cfg)


def test_validate_fails_on_placeholder_bindings() -> None:
    s = Settings()  # defaults are all placeholders
    with pytest.raises(ValueError, match="placeholders"):
        s.validate()


def test_validate_passes_on_bound_settings(sample_settings_yaml: Path) -> None:
    s = Settings.from_yaml(sample_settings_yaml)
    s.validate()  # should not raise


def test_validate_reports_unset_field_names() -> None:
    s = Settings(
        identity_col="aid",
        timestamp_col="event_ts",
        opcode_col="[opcode_col]",  # still a placeholder
        status_col="status",
        success_sentinel="00000",
    )
    with pytest.raises(ValueError) as exc:
        s.validate()
    assert "opcode_col" in str(exc.value)


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CERNO_IDENTITY_COL", "user_id")
    monkeypatch.setenv("CERNO_TIMESTAMP_COL", "ts")
    s = Settings.from_env()
    assert s.identity_col == "user_id"
    assert s.timestamp_col == "ts"


def test_ensure_dirs_creates_paths(tmp_path: Path) -> None:
    s = Settings(
        identity_col="aid",
        timestamp_col="ts",
        opcode_col="op",
        status_col="st",
        success_sentinel="ok",
        extract_dir=str(tmp_path / "extract"),
        ma_d_dir=str(tmp_path / "ma_d"),
        ma_s_dir=str(tmp_path / "ma_s"),
        marts_dir=str(tmp_path / "marts"),
        manifests_dir=str(tmp_path / "manifests"),
        findings_dir=str(tmp_path / "findings"),
    )
    s.ensure_dirs()
    for sub in ("extract", "ma_d", "ma_s", "marts", "manifests", "findings"):
        assert (tmp_path / sub).is_dir()
