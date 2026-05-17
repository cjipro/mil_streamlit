"""Tests for canonical JSON + SHA-256 helpers."""

from __future__ import annotations

import math

import pytest

from pulse.lineage.canonical import canonical_json, sha256_hex


def test_dict_keys_sorted() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_list_order_preserved() -> None:
    # Lists are ordered data — verifier must NOT sort.
    assert canonical_json([3, 1, 2]) == "[3,1,2]"


def test_nested_dict_sorted_recursively() -> None:
    encoded = canonical_json({"outer": {"z": 1, "a": 2}, "alpha": "x"})
    assert encoded == '{"alpha":"x","outer":{"a":2,"z":1}}'


def test_byte_identical_across_reruns() -> None:
    obj = {"k": "v", "n": 42, "list": [1, 2, {"nested": True}]}
    assert canonical_json(obj) == canonical_json(obj)


def test_none_encoded_as_null() -> None:
    assert canonical_json({"k": None}) == '{"k":null}'


def test_booleans_encoded() -> None:
    assert canonical_json({"t": True, "f": False}) == '{"f":false,"t":true}'


def test_unicode_string_preserved() -> None:
    # ensure_ascii=False keeps cohort labels like "über-50" intact.
    assert canonical_json({"k": "über-50"}) == '{"k":"über-50"}'


def test_non_finite_number_rejected() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"k": math.nan})
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"k": math.inf})


def test_non_string_dict_key_rejected() -> None:
    with pytest.raises(TypeError, match="string keys"):
        canonical_json({1: "x"})


def test_tuple_encoded_as_list() -> None:
    assert canonical_json({"k": (1, 2, 3)}) == '{"k":[1,2,3]}'


def test_sha256_hex_lowercase_hex() -> None:
    h = sha256_hex("hello")
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert h == h.lower()
    assert len(h) == 64


def test_sha256_hex_utf8_encoding() -> None:
    # 'café' must hash by UTF-8 bytes, not by latin-1.
    h1 = sha256_hex("café")
    h2 = sha256_hex("caf" + "é")  # same string different construction
    assert h1 == h2
