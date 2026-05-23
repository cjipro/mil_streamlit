# pulse/seq — behavioral-sequence models

Models customer journeys as **sequences** and learns what a *normal* one looks
like, so the surprising (friction) ones stand out. Two lanes, same idea:

| Lane | Module | Where it runs | Status |
|---|---|---|---|
| **Classical (in-bank, on-mission)** | `transitions.py` (PULSE-131) | inside the bank, the locked Pulse runtime | the serving-eligible path |
| **Transformer (off-node research)** | `pipeline.py` + `preflight.py` (PULSE-130) | off-node GPU box only | dev/research spike |

> **Why two lanes.** The bank edge node is **CPU-only** with **no `accelerate`**
> (confirmed 2026-05-23), and a Transformer is a black-box deep model that would
> need a model-governance story (explainability / validation / drift) before it
> could serve. So the Transformer is a **research spike only**; the **classical
> transition model is the in-bank path** — classical ML + statistics, explainable,
> deterministic, on approved bank libs, per the locked non-LLM runtime.

---

## Classical lane — `transitions.py` (PULSE-131)

The in-bank counterpart to the Transformer, done classically:

1. **DuckDB within-session transition model.** A first-order Markov model over
   each session's event-type sequence (ordered by `sequence_no`, the canonical
   rule — not event_ts). DuckDB's `LAG` window builds (from → to) transition
   counts; Python adds Laplace smoothing. The smoothed transition table **is the
   model artifact** — persisted and frozen on reuse, exactly as PULSE-130
   persists its vocab as the tokeniser.
2. **Per-session features.** Each path is scored against the corpus model into
   interpretable features — mean/max transition **surprisal** (-log2 P), rarest
   transition, count of rare transitions, self-loop ratio — plus cheap
   behavioural counts (errors / back-presses / retries / dwell / duration).
   Friction surfaces as surprising, rare, self-looping transitions
   (`error→dwell`, `back_press→back_press`, `dwell→hesitation→exit`).
3. **scikit-learn classifier.** A `StandardScaler → LogisticRegression` pipeline.
   Interpretable coefficients, calibrated probabilities, deterministic per seed.

**Honest scope:** on the synthetic corpus the friction label is *defined by* the
injected events, so separation is near-perfect — the spike validates the
**pipeline shape** on approved in-bank libs, and the report fits a
**transition-features-only** model to show the sequence structure alone carries
the signal. In-bank, the same features predict the harder, telemetry-only target
of journey non-completion (no annotation needed). Reads MA_D directly — no TAQ /
real-bank dependency; the synthetic corpus comes from the PULSE-28 generator.

```
py -m pulse.seq.transitions --sessions 2000 --seed 20260523   # generate → model → features → train
```

Artifacts land in `--workdir` (default `dist/seq`): `ma_d/`,
`transition_model.parquet` (+ `.meta.json`), `report.json`.

---

## Transformer lane — `pipeline.py` (PULSE-130, off-node research only)

> **Lane:** dev/research — **not** the Pulse procurement runtime. A Transformer
> is non-LLM (so the non-LLM-runtime lock doesn't bar it), but it's a black-box
> deep model: serving it would need a governance story that is **out of scope
> for this spike**.

### Pipeline
1. **DuckDB** (`run_duckdb_pipeline`) — operation strings → integer token IDs
   (deterministic, `ORDER BY operation`); events ordered by `sequence_order`
   within a session; sessions chronologically stitched per customer
   (`ORDER BY session_start, session_id`) with `[SEP]` between them; `flatten()`
   to one token stream per customer → Parquet. **The vocab is persisted as the
   tokeniser artifact** — reused on later runs (new ops → `[UNK]`, never
   renumbered), so the model stays consistent.
2. **PyArrow** (`ShardedSessionDataset`) — `memory_map`'d Parquet, row groups
   sharded across DataLoader workers (no duplication), reservoir shuffle buffer
   + shuffled row-group order, fixed 512-token windows. RAM-bounded (one row
   group at a time).
3. **HF GPT-2** (`train_behavioral_transformer`) — offline (`HF_HUB_OFFLINE`,
   `GPT2Config` built locally); `labels=input_ids` (HF shifts internally for
   next-token prediction). Trained with a **native PyTorch loop** (AdamW), **not**
   the HF `Trainer` — `Trainer` hard-requires `accelerate`, which is **not** in
   the approved libs / not on the node (confirmed 2026-05-23). Auto-detects
   device; the node is **CPU-only**, so this is the off-node reference.

### Run order
```
py pulse/seq/preflight.py     # offline env gate — MUST pass on the node first
py pulse/seq/pipeline.py      # tokenise → stream → train
```

### Expected raw schema (sessionised upstream)
One row per event: `customer_id, session_id, session_start, sequence_order, operation`.

### Special tokens
`[PAD]=0  [UNK]=1  [BOS]=2  [EOS]=3  [SEP]=4`; operation IDs start at 11.

---

## Approved stack (both lanes — confirmed on edge node 2026-05-23)
Python 3.11.9 · duckdb 1.5.2 · pyarrow 18.1.0 · numpy 1.26.4 · scikit-learn 1.5.1
(classical lane) · torch 2.5.0+cu124 + transformers 4.44.1 (Transformer lane).
**No `accelerate`** (so no HF `Trainer`). The `+cu124` is the CUDA *wheel build*,
**not** GPU hardware — the node is **CPU-only** (`torch.cuda.is_available()` is
`False`). All captured in `APPROVED_LIBRARIES.md`.

## Boundaries (both lanes)
- No `mil/` imports (Zero Entanglement). No real PII — real-bank ingestion stays
  on the work machine; both lanes run on synthetic / edge-local data only.
- **Transformer gate:** `preflight.py` must pass on the node before any
  real-data Transformer run.
