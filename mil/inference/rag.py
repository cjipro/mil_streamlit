"""
mil/inference/rag.py

CHRONICLE RAG layer — finds the best historical pattern match for a signal cluster.
Extracted from mil_agent.py for independent testability.

Primary:  all-MiniLM-L6-v2 cosine similarity (sentence-transformers)
Fallback: keyword overlap (when sentence-transformers unavailable)

Similarity threshold: 0.30 (cosine). Keyword overlap threshold: 0.40.
Rationale documented in thresholds.yaml — cosine 0.30 ≈ related domain.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def _sim_threshold() -> float:
    try:
        from mil.config.thresholds import T as _T
    except ImportError:
        from config.thresholds import T as _T
    return float(_T("inference.sim_threshold"))

# Module-level cache — loaded once per process, shared across calls
_EMBED_MODEL = None          # SentenceTransformer or False when unavailable
_CHR_EMBED_CACHE: dict = {}  # chronicle_id -> L2-normalised embedding vector


def _load_embed_model():
    """Load all-MiniLM-L6-v2 once; return False if sentence-transformers not installed."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            from mil.config.retrieval_models import INFERENCE_EMBEDDING_MODEL, EMBEDDING_DEVICE
            # device="cpu" pinned 2026-05-24. The model is tiny, so CPU cost is
            # negligible — but this in-process GPU encode was the operation in flight at
            # 3 mid-pipeline machine crashes (BSOD 0x116 VIDEO_TDR_ERROR on the RTX 5070 Ti
            # Laptop: 28/04, 05/05, 12/05). Pinning to CPU removes the GPU as a crash
            # trigger for the daily run. See memory project_gpu_tdr_crashes.md.
            # MIL-183: model name centralised in retrieval_models. Still MiniLM here
            # (NOT BGE like the chat retriever) — the 0.30 sim_threshold is calibrated
            # to MiniLM's cosine distribution; swapping needs recalibration (follow-up).
            _EMBED_MODEL = SentenceTransformer(INFERENCE_EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
            logger.info("[rag] Loaded sentence-transformer: %s (device=%s)",
                        INFERENCE_EMBEDDING_MODEL, EMBEDDING_DEVICE)
        except Exception as exc:
            logger.warning("[rag] sentence-transformers unavailable (%s) — using keyword overlap", exc)
            _EMBED_MODEL = False
    return _EMBED_MODEL


def _chr_vec(entry: dict, model):
    """Return cached L2-normalised embedding for a CHRONICLE entry."""
    cid = entry["chronicle_id"]
    if cid not in _CHR_EMBED_CACHE:
        text = entry["pattern_description"] + " " + " ".join(entry["pattern_keywords"])
        _CHR_EMBED_CACHE[cid] = model.encode(text, normalize_embeddings=True)
    return _CHR_EMBED_CACHE[cid]


def _keyword_overlap(signal_keywords: list[str], chronicle_keywords: list[str]) -> float:
    """Fallback similarity: keyword overlap [0.0, 1.0]."""
    if not signal_keywords or not chronicle_keywords:
        return 0.0
    sig_lower   = list(dict.fromkeys(k.lower() for k in signal_keywords))
    chron_lower = [k.lower() for k in chronicle_keywords]
    hits = 0
    for sk in sig_lower:
        for ck in chron_lower:
            if sk in ck or ck in sk:
                hits += 1
                break
    return min(hits / len(chronicle_keywords), 1.0)


def find_best_chronicle_match(
    journey_id: Optional[str],
    signal_keywords: list[str],
    chronicle_entries: list[dict],
) -> tuple[Optional[dict], float]:
    """
    Find the highest-similarity CHRONICLE entry for a given journey_id + keywords.
    Only considers inference_approved=True entries.

    Returns (best_entry_or_None, sim_hist_score [0.0, 1.0]).
    Returns (None, 0.0) if no approved match — finding will be UNANCHORED.
    """
    model = _load_embed_model()

    signal_vec = None
    if model:
        signal_text = " ".join(dict.fromkeys(k.lower() for k in signal_keywords if k))[:512]
        try:
            signal_vec = model.encode(signal_text, normalize_embeddings=True)
        except Exception as exc:
            logger.warning("[rag] embed encode failed (%s) — falling back to keyword overlap", exc)

    best_entry = None
    best_score = 0.0

    for entry in chronicle_entries:
        if not entry.get("inference_approved"):
            continue
        if journey_id and journey_id not in entry.get("journey_tags", []):
            continue

        if signal_vec is not None:
            try:
                import numpy as np
                score = float(np.dot(signal_vec, _chr_vec(entry, model)))
            except Exception:
                score = _keyword_overlap(signal_keywords, entry["pattern_keywords"])
        else:
            score = _keyword_overlap(signal_keywords, entry["pattern_keywords"])

        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry, round(best_score, 4)
