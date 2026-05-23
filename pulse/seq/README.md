# pulse/seq — behavioral-sequence model spike (PULSE-130)

Models customer journeys as **token sequences** and trains a small, fully
**offline** Transformer on them, on the air-gapped bank edge node.

> **Lane:** dev/research — **not** the Pulse procurement runtime, which stays
> classical-ML + statistics per the locked design. A Transformer is non-LLM (so
> the non-LLM-runtime lock doesn't bar it), but it's a black-box deep model:
> taking it into the serving path would need a model-governance story
> (explainability / validation / drift) that is **out of scope for this spike**.

## Pipeline
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
   `GPT2Config` built locally, `report_to="none"`); `labels=input_ids` (HF
   shifts internally for next-token prediction).

## Run order
```
py pulse/seq/preflight.py     # offline env gate — MUST pass on the node first
py pulse/seq/pipeline.py      # tokenise → stream → train
```

## Expected raw schema (sessionised upstream)
One row per event: `customer_id, session_id, session_start, sequence_order, operation`.

## Special tokens
`[PAD]=0  [UNK]=1  [BOS]=2  [EOS]=3  [SEP]=4`; operation IDs start at 11.

## Approved stack (confirmed on edge node 2026-05-23)
Python 3.11.9 · duckdb 1.5.2 · pyarrow 18.1.0 · torch 2.5.0+cu124 (GPU) ·
transformers 4.44.1 · numpy 1.26.4. All captured in `APPROVED_LIBRARIES.md`
(pins for `torch`/`transformers`/`tokenizers` to be finalised from a
`pip list --format=freeze` on the node).

## Boundaries
- No `mil/` imports (Zero Entanglement). No real PII — real-bank ingestion stays
  on the work machine; this spike runs on synthetic/edge-local data only.
- **Gate:** `preflight.py` must pass on the node before any real-data run.
