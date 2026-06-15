"""Shared pytest fixtures for the cerno test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# Ensure src/ is on sys.path even when pytest is invoked without
# pip-installing the package (matches the bank edge-node pattern where
# we run from a clone, not a pip install).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def sample_settings_yaml(tmp_path: Path) -> Path:
    """A minimal valid settings YAML, bound to dummy placeholders + paths."""
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        "identity_col: aid\n"
        "timestamp_col: event_ts\n"
        "opcode_col: op_code\n"
        "status_col: status_code\n"
        "success_sentinel: '00000'\n"
        "payload_col: payload\n"
        "idle_threshold_min: 20\n"
        f"extract_dir: {tmp_path / 'extract'}\n"
        f"ma_d_dir: {tmp_path / 'ma_d'}\n"
        f"ma_s_dir: {tmp_path / 'ma_s'}\n"
        f"marts_dir: {tmp_path / 'marts'}\n"
        f"manifests_dir: {tmp_path / 'manifests'}\n"
        f"findings_dir: {tmp_path / 'findings'}\n",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def mini_ma_d_rows() -> list[dict]:
    """A tiny synthetic MA_D dataset: ~50 events, 5 sessions, 1 journey.

    One planted error to exercise the -ERROR sentinel; one bounce session
    (single event) to confirm the bounce flag. Deterministic.
    """
    rows: list[dict] = []
    sessions = [
        ("s1", ["login", "screen.home", "screen.loans.step1", "screen.loans.step2",
                "screen.loans.step3", "screen.loans.confirm"]),
        ("s2", ["login", "screen.home", "screen.loans.step1", "screen.loans.step2",
                "screen.loans.step3"]),  # ends mid-journey
        ("s3", ["login", "screen.home", "api.balance", "screen.home", "logout"]),
        ("s4", ["login", "screen.home", "screen.loans.step1", "screen.loans.step1",
                "screen.loans.step1"]),  # repeated_identical_failure setup
        ("s5", ["login"]),  # bounce
    ]
    seq = 1
    ts_start = 1_700_000_000
    for sid, ops in sessions:
        for i, op in enumerate(ops):
            status = "00000"
            # plant an error on s4's repeated step
            if sid == "s4" and op == "screen.loans.step1" and i >= 1:
                status = "E142"
            rows.append({
                "aid": sid,
                "event_ts": ts_start + seq * 10,
                "op_code": op,
                "status_code": status,
                "sequence_no": i + 1,
                "payload": "{}",
            })
            seq += 1
    return rows
