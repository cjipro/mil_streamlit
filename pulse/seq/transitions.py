"""Classical within-session transition model (PULSE-131) — the in-bank lane.

The classical, **in-bank, on-mission** counterpart to the PULSE-130 Transformer
spike. Where PULSE-130 trains a deep next-token model OFF-NODE (the bank edge is
CPU-only, no `accelerate`), this stays inside the locked Pulse runtime:
classical ML + statistics, deterministic, explainable, on the approved bank libs
(duckdb 1.5.2, numpy 1.26.4, scikit-learn 1.5.1). Procurement-passable.

Same idea as the Transformer — *learn what a normal behavioural sequence looks
like, then flag the surprising ones* — done classically:

  1. **DuckDB within-session transition model.** A first-order Markov model over
     the per-session event-type sequence (ordered by `sequence_no`, the canonical
     ordering rule — NOT event_ts). DuckDB's `LAG` window builds the
     (from_token -> to_token) transition counts; Python adds Laplace smoothing.
     The smoothed transition table IS the model artifact — persisted and frozen
     on reuse, exactly as PULSE-130 persists its vocab as the tokeniser.
  2. **Per-session features.** Each session's path is scored against the corpus
     transition model into interpretable features — mean/max transition surprisal
     (-log2 P), rarest transition, count of rare transitions, self-loop ratio —
     plus a few cheap behavioural counts. Friction shows up as surprising,
     rare, self-looping transitions (error->dwell, back_press->back_press,
     dwell->hesitation->exit).
  3. **scikit-learn classifier.** A `StandardScaler -> LogisticRegression`
     pipeline over those features. Interpretable coefficients, calibrated
     probabilities, deterministic for a fixed seed.

Honest scope note: on the synthetic corpus the friction label is *defined by*
the injected events (errors / back-presses / hesitation), so behavioural +
surprisal features separate it near-perfectly. The spike validates the *pipeline
shape* on approved in-bank libs, not a hard prediction task — the report also
fits a **transition-features-only** model so you can see the sequence structure
alone carries the signal. In-bank these same features predict the harder,
telemetry-only target of journey non-completion (no annotation needed).

Boundaries: no `mil/` imports (Zero Entanglement); synthetic / edge-local data
only — real-bank ingestion stays on the work machine.

Run:  py -m pulse.seq.transitions --sessions 2000 --seed 20260523
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

# Probability below which a taken transition counts as "rare" (a friction tell).
_RARE_TRANSITION_PROB = 0.01

# Feature column order is the model's contract — keep it stable. The transition
# group is the sequence model's own contribution; the behavioural group is the
# cheap MA_S-style aggregate baseline it's measured against.
_TRANSITION_FEATURES: tuple[str, ...] = (
    "n_transitions",
    "mean_surprisal",
    "max_surprisal",
    "min_transition_prob",
    "n_rare_transitions",
    "self_loop_ratio",
)
_BEHAVIOURAL_FEATURES: tuple[str, ...] = (
    "n_errors",
    "n_back_press",
    "n_retries",
    "max_dwell_seconds",
    "duration_seconds",
)
FEATURE_NAMES: tuple[str, ...] = _TRANSITION_FEATURES + _BEHAVIOURAL_FEATURES


# ── transition model ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransitionModel:
    """First-order Markov transition model over within-session event-type tokens.

    `counts[(from, to)]` are corpus transition counts; `from_totals[from]` the
    row totals; `vocab` the observed token set. `prob`/`surprisal` apply add-alpha
    (Laplace) smoothing so an unseen pair on a new session still scores finitely
    (the classical analog of routing unseen ops to `[UNK]` in PULSE-130)."""

    counts: dict[tuple[str, str], int]
    from_totals: dict[str, int]
    vocab: tuple[str, ...]
    alpha: float
    n_transitions: int

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    def prob(self, frm: str, to: str) -> float:
        """Smoothed P(to | from). Uniform 1/V for a fully unseen `from` state."""
        v = self.vocab_size
        if v == 0:
            return 0.0
        num = self.counts.get((frm, to), 0) + self.alpha
        den = self.from_totals.get(frm, 0) + self.alpha * v
        return num / den

    def surprisal(self, frm: str, to: str) -> float:
        """-log2 P(to | from). High = the path took an unexpected step."""
        p = self.prob(frm, to)
        return -math.log2(p) if p > 0 else float("inf")


def build_transition_model(
    ma_d_dir: str | Path, *, alpha: float = 1.0, artifact_path: str | Path | None = None
) -> TransitionModel:
    """Build (or reuse a frozen) within-session transition model from MA_D.

    DuckDB's `LAG` window pairs each event with its in-session predecessor
    (ordered by sequence_no), and the GROUP BY tallies (from -> to) counts. If
    `artifact_path` exists the frozen model is loaded instead of rebuilt — the
    tokeniser-is-an-artifact discipline from PULSE-130."""
    if artifact_path is not None and Path(artifact_path).exists():
        return _load_artifact(artifact_path)

    glob = str(Path(ma_d_dir) / "**" / "*.parquet")
    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            WITH seq AS (
                SELECT
                    event_type AS to_tok,
                    LAG(event_type) OVER (
                        PARTITION BY session_id ORDER BY sequence_no
                    ) AS from_tok
                FROM read_parquet(?, hive_partitioning = true)
            )
            SELECT from_tok, to_tok, count(*) AS n
            FROM seq
            WHERE from_tok IS NOT NULL
            GROUP BY from_tok, to_tok
            ORDER BY from_tok, to_tok
            """,
            [glob],
        ).fetchall()
    finally:
        con.close()

    counts: dict[tuple[str, str], int] = {}
    from_totals: dict[str, int] = {}
    vocab: set[str] = set()
    total = 0
    for frm, to, n in rows:
        counts[(frm, to)] = int(n)
        from_totals[frm] = from_totals.get(frm, 0) + int(n)
        vocab.add(frm)
        vocab.add(to)
        total += int(n)

    model = TransitionModel(
        counts=counts,
        from_totals=from_totals,
        vocab=tuple(sorted(vocab)),
        alpha=alpha,
        n_transitions=total,
    )
    if artifact_path is not None:
        _persist_artifact(model, artifact_path)
    return model


