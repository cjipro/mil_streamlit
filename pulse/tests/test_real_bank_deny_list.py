"""Deny-list contract tests for the real_bank adapter.

These are the v1 PII boundary tests. Every field listed in
pulse/contracts/real_bank_contract.yaml `deny_fields` must raise
DenyListViolation when present in a source event — at any nesting depth.
"""

from __future__ import annotations

import pytest
import yaml

from pulse.adapters import DenyListViolation
from pulse.adapters.real_bank import RealBankAdapter, _CONTRACT_PATH


def _deny_fields() -> list[str]:
    with _CONTRACT_PATH.open("r", encoding="utf-8") as f:
        contract = yaml.safe_load(f)
    return contract["deny_fields"]


@pytest.mark.parametrize("denied_field", _deny_fields())
def test_top_level_denied_field_raises(denied_field: str) -> None:
    adapter = RealBankAdapter()
    source = {denied_field: "anything"}
    with pytest.raises(DenyListViolation, match=denied_field):
        adapter.ingest(source, batch_hash="f" * 64)


@pytest.mark.parametrize("denied_field", _deny_fields())
def test_nested_in_payload_denied_field_raises(denied_field: str) -> None:
    adapter = RealBankAdapter()
    source = {
        "events": {
            "session_id": "sess-1",
            "payload": {denied_field: "leaked"},
        },
    }
    with pytest.raises(DenyListViolation, match=denied_field):
        adapter.ingest(source, batch_hash="g" * 64)


@pytest.mark.parametrize("denied_field", _deny_fields())
def test_inside_list_denied_field_raises(denied_field: str) -> None:
    adapter = RealBankAdapter()
    source = {"batch": [{"ok": 1}, {denied_field: "leaked"}]}
    with pytest.raises(DenyListViolation, match=denied_field):
        adapter.ingest(source, batch_hash="h" * 64)


def test_clean_source_event_does_not_raise_deny_list() -> None:
    """A clean event passes the deny-list check and hits map_event() —
    which still raises NotImplementedError because mappings are placeholders.
    The point is: deny-list runs FIRST and lets clean events through."""
    adapter = RealBankAdapter()
    source = {"events": {"session_id": "sess-1", "payload": {"duration_ms": 100}}}
    with pytest.raises(NotImplementedError, match="placeholders"):
        adapter.ingest(source, batch_hash="i" * 64)


def test_deny_fields_complete_per_ticket_spec() -> None:
    """Per PULSE-87 ticket — these 10 fields must all be in the deny-list."""
    expected = {
        "customer_name",
        "account_number",
        "sort_code",
        "email",
        "phone",
        "postcode_full",
        "dob",
        "balance",
        "transaction_amount",
        "merchant_name",
    }
    assert set(_deny_fields()) >= expected, (
        f"missing deny-list entries: {expected - set(_deny_fields())}"
    )
