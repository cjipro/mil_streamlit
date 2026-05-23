"""Tests for the classical within-session transition model (PULSE-131).

Covers the in-bank classical lane that mirrors the PULSE-130 Transformer spike:
  - DuckDB transition model is valid (smoothed rows sum to 1) and deterministic
  - the persisted artifact reloads to an identical, frozen model
  - per-session features score a hand-built sequence as expected (surprisal,
    self-loop ratio, rare-transition count)
  - the scikit-learn classifier separates friction from normal, is deterministic
    for a fixed seed, and the transition features alone carry signal
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pulse.seq.transitions import (
    FEATURE_NAMES,
    TransitionModel,
    build_feature_matrix,
    build_transition_model,
    run_synthetic,
    session_features,
    train_friction_classifier,
)
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d

CFG = GeneratorConfig(n_sessions=160, seed=42, friction_rate=0.4)


def _model() -> TransitionModel:
    """Hand-built model with known counts for exact feature assertions."""
    return TransitionModel(
        counts={("a", "b"): 8, ("b", "a"): 1, ("a", "a"): 1},
        from_totals={"a": 9, "b": 1},
        vocab=("a", "b"),
        alpha=1.0,
        n_transitions=10,
    )


def test_transition_model_is_valid_and_deterministic(tmp_path):
    ev, _ = generate(CFG)
    write_ma_d(ev, tmp_path / "ma_d")

    m1 = build_transition_model(tmp_path / "ma_d")
    m2 = build_transition_model(tmp_path / "ma_d")

    assert m1.counts == m2.counts and m1.from_totals == m2.from_totals
    assert m1.vocab == m2.vocab and m1.n_transitions > 0
    # 'error' and 'back_press' only appear inside planted signatures -> in vocab.
    assert {"screen_view", "dwell", "error", "back_press"} <= set(m1.vocab)

    # Smoothed transition rows are a proper distribution over the vocab per state.
    for frm in m1.vocab:
        total = sum(m1.prob(frm, to) for to in m1.vocab)
        assert total == pytest.approx(1.0, abs=1e-9)


def test_artifact_persist_and_frozen_reuse(tmp_path):
    ev, _ = generate(CFG)
    write_ma_d(ev, tmp_path / "ma_d")
    artifact = tmp_path / "transition_model.parquet"

    built = build_transition_model(tmp_path / "ma_d", artifact_path=artifact)
    assert artifact.exists() and artifact.with_suffix(".meta.json").exists()

    # Reuse loads the frozen artifact (not a rebuild) and is identical.
    reloaded = build_transition_model(tmp_path / "ma_d", artifact_path=artifact)
    assert reloaded.counts == built.counts
    assert reloaded.from_totals == built.from_totals
    assert reloaded.vocab == built.vocab
    assert reloaded.alpha == built.alpha


def test_session_features_on_handbuilt_sequence():
    m = _model()
    behav = {"n_errors": 2, "n_back_press": 0, "n_retries": 1,
             "max_dwell_seconds": 60.0, "duration_seconds": 90.0}
    feats = session_features(["a", "b", "a", "a"], m, behav)

    # Transitions taken: (a,b)=9/11, (b,a)=2/3, (a,a)=2/11.
    assert feats["n_transitions"] == 3.0
    assert feats["self_loop_ratio"] == pytest.approx(1 / 3)
    assert feats["min_transition_prob"] == pytest.approx(2 / 11)
    assert feats["max_surprisal"] == pytest.approx(-math.log2(2 / 11))
    assert feats["mean_surprisal"] == pytest.approx(
        np.mean([-math.log2(9 / 11), -math.log2(2 / 3), -math.log2(2 / 11)])
    )
    assert feats["n_rare_transitions"] == 0.0
    # Behavioural counts pass through, ordered by the feature contract.
    assert feats["n_errors"] == 2.0 and feats["duration_seconds"] == 90.0
    assert list(feats) == list(FEATURE_NAMES)


def test_session_features_handles_short_sequences():
    feats = session_features(["a"], _model(), {})
    assert feats["n_transitions"] == 0.0
    assert feats["mean_surprisal"] == 0.0
    assert feats["min_transition_prob"] == 1.0  # no transition taken -> least surprising
    assert feats["self_loop_ratio"] == 0.0


def test_rare_transition_is_flagged():
    # A transition the corpus never saw, from a high-traffic state, is rare.
    m = TransitionModel(
        counts={("a", "b"): 10_000}, from_totals={"a": 10_000},
        vocab=("a", "b"), alpha=1.0, n_transitions=10_000,
    )
    # P(a->a) = 1 / (10000 + 2) ~ 1e-4 < 0.01 rare threshold.
    feats = session_features(["a", "a"], m, {})
    assert feats["n_rare_transitions"] == 1.0


def test_classifier_separates_friction_and_is_deterministic(tmp_path):
    r1 = run_synthetic(sessions=400, seed=7, friction_rate=0.4, workdir=tmp_path / "r1")
    r2 = run_synthetic(sessions=400, seed=7, friction_rate=0.4, workdir=tmp_path / "r2")

    # Both classes present and a meaningful friction rate.
    assert 0 < r1["n_friction"] < r1["n_sessions"]
    full = r1["full"]
    # Friction is well separated (synthetic — defined by injected events).
    assert full["roc_auc"] > 0.8
    assert full["mean_proba_friction"] > full["mean_proba_normal"]
    # Transition features ALONE carry signal (the sequence model's contribution).
    assert r1["transition_only"]["roc_auc"] > 0.6
    # Fully deterministic for a fixed seed.
    assert r1["full"] == r2["full"]
    assert r1["coefficients"] == r2["coefficients"]
    # Artifacts written.
    assert (tmp_path / "r1" / "transition_model.parquet").exists()
    assert (tmp_path / "r1" / "report.json").exists()


def test_train_requires_both_classes(tmp_path):
    ev, _ = generate(CFG)
    write_ma_d(ev, tmp_path / "ma_d")
    model = build_transition_model(tmp_path / "ma_d")
    X, _, names = build_feature_matrix(tmp_path / "ma_d", model)
    with pytest.raises(ValueError, match="both"):
        train_friction_classifier(X, np.zeros(len(X), dtype=int), names)
