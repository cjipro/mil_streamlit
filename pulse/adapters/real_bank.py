"""real_bank adapter — production telemetry placeholder.

Skeleton-only at PULSE-87. Field mappings live on the work-machine side and
will be filled out separately. The deny_fields enforcement IS active and
load-bearing — that's the v1 PII boundary contract.

Filed under PULSE-87.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pulse.adapters.base import Adapter

_CONTRACT_PATH = Path(__file__).parent.parent / "contracts" / "real_bank_contract.yaml"


class RealBankAdapter(Adapter):
    """Production-side adapter. Skeleton at v1 — field mappings filled on work machine."""

    contract_path = _CONTRACT_PATH

    def map_event(self, source_event: dict[str, Any]) -> dict[str, Any]:
        # Detect placeholder mappings ('<TBD ...>'); refuse to silently emit garbage.
        mappings = self.contract["field_mappings"]
        placeholders = [
            k for k, v in mappings.items() if isinstance(v, str) and v.startswith("<")
        ]
        if placeholders:
            raise NotImplementedError(
                f"real_bank_contract.yaml field mappings are placeholders for: "
                f"{placeholders}. Fill them on the work-machine side before ingest."
            )

        # When mappings are filled, this looks the same as taq.py — left as a
        # follow-up so the implementation lives next to the real source vocabulary.
        raise NotImplementedError(
            "real_bank_adapter.map_event filled separately — see ticket Out of scope."
        )
