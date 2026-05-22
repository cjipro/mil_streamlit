"""TAQ adapter — maps TAQ synthetic telemetry into the Pulse canonical schema.

Reads pulse/contracts/taq_contract.yaml for field mappings.
Looks up journey_category via pulse/contracts/journey_taxonomy.yaml.

Filed under PULSE-87.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from pulse.adapters.base import Adapter, _lookup_path

_CONTRACT_PATH = Path(__file__).parent.parent / "contracts" / "taq_contract.yaml"
_TAXONOMY_PATH = Path(__file__).parent.parent / "contracts" / "journey_taxonomy.yaml"


@functools.lru_cache(maxsize=1)
def _journey_taxonomy() -> dict[str, str]:
    with _TAXONOMY_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["journeys"]


class TAQAdapter(Adapter):
    """Maps TAQ App events into canonical Pulse events."""

    contract_path = _CONTRACT_PATH

    def map_event(self, source_event: dict[str, Any]) -> dict[str, Any]:
        mappings = self.contract["field_mappings"]

        journey_id = _lookup_path(source_event, mappings["journey_id"])
        cohort_tags = self._optional_lookup(source_event, mappings["cohort_tags"])

        return {
            "identity": {
                "session_id": _lookup_path(source_event, mappings["session_id"]),
                "subject_id": _lookup_path(source_event, mappings["subject_id"]),
                "cohort_tags": cohort_tags if cohort_tags is not None else [],
            },
            "context": {
                "journey_id": journey_id,
                "journey_category": _derive_journey_category(journey_id),
                "screen_id": _lookup_path(source_event, mappings["screen_id"]),
                "sequence_no": _lookup_path(source_event, mappings["sequence_no"]),
            },
            "event": {
                "event_type": _lookup_path(source_event, mappings["event_type"]),
                "event_ts": _lookup_path(source_event, mappings["event_ts"]),
                "payload": _lookup_path(source_event, mappings["payload"]),
            },
        }

    @staticmethod
    def _optional_lookup(source_event: dict[str, Any], dotted: str) -> Any:
        try:
            return _lookup_path(source_event, dotted)
        except KeyError:
            return None


def _derive_journey_category(journey_id: str) -> str:
    taxonomy = _journey_taxonomy()
    if journey_id not in taxonomy:
        raise ValueError(
            f"journey_id {journey_id!r} not in pulse/contracts/journey_taxonomy.yaml"
        )
    return taxonomy[journey_id]
