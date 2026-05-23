"""Offline environment preflight for the pulse.seq pipeline (PULSE-130).

Run this on the air-gapped edge node BEFORE any real-data run. It uses ONLY
synthetic data it generates itself, makes ZERO network calls, and exercises the
exact features the pipeline depends on. Prints PASS/FAIL per check and exits 1
on the first failure; prints `PREFLIGHT PASSED` if the node is cleared.

    py pulse/seq/preflight.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

os.environ["HF_HUB_OFFLINE"] = "1"        # set before importing transformers
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_FAILS: list[str] = []


def check(name, fn):
    try:
        detail = fn()
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    except Exception as e:  # noqa: BLE001 — preflight reports, doesn't raise
        print(f"  ❌ {name} — {type(e).__name__}: {e}")
        _FAILS.append(name)


def main() -> int:
    scratch = tempfile.mkdtemp(prefix="seq_preflight_")
    try:
        # 1) Python + library versions ------------------------------------
        def versions():
            import duckdb, numpy, pyarrow, torch, transformers
            assert sys.version_info[:2] == (3, 11), f"Python {sys.version_info[:3]}, need 3.11"
            return (f"py{sys.version.split()[0]} duckdb{duckdb.__version__} "
                    f"pyarrow{pyarrow.__version__} torch{torch.__version__} "
                    f"transformers{transformers.__version__} numpy{numpy.__version__}")
        check("python 3.11 + imports/versions", versions)

        # 2) DuckDB feature exercise (the exact ops the pipeline uses) -----
        sessions = os.path.join(scratch, "sessions.parquet")
        tokens = os.path.join(scratch, "tokens.parquet")

        def duckdb_features():
            import duckdb, pyarrow as pa, pyarrow.parquet as pq
            # synthetic sessionised events
            tbl = pa.table({
                "customer_id": [1, 1, 1, 2, 2],
                "session_id":  [10, 10, 11, 20, 20],
                "session_start": [1, 1, 2, 1, 1],
                "sequence_order": [1, 2, 1, 1, 2],
                "operation": ["login", "view", "pay", "login", "logout"],
            })
            pq.write_table(tbl, sessions)
            con = duckdb.connect()
            con.execute(f"""CREATE TABLE vocab AS
                SELECT operation, CAST(ROW_NUMBER() OVER (ORDER BY operation) + 10 AS INTEGER) AS token_id
                FROM (SELECT DISTINCT operation FROM '{sessions}') WHERE operation IS NOT NULL""")
            con.execute("INSERT INTO vocab VALUES ('[SEP]', 4)")
            con.execute(f"""COPY (
                SELECT customer_id,
                       flatten(list(s ORDER BY session_start, session_id))::INT[] AS input_ids
                FROM (SELECT customer_id, session_id, session_start,
                             list_append(list(COALESCE(v.token_id,1) ORDER BY sequence_order), 4) AS s
                      FROM '{sessions}' p LEFT JOIN vocab v ON p.operation=v.operation
                      GROUP BY customer_id, session_id, session_start)
                GROUP BY customer_id
            ) TO '{tokens}' (FORMAT PARQUET, ROW_GROUP_SIZE 10000)""")
            return "ROW_NUMBER/list ORDER BY/list_append/flatten/COPY ok"
        check("duckdb tokenise + stitch features", duckdb_features)

        # 3) pyarrow memory-mapped row-group streaming --------------------
        def pyarrow_stream():
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(tokens, memory_map=True)
            rows = pf.read_row_group(0, columns=["input_ids"]).column("input_ids").to_pylist()
            assert rows and rows[0], "no streamed rows"
            return f"{pf.num_row_groups} row group(s), {len(rows)} customers"
        check("pyarrow memory_map + read_row_group + to_pylist", pyarrow_stream)

        # 4) offline GPT-2 build + one forward/backward -------------------
        def model_fwd_bwd():
            import torch
            from transformers import GPT2Config, GPT2LMHeadModel
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            cfg = GPT2Config(vocab_size=64, n_positions=64, n_layer=2, n_head=2, n_embd=64)
            model = GPT2LMHeadModel(cfg).to(dev)          # local init, no Hub
            ids = torch.randint(0, 64, (2, 64), device=dev)
            out = model(input_ids=ids, labels=ids)
            out.loss.backward()
            return f"device={dev}, loss={out.loss.item():.3f}"
        check("offline GPT-2 build + fwd/bwd (no network)", model_fwd_bwd)

        # 5) HF Trainer 2 steps over a tiny IterableDataset ---------------
        def trainer_smoke():
            import torch
            from torch.utils.data import IterableDataset
            from transformers import GPT2Config, GPT2LMHeadModel, Trainer, TrainingArguments

            class Tiny(IterableDataset):
                def __iter__(self):
                    for _ in range(64):
                        t = torch.randint(0, 64, (32,), dtype=torch.long)
                        yield {"input_ids": t, "labels": t.clone()}

            cfg = GPT2Config(vocab_size=64, n_positions=32, n_layer=2, n_head=2, n_embd=64)
            args = TrainingArguments(
                output_dir=os.path.join(scratch, "trainer"), max_steps=2,
                per_device_train_batch_size=8, dataloader_num_workers=2,
                report_to="none", logging_steps=1, fp16=torch.cuda.is_available(),
                remove_unused_columns=False,
            )
            Trainer(model=GPT2LMHeadModel(cfg), args=args, train_dataset=Tiny()).train()
            return "2 steps, report_to=none (no logging hang)"
        check("HF Trainer 2-step offline smoke", trainer_smoke)

        # 6) resources + writable scratch ---------------------------------
        def resources():
            import torch
            cpu = os.cpu_count()
            mem = ""
            try:
                import psutil
                mem = f", RAM {psutil.virtual_memory().total / 1e9:.0f}GB"
            except Exception:
                pass
            gpu = "none"
            if torch.cuda.is_available():
                p = torch.cuda.get_device_properties(0)
                gpu = f"{p.name} {p.total_memory / 1e9:.0f}GB"
            probe = os.path.join(scratch, "w.txt")
            with open(probe, "w") as f:
                f.write("ok")
            return f"cpu={cpu}{mem}, gpu={gpu}, scratch writable"
        check("resources + writable scratch", resources)

    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if _FAILS:
        print(f"\nPREFLIGHT FAILED — {len(_FAILS)} check(s): {', '.join(_FAILS)}")
        return 1
    print("\nPREFLIGHT PASSED — node cleared for the pulse.seq pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
