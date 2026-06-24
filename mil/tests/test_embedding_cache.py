"""
mil/tests/test_embedding_cache.py — MIL-183.

The embedding cache must be MODEL-AWARE: swapping the embedding model (or a
legacy cache with no model stamp) must invalidate the cache so we never serve
vectors from one model against query vectors from another.

Run: py -m pytest mil/tests/test_embedding_cache.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from mil.chat.retrievers import embedding as emb


def _write_cache(path, model_name, with_model=True):
    arrs = {"ids": np.array(["E1"]), "vectors": np.zeros((1, 384), dtype=np.float32)}
    if with_model:
        arrs["model"] = np.array(model_name)
    np.savez(path, **arrs)


def test_cache_invalid_when_model_differs(tmp_path, monkeypatch):
    p = tmp_path / "cache.npz"
    _write_cache(p, "some-old-model")
    monkeypatch.setattr(emb, "_CACHE_PATH", p)
    monkeypatch.setattr(emb, "corpus_mtime", lambda: 0.0)   # cache is "fresh" vs corpus
    assert emb._cache_valid() is False                       # but model mismatch → invalid


def test_cache_valid_when_model_matches(tmp_path, monkeypatch):
    p = tmp_path / "cache.npz"
    _write_cache(p, emb._MODEL_NAME)
    monkeypatch.setattr(emb, "_CACHE_PATH", p)
    monkeypatch.setattr(emb, "corpus_mtime", lambda: 0.0)
    assert emb._cache_valid() is True


def test_legacy_cache_without_model_stamp_is_invalid(tmp_path, monkeypatch):
    p = tmp_path / "cache.npz"
    _write_cache(p, "ignored", with_model=False)             # pre-MIL-183 cache shape
    monkeypatch.setattr(emb, "_CACHE_PATH", p)
    monkeypatch.setattr(emb, "corpus_mtime", lambda: 0.0)
    assert emb._cached_model_name() is None
    assert emb._cache_valid() is False


def test_missing_cache_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_CACHE_PATH", tmp_path / "nope.npz")
    assert emb._cache_valid() is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
