"""
mil/chat/feedback.py — MIL-48.

Append-only feedback log for Ask CJI Pro. Partners on alpha record
thumbs-up / thumbs-down + an optional free-text note per answer.

Storage: mil/data/ask_feedback_log.jsonl — paired with audit log by trace_id.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent
_FEEDBACK_LOG = _MIL_ROOT / "data" / "ask_feedback_log.jsonl"

Verdict = Literal["up", "down", "refusal_wrong", "refusal_right"]


@dataclass
class FeedbackEntry:
    trace_id: str
    verdict: Verdict
    note: str = ""
    partner_id: Optional[str] = None
    timestamp: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def log(entry: FeedbackEntry) -> None:
    """Append one JSONL line to the feedback log."""
    try:
        _FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _FEEDBACK_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[feedback] write failed: %s", exc)


def summary() -> dict:
    """Return aggregate counts — useful for ops dashboard."""
    counts = {"up": 0, "down": 0, "refusal_wrong": 0, "refusal_right": 0}
    if not _FEEDBACK_LOG.exists():
        return {"total": 0, **counts}
    total = 0
    try:
        with _FEEDBACK_LOG.open(encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                verdict = entry.get("verdict")
                if verdict in counts:
                    counts[verdict] += 1
                total += 1
    except Exception as exc:
        logger.warning("[feedback] read failed: %s", exc)
    return {"total": total, **counts}
