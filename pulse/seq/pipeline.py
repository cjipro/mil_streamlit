"""End-to-end behavioral-sequence pipeline (PULSE-130) — air-gapped edge node.

DuckDB tokenises + chronologically stitches sessions (persisting the vocab as the
tokeniser artifact), a sharded + shuffled PyArrow IterableDataset streams fixed
512-token windows RAM-bounded, and an OFFLINE HuggingFace GPT-2 trains on them.

Approved stack only (confirmed on edge node 2026-05-23): duckdb 1.5.2,
pyarrow 18.1.0, torch 2.5.0+cu124, transformers 4.44.1, numpy 1.26.4. Python 3.11.

Expected raw schema (sessionised upstream, one row per event):
    customer_id, session_id, session_start, sequence_order, operation
"""

from __future__ import annotations

import os
import random
import time

import duckdb
import pyarrow.parquet as pq
import torch
from torch.utils.data import DataLoader, IterableDataset
from transformers import GPT2Config, GPT2LMHeadModel

# Total isolation from the Hugging Face Hub for the whole process lifecycle.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Reserved special-token ids: [PAD]=0, [UNK]=1, [BOS]=2, [EOS]=3, [SEP]=4
PAD_ID, UNK_ID, BOS_ID, EOS_ID, SEP_ID = 0, 1, 2, 3, 4


# ---------------------------------------------------------------------------
# Stage 1 — deterministic tokenise + chronological stitch + vocab persistence
# ---------------------------------------------------------------------------
def run_duckdb_pipeline(raw_parquet_dir: str, output_parquet_path: str, vocab_path: str) -> int:
    con = duckdb.connect()

    if os.path.exists(vocab_path):
        # Inference / incremental mode: reuse the frozen tokeniser. Never renumber.
        print(f"[seq] loading existing vocab artifact: {vocab_path}")
        con.execute(f"CREATE TABLE vocab AS SELECT * FROM '{vocab_path}'")
    else:
        # Initial build: deterministic ids (ORDER BY operation), ops start at 11.
        print("[seq] building fresh deterministic vocab")
        con.execute(f"""
            CREATE TABLE vocab AS
            SELECT operation, CAST(ROW_NUMBER() OVER (ORDER BY operation) + 10 AS INTEGER) AS token_id
            FROM (SELECT DISTINCT operation FROM '{raw_parquet_dir}/*.parquet')
            WHERE operation IS NOT NULL
        """)
        con.execute(f"INSERT INTO vocab VALUES ('[UNK]', {UNK_ID}), ('[SEP]', {SEP_ID})")
        con.execute(f"COPY vocab TO '{vocab_path}' (FORMAT PARQUET)")  # THIS IS THE TOKENISER
        print(f"[seq] persisted vocab artifact: {vocab_path}")

    # LEFT JOIN + coalesce → unseen ops route to [UNK] (never dropped, never renumbered).
    print("[seq] stitching sessions chronologically per customer")
    con.execute(f"""
        COPY (
            SELECT
                customer_id,
                flatten(list(session_tokens ORDER BY session_start, session_id))::INT[] AS input_ids
            FROM (
                SELECT
                    customer_id, session_id, session_start,
                    list_append(
                        list(COALESCE(v.token_id, {UNK_ID}) ORDER BY sequence_order), {SEP_ID}
                    ) AS session_tokens
                FROM '{raw_parquet_dir}/*.parquet' p
                LEFT JOIN vocab v ON p.operation = v.operation
                GROUP BY customer_id, session_id, session_start
            )
            GROUP BY customer_id
        ) TO '{output_parquet_path}' (FORMAT PARQUET, ROW_GROUP_SIZE 10000)
    """)

    vocab_size = con.execute("SELECT MAX(token_id) FROM vocab").fetchone()[0] + 1
    print(f"[seq] pipeline complete · vocab_size={vocab_size}")
    return vocab_size


