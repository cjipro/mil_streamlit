"""Adapter ABC — every data source implements this.

Lifecycle:
  source_event -> deny-list check -> map_event() -> stamp envelope -> validate() -> emit

A subclass declares its contract_path. The base class loads the YAML, enforces
deny_fields on every incoming source event, and stamps the envelope. Subclasses
only need to implement map_event() for source-specific field mapping.

Filed under PULSE-87.
"""

from __future__ import annotations

import datetime as dt
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from pulse.schema import validate


class DenyListViolation(ValueError):
    """Raised when a source event carries a field listed in the adapter's deny_fields."""


class Adapter(ABC):
    """Base class for per-source adapters."""

    contract_path: Path  # subclass sets this — absolute path to its contract YAML

    def __init__(self) -> None:
        if not hasattr(self, "contract_path"):
            raise NotImplementedError(
                f"{type(self).__name__} must set `contract_path` class attribute"
            )
        self.contract = self._load_contract()
        self._deny_set = set(self.contract.get("deny_fields", []))

    def _load_contract(self) -> dict[str, Any]:
        with self.contract_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @abstractmethod
    def map_event(self, source_event: dict[str, Any]) -> dict[str, Any]:
        """Map a source-native event into canonical shape MINUS the envelope.

        Return a dict with keys: identity, context, event.
        The base class adds the envelope and validates.
        """

    def ingest(
        self,
        source_event: dict[str, Any],
        batch_hash: str,
    ) -> dict[str, Any]:
        """Public entry: validate deny-list, map, stamp envelope, return canonical event."""
        self._enforce_deny_list(source_event)
        canonical = self.map_event(source_event)
        canonical["envelope"] = self._stamp_envelope(source_event, batch_hash)
        validate(canonical)
        return canonical

    def _enforce_deny_list(self, source_event: Any) -> None:
        """Walk the source event recursively. Raise on any deny-listed key."""
        if not self._deny_set:
            return
        self._walk_deny(source_event, path="")

    def _walk_deny(self, obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in self._deny_set:
                    raise DenyListViolation(
                        f"deny-listed field '{k}' present at {path or '<root>'}"
                    )
                self._walk_deny(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self._walk_deny(v, f"{path}[{i}]")

    def _stamp_envelope(
        self,
        source_event: dict[str, Any],
        batch_hash: str,
    ) -> dict[str, Any]:
        source_event_id = self._resolve_source_event_id(source_event)
        return {
            "pulse_event_id": uuid.uuid4().hex,
            "source": self.contract["source_name"],
            "source_event_id": source_event_id,
            "ingest_ts": _iso_now(),
            "ingest_pipeline_version": self.contract.get(
                "adapter_version", "0.1.0"
            ),
            "ingest_batch_hash": batch_hash,
            "contract_version": self.contract.get("version", "0.0.0"),
        }

    def _resolve_source_event_id(self, source_event: dict[str, Any]) -> str:
        """Look up the source_event_id per the contract's field mapping."""
        mappings = self.contract.get("field_mappings", {})
        spec = mappings.get("source_event_id")
        if not spec or not isinstance(spec, str) or spec.startswith("<"):
            # placeholder ('<TBD ...>') or absent — caller hasn't defined it yet.
            return f"unmapped:{uuid.uuid4().hex[:8]}"
        return _lookup_path(source_event, spec)


def _iso_now() -> str:
    """ISO 8601 UTC with millisecond precision, matching schema timestamp regex."""
    now = dt.datetime.now(dt.timezone.utc)
    # Truncate microseconds to milliseconds.
    ms = now.microsecond // 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def _lookup_path(obj: dict[str, Any], dotted: str) -> Any:
    """Walk a dotted path through nested dicts: 'events.payload.error_code'."""
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(f"path {dotted!r} not found in source event at {part!r}")
        cur = cur[part]
    return cur
