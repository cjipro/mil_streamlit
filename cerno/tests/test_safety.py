"""Tests for cerno.safety — the import-time banned-imports gate."""

from __future__ import annotations

import sys

import pytest

from cerno.safety import BANNED, SafetyViolation, assert_safe


def test_assert_safe_passes_on_clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make doubly sure no banned module is in sys.modules.
    for name in BANNED:
        monkeypatch.delitem(sys.modules, name, raising=False)
    assert_safe()  # should not raise


def test_assert_safe_raises_when_banned_module_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", object())
    with pytest.raises(SafetyViolation, match="banned modules"):
        assert_safe()


def test_safety_violation_is_an_importerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Downstream code that catches ImportError must catch the violation."""
    monkeypatch.setitem(sys.modules, "openai", object())
    with pytest.raises(ImportError):
        assert_safe()


def test_assert_safe_lists_all_banned_modules_in_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", object())
    monkeypatch.setitem(sys.modules, "transformers", object())
    with pytest.raises(SafetyViolation) as exc:
        assert_safe()
    assert "torch" in str(exc.value)
    assert "transformers" in str(exc.value)
