"""
mil/config/retrieval_models.py — MIL-182 / MIL-183.

Single source of truth for the embedding + reranker model names used across
the retrieval stack. Previously `all-MiniLM-L6-v2` was hardcoded in two places
(mil/chat/retrievers/embedding.py and mil/inference/rag.py); centralise here.

Transition note (MIL-183): the chat retriever moved to BGE-small (2026 CPU-
friendly, materially better retrieval than the 2021-era MiniLM). The INFERENCE
embedding (rag.py, CHRONICLE matching) is deliberately STILL on MiniLM — its
cosine `sim_threshold` (0.30) is calibrated to MiniLM's distribution and a
model swap there re-anchors live findings, so it needs threshold recalibration
+ CHR-match-distribution validation before swapping (tracked as an MIL-183
follow-up). Different values during the transition is intentional, not drift.

All models run via the already-approved `sentence-transformers` package
(APPROVED_LIBRARIES.md) on CPU — the CPU pin is load-bearing (the in-process
GPU encode was the op in flight at the 0x116 VIDEO_TDR_ERROR BSODs; see memory
project_gpu_tdr_crashes.md).
"""
from __future__ import annotations

# Ask CJI Pro dense retriever (mil/chat/retrievers/embedding.py)
CHAT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# CHRONICLE RAG matching (mil/inference/rag.py) — swap deferred, see module note
INFERENCE_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Cross-encoder reranker for the Ask CJI Pro pipeline (mil/chat/rerank.py)
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"

# All sentence-transformers loads pin to CPU (TDR-crash mitigation).
EMBEDDING_DEVICE = "cpu"
