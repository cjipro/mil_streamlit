"""
jax_synthetic_filter.py — Jax Signal Authenticity Filter.

Filters coordinated bots, fake reviews, narrative drift,
like farming, spam replies, and bot view inflation.

Input:  raw signal dict (from any source)
Output: signal dict with jax_flags[] added and jax_clean: bool

Twitter-specific checks are placeholder — ready to activate
when Twitter source moves from STUB to ACTIVE.

Zero Entanglement: no imports from internal modules.
"""
import re
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────
MIN_REVIEW_LENGTH = 10
MAX_REPEATED_PHRASE_RATIO = 0.4      # fraction of text that is repeated phrases
COORDINATED_TIMESTAMP_WINDOW = 300  # seconds — posts within 5min are suspicious
COORDINATED_CLUSTER_SIZE = 5        # >= N posts in window = coordinated flag

# YouTube specific
LIKE_FARMING_RATIO = 50.0
BOT_VIEW_RATIO = 0.001

# Reddit specific
KARMA_THRESHOLD = 10                 # very low karma = new/throwaway account


def _flag_short_content(text: str) -> bool:
    """Reviews with almost no content are suspicious."""
    return len(text.strip()) < MIN_REVIEW_LENGTH


def _flag_repeated_phrases(text: str) -> bool:
    """Detect copy-paste reviews — same phrase appears many times."""
    if not text:
        return False
    words = text.lower().split()
    if len(words) < 5:
        return False
    # Check for repeated trigrams
    trigrams = [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
    unique_ratio = len(set(trigrams)) / len(trigrams)
    return unique_ratio < (1 - MAX_REPEATED_PHRASE_RATIO)


def _flag_like_farming_youtube(item: dict) -> bool:
    likes = item.get("like_count", 0)
    comments = item.get("comment_count", 0)
    if comments == 0:
        return False
    return (likes / comments) > LIKE_FARMING_RATIO


def _flag_bot_view_inflation_youtube(item: dict) -> bool:
    views = item.get("view_count", 0)
    comments = item.get("comment_count", 0)
    if views < 1000 or comments == 0:
        return False
    return (comments / views) < BOT_VIEW_RATIO


def apply_jax_filter(signal: dict) -> dict:
    """
    Apply Jax filter to a signal dict. Returns the signal dict
    with jax_flags[] populated and jax_clean set.

    signal must have keys: source, raw_data (dict)
    """
    signal = dict(signal)  # don't mutate input
    if "jax_flags" not in signal:
        signal["jax_flags"] = []

    source = signal.get("source", "")
    raw = signal.get("raw_data", {})

    # ── Universal checks ──────────────────────────────────────
    text_fields = ["review", "content", "body", "review_text", "comment_text", "summary"]
    text = " ".join(str(raw.get(f, "")) for f in text_fields if raw.get(f))

    if _flag_short_content(text) and text:
        signal["jax_flags"].append("JAX_SHORT_CONTENT")

    if _flag_repeated_phrases(text):
        signal["jax_flags"].append("JAX_REPEATED_PHRASES")

    # ── App Store / Google Play / Trustpilot ──────────────────
    if source in ("app_store", "google_play", "trustpilot"):
        rating = raw.get("rating", 3)
        if rating == 1 and len(text.strip()) < 20:
            signal["jax_flags"].append("JAX_DRIVE_BY_ONE_STAR")

    # ── Reddit ────────────────────────────────────────────────
    if source == "reddit":
        score = raw.get("score", 0)
        if score < 0:
            signal["jax_flags"].append("JAX_DOWNVOTED_POST")

    # ── YouTube ───────────────────────────────────────────────
    if source == "youtube":
        if _flag_like_farming_youtube(raw):
            signal["jax_flags"].append("JAX_LIKE_FARMING")
        if _flag_bot_view_inflation_youtube(raw):
            signal["jax_flags"].append("JAX_BOT_VIEW_INFLATION")

    # ── Twitter — placeholder ─────────────────────────────────
    # Twitter-specific Jax checks go here when source activates.
    # Planned checks:
    #   JAX_COORDINATED_CAMPAIGN — clustered timestamps + identical phrasing
    #   JAX_ASTROTURF — new accounts posting identical narrative
    #   JAX_TRENDING_MANIPULATION — sudden spike with no organic precursor

    signal["jax_clean"] = len(signal["jax_flags"]) == 0
    return signal


def apply_jax_filter_batch(signals: list[dict]) -> list[dict]:
    """Apply Jax filter to a list of signals. Returns filtered list."""
    return [apply_jax_filter(s) for s in signals]
