"""
mil/chat/audit.py — MIL-46.

Append-only query audit log. One JSONL line per /ask query.

Persisted to mil/data/ask_audit_log.jsonl — never rewritten.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MIL_ROOT  = Path(__file__).parent.parent
_AUDIT_LOG = _MIL_ROOT / "data" / "ask_audit_log.jsonl"


@dataclass
class AuditEntry:
    trace_id: str
    timestamp: str = ""
    query: str = ""
    intent: str = ""
    retrievers_hit: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: str = ""
    refusal_class: str = ""
    model_used: str = ""
    cache_hit: bool = False
    latency_ms: int = 0
    partner_id: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def log(entry: AuditEntry) -> None:
    """Append one JSONL line to the audit log. Never rewrites."""
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[audit] write failed: %s", exc)