# ---------------------------------------------------------------------------
# Stage 2 — sharded, shuffled, RAM-bounded streaming dataset
# ---------------------------------------------------------------------------
class ShardedSessionDataset(IterableDataset):
    def __init__(self, parquet_path: str, block_size: int = 512,
                 shuffle_buffer: int = 20000, seed: int = 42):
        self.parquet_path = parquet_path
        self.block_size = block_size
        self.shuffle_buffer = shuffle_buffer
        self.seed = seed

    def __iter__(self):
        pf = pq.ParquetFile(self.parquet_path, memory_map=True)
        n_rg = pf.num_row_groups

        wi = torch.utils.data.get_worker_info()
        wid, nw = (wi.id, wi.num_workers) if wi else (0, 1)
        if wid == 0 and nw > n_rg:
            print(f"[seq][warn] {nw} workers > {n_rg} row groups — extra workers idle.")

        # Per-epoch reshuffle relies on the per-worker seed the DataLoader rotates each
        # epoch; single-process (no workers) uses a fixed seed → reproducible order.
        epoch_salt = torch.initial_seed() if wi else self.seed
        rng = random.Random(self.seed ^ wid ^ epoch_salt)

        rgs = list(range(wid, n_rg, nw))   # shard row groups across workers — no dupes
        rng.shuffle(rgs)

        buf: list = []
        for rg_idx in rgs:
            col = pf.read_row_group(rg_idx, columns=["input_ids"]).column("input_ids")
            for hist in col.to_pylist():
                if not hist:
                    continue
                for j in range(0, len(hist), self.block_size):
                    chunk = hist[j:j + self.block_size]
                    if len(chunk) != self.block_size:
                        continue
                    buf.append(chunk)
                    if len(buf) >= self.shuffle_buffer:     # reservoir shuffle buffer
                        k = rng.randrange(len(buf))
                        t = torch.tensor(buf[k], dtype=torch.long)
                        buf[k] = buf[-1]; buf.pop()
                        yield {"input_ids": t, "labels": t.clone()}
        rng.shuffle(buf)
        for chunk in buf:
            t = torch.tensor(chunk, dtype=torch.long)
            yield {"input_ids": t, "labels": t.clone()}


# ---------------------------------------------------------------------------
# Stage 3 — offline GPT-2 training
# ---------------------------------------------------------------------------
def train_behavioral_transformer(tokenized_parquet: str, vocab_size: int,
                                 context_window: int = 512, max_steps: int = 1000,
                                 batch_size: int = 16) -> None:
    """Native PyTorch loop — **no HF Trainer** (and therefore no `accelerate`,
    which transformers' Trainer hard-requires and which is NOT in the bank
    approved-libs / not on the edge node — PULSE-130). Auto-detects device.

    NB: the bank edge node is **CPU-only** (PULSE-130), so this is the OFF-NODE
    reference; real pretraining belongs on a GPU box. The architecture below is
    deliberately small to stay CPU-runnable; size it up off-node on a GPU.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = GPT2Config(
        vocab_size=vocab_size, n_positions=context_window,
        n_layer=4, n_head=4, n_embd=256,   # illustrative CPU-runnable scale
        bos_token_id=BOS_ID, eos_token_id=EOS_ID, pad_token_id=PAD_ID,
    )
    model = GPT2LMHeadModel(config).to(device)   # local init — no Hub fetch
    print(f"[seq] {model.num_parameters():,} params on {device}")

    loader = DataLoader(
        ShardedSessionDataset(tokenized_parquet, block_size=context_window),
        batch_size=batch_size, num_workers=0,
    )
    opt = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=0.01)
    model.train()
    t0 = time.time()
    for step, batch in enumerate(loader):
        if step >= max_steps:
            break
        ids = batch["input_ids"].to(device)
        loss = model(input_ids=ids, labels=batch["labels"].to(device)).loss
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step % 50 == 0:
            print(f"[seq] step {step} · loss {loss.item():.4f} · {time.time() - t0:.1f}s")
    print("[seq] native loop done — ran without HF Trainer / accelerate.")


if __name__ == "__main__":
    RAW_DIR = "/data/local_cache/raw_sessions"
    PREPPED = "/data/local_cache/prepped_tokenized_data.parquet"
    VOCAB = "/data/local_cache/production_vocabulary.parquet"

    vocab_size = run_duckdb_pipeline(RAW_DIR, PREPPED, VOCAB)
    train_behavioral_transformer(PREPPED, vocab_size=vocab_size)