def _persist_artifact(model: TransitionModel, artifact_path: str | Path) -> None:
    """Persist the transition counts (Parquet) + a small meta sidecar (JSON)."""
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({
        "from_tok": [k[0] for k in model.counts],
        "to_tok": [k[1] for k in model.counts],
        "n": list(model.counts.values()),
    })
    pq.write_table(table, path)
    meta = {
        "alpha": model.alpha,
        "vocab": list(model.vocab),
        "from_totals": model.from_totals,
        "n_transitions": model.n_transitions,
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _load_artifact(artifact_path: str | Path) -> TransitionModel:
    path = Path(artifact_path)
    meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    table = pq.read_table(path)
    frm = table.column("from_tok").to_pylist()
    to = table.column("to_tok").to_pylist()
    n = table.column("n").to_pylist()
    counts = {(f, t): int(c) for f, t, c in zip(frm, to, n)}
    return TransitionModel(
        counts=counts,
        from_totals={k: int(v) for k, v in meta["from_totals"].items()},
        vocab=tuple(meta["vocab"]),
        alpha=float(meta["alpha"]),
        n_transitions=int(meta["n_transitions"]),
    )


# ── per-session features ──────────────────────────────────────────────────────


def session_rows(ma_d_dir: str | Path) -> list[dict[str, Any]]:
    """One row per session: the ordered event-type token list + behavioural counts.

    A single DuckDB aggregate pass — `list(... ORDER BY sequence_no)` reconstructs
    the in-session sequence; the FILTERed counts and max-dwell are the MA_S-style
    behavioural aggregates the classifier uses as its non-sequence baseline."""
    glob = str(Path(ma_d_dir) / "**" / "*.parquet")
    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT
                session_id,
                list(event_type ORDER BY sequence_no)                       AS toks,
                count(*) FILTER (WHERE event_type = 'error')                AS n_errors,
                count(*) FILTER (WHERE event_type = 'back_press')           AS n_back_press,
                count(*) FILTER (WHERE event_type = 'retry')                AS n_retries,
                coalesce(max(CASE WHEN event_type = 'dwell'
                    THEN TRY_CAST(json_extract(payload_json, '$.duration_seconds') AS DOUBLE)
                END), 0.0)                                                  AS max_dwell_seconds,
                date_diff('second',
                    min(strptime(event_ts, '%Y-%m-%dT%H:%M:%SZ')),
                    max(strptime(event_ts, '%Y-%m-%dT%H:%M:%SZ')))          AS duration_seconds
            FROM read_parquet(?, hive_partitioning = true)
            GROUP BY session_id
            ORDER BY session_id
            """,
            [glob],
        ).fetchall()
    finally:
        con.close()

    cols = ["session_id", "toks", "n_errors", "n_back_press", "n_retries",
            "max_dwell_seconds", "duration_seconds"]
    return [dict(zip(cols, r)) for r in rows]


def session_features(toks: list[str], model: TransitionModel, behavioural: dict[str, Any]
                     ) -> dict[str, float]:
    """Score one session's token sequence against the transition model.

    Transition features capture how surprising / rare / self-looping the path is
    versus corpus-normal; behavioural features are cheap aggregate counts. Ordered
    by `FEATURE_NAMES`."""
    surprisals: list[float] = []
    probs: list[float] = []
    self_loops = 0
    for frm, to in zip(toks, toks[1:]):
        surprisals.append(model.surprisal(frm, to))
        probs.append(model.prob(frm, to))
        if frm == to:
            self_loops += 1

    n_trans = len(surprisals)
    feats: dict[str, float] = {
        "n_transitions": float(n_trans),
        "mean_surprisal": float(np.mean(surprisals)) if surprisals else 0.0,
        "max_surprisal": float(max(surprisals)) if surprisals else 0.0,
        "min_transition_prob": float(min(probs)) if probs else 1.0,
        "n_rare_transitions": float(sum(1 for p in probs if p < _RARE_TRANSITION_PROB)),
        "self_loop_ratio": (self_loops / n_trans) if n_trans else 0.0,
    }
    for name in _BEHAVIOURAL_FEATURES:
        feats[name] = float(behavioural.get(name, 0.0) or 0.0)
    return feats


def build_feature_matrix(
    ma_d_dir: str | Path, model: TransitionModel
) -> tuple[np.ndarray, list[str], tuple[str, ...]]:
    """Return (X, session_ids, feature_names) — X rows aligned to session_ids."""
    rows = session_rows(ma_d_dir)
    session_ids: list[str] = []
    matrix: list[list[float]] = []
    for r in rows:
        feats = session_features(list(r["toks"]), model, r)
        session_ids.append(r["session_id"])
        matrix.append([feats[name] for name in FEATURE_NAMES])
    return np.asarray(matrix, dtype=float), session_ids, FEATURE_NAMES


# ── scikit-learn friction classifier ──────────────────────────────────────────


def train_friction_classifier(
    X: np.ndarray, y: np.ndarray, feature_names: tuple[str, ...], *, seed: int = 42
) -> dict[str, Any]:
    """Fit StandardScaler -> LogisticRegression on the session features.

    Deterministic for a fixed `seed`. Reports held-out ROC-AUC / average-precision
    / Brier, the friction-vs-normal mean predicted probability gap, interpretable
    per-feature coefficients, and a transition-features-only AUC so the sequence
    model's standalone contribution is visible. Imports sklearn lazily so importing
    this module costs nothing when only the transition model is wanted."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        precision_recall_fscore_support,
        roc_auc_score,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if len(np.unique(y)) < 2:
        raise ValueError("need both friction and non-friction sessions to train")

    def _fit_eval(Xm: np.ndarray) -> dict[str, Any]:
        X_tr, X_te, y_tr, y_te = train_test_split(
            Xm, y, test_size=0.30, random_state=seed, stratify=y
        )
        clf = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, random_state=seed),
        )
        clf.fit(X_tr, y_tr)
        proba = clf.predict_proba(X_te)[:, 1]
        preds = (proba >= 0.5).astype(int)
        prec, rec, f1, _ = precision_recall_fscore_support(
            y_te, preds, average="binary", zero_division=0
        )
        return {
            "clf": clf,
            "n_train": int(len(y_tr)),
            "n_test": int(len(y_te)),
            "roc_auc": round(float(roc_auc_score(y_te, proba)), 4),
            "average_precision": round(float(average_precision_score(y_te, proba)), 4),
            "brier": round(float(brier_score_loss(y_te, proba)), 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1": round(float(f1), 4),
            "mean_proba_friction": round(float(proba[y_te == 1].mean()), 4),
            "mean_proba_normal": round(float(proba[y_te == 0].mean()), 4),
        }

    full = _fit_eval(X)
    coefs = full.pop("clf").named_steps["logisticregression"].coef_[0]

    # Transition-features-only refit — does sequence structure alone separate friction?
    trans_idx = [feature_names.index(n) for n in _TRANSITION_FEATURES]
    trans_only = _fit_eval(X[:, trans_idx])
    trans_only.pop("clf")

    return {
        "n_sessions": int(len(y)),
        "n_friction": int(y.sum()),
        "friction_rate": round(float(y.mean()), 4),
        "features": list(feature_names),
        "full": full,
        "transition_only": {
            "features": list(_TRANSITION_FEATURES),
            "roc_auc": trans_only["roc_auc"],
            "average_precision": trans_only["average_precision"],
        },
        "coefficients": {n: round(float(c), 4) for n, c in zip(feature_names, coefs)},
    }


# ── CLI: synthetic end-to-end (DuckDB transition model -> features -> sklearn) ──


def _synthetic_friction_labels(seed: int, sessions: int, friction_rate: float, out_dir: Path
                               ) -> dict[str, int]:
    """Generate a labelled synthetic MA_D corpus; return session_id -> friction(0/1).

    Reuses the PULSE-28 generator so the corpus matches the rest of the engine.
    Friction = a planted signature is present (the generator's ground truth)."""
    from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d

    cfg = GeneratorConfig(n_sessions=sessions, seed=seed, friction_rate=friction_rate)
    events, labels = generate(cfg)
    write_ma_d(events, out_dir)
    return {lab["session_id"]: int(lab["planted_signature"] != "none") for lab in labels}


def run_synthetic(
    *, sessions: int = 2000, seed: int = 20260523, friction_rate: float = 0.35,
    workdir: str | Path = "dist/seq",
) -> dict[str, Any]:
    """One-command spike: generate -> DuckDB transition model -> features -> train."""
    work = Path(workdir)
    if work.exists():
        shutil.rmtree(work)
    ma_d = work / "ma_d"

    label_by_session = _synthetic_friction_labels(seed, sessions, friction_rate, ma_d)
    model = build_transition_model(ma_d, artifact_path=work / "transition_model.parquet")
    X, session_ids, names = build_feature_matrix(ma_d, model)
    y = np.array([label_by_session.get(sid, 0) for sid in session_ids], dtype=int)

    report = train_friction_classifier(X, y, names, seed=seed)
    report["transition_model"] = {
        "vocab": list(model.vocab),
        "vocab_size": model.vocab_size,
        "n_transitions": model.n_transitions,
        "artifact": str(work / "transition_model.parquet"),
    }
    (work / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="Classical within-session transition model (PULSE-131)")
    p.add_argument("--sessions", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260523)
    p.add_argument("--friction-rate", type=float, default=0.35)
    p.add_argument("--workdir", type=str, default="dist/seq")
    args = p.parse_args()
    report = run_synthetic(
        sessions=args.sessions, seed=args.seed,
        friction_rate=args.friction_rate, workdir=args.workdir,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
