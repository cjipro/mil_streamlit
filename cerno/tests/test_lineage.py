"""Tests for cerno.lineage — chain_id + verify_chain."""

from __future__ import annotations

from dataclasses import replace

from cerno.lineage import chain_id, verify_chain
from cerno.manifest import Manifest


def _m(layer: str, snap: str, source: str | None = None) -> Manifest:
    return Manifest(
        layer=layer,
        grain="row",
        row_count=10,
        snapshot_id=snap,
        source_snapshot_id=source,
    )


def test_chain_id_deterministic() -> None:
    a = chain_id("prev123", "this456")
    b = chain_id("prev123", "this456")
    assert a == b
    assert len(a) == 16


def test_chain_id_differs_for_different_inputs() -> None:
    a = chain_id("prev123", "this456")
    b = chain_id("prev123", "this789")
    assert a != b


def test_chain_id_handles_none_prev() -> None:
    a = chain_id(None, "head")
    b = chain_id("", "head")
    # Documented: None normalises to "".
    assert a == b


def test_verify_chain_passes_on_intact_chain() -> None:
    m_src = _m("source", "s0")
    m_ma_d = _m("ma_d", "d1", source="s0")
    m_ma_s = _m("ma_s", "ss2", source="d1")
    ok, errors = verify_chain([m_src, m_ma_d, m_ma_s])
    assert ok, errors


def test_verify_chain_detects_mutated_link() -> None:
    m_src = _m("source", "s0")
    m_ma_d = _m("ma_d", "d1", source="s0")
    # Mutate ma_s's source pointer — chain should break at index 2.
    m_ma_s = _m("ma_s", "ss2", source="WRONG")
    ok, errors = verify_chain([m_src, m_ma_d, m_ma_s])
    assert not ok
    assert any("index 2" in e for e in errors)


def test_verify_chain_single_manifest_is_ok() -> None:
    ok, errors = verify_chain([_m("head", "h0")])
    assert ok
    assert errors == []


def test_verify_chain_detects_first_link_break() -> None:
    m_src = _m("source", "s0")
    m_ma_d = _m("ma_d", "d1", source="not_s0")
    ok, errors = verify_chain([m_src, m_ma_d])
    assert not ok
    assert any("index 1" in e for e in errors)
