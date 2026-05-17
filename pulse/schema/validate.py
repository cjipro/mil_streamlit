"""Pulse canonical schema loader + validator.

`validate(event)` checks a candidate canonical event dict against
canonical_schema.yaml. Raises SchemaValidationError on any shape/type mismatch.

Pure stdlib + PyYAML (already a project dependency). No jsonschema dep —
the schema YAML is intentionally narrow and the rules are explicit here so
the validation logic itself stays readable.

Filed under PULSE-87.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_PATH = Path(__file__).parent / "canonical_schema.yaml"

# ISO 8601 UTC, millisecond precision. Examples:
#   2026-05-17T14:30:00.123Z
#   2026-05-17T14:30:00.123+00:00
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$"
)


class SchemaValidationError(ValueError):
    """Raised when a candidate event does not match canonical_schema.yaml."""


@functools.lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Load and cache canonical_schema.yaml."""
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate(event: dict[str, Any]) -> None:
    """Validate a candidate canonical event. Raises SchemaValidationError on mismatch."""
    schema = load_schema()
    spec = schema["canonical_event"]

    if not isinstance(event, dict):
        raise SchemaValidationError(f"event must be dict, got {type(event).__name__}")

    expected_sections = set(spec.keys())
    actual_sections = set(event.keys())
    if missing := expected_sections - actual_sections:
        raise SchemaValidationError(f"missing top-level sections: {sorted(missing)}")
    if extra := actual_sections - expected_sections:
        raise SchemaValidationError(f"unexpected top-level sections: {sorted(extra)}")

    for section_name, field_specs in spec.items():
        section = event[section_name]
        if not isinstance(section, dict):
            raise SchemaValidationError(
                f"section '{section_name}' must be dict, got {type(section).__name__}"
            )
        _validate_section(section_name, section, field_specs)


def _validate_section(
    section_name: str, section: dict[str, Any], field_specs: dict[str, Any]
) -> None:
    """Validate one section (envelope / identity / context / event) against its field specs."""
    for field_name, field_spec in field_specs.items():
        required = field_spec.get("required", True)
        present = field_name in section

        if not present:
            if required:
                raise SchemaValidationError(
                    f"{section_name}.{field_name}: required field missing"
                )
            continue

        value = section[field_name]
        _check_type(f"{section_name}.{field_name}", value, field_spec)

    if extra := set(section.keys()) - set(field_specs.keys()):
        raise SchemaValidationError(
            f"section '{section_name}': unexpected fields {sorted(extra)}"
        )


def _check_type(path: str, value: Any, spec: dict[str, Any]) -> None:
    """Check one field against its declared type."""
    expected = spec["type"]

    if expected == "string":
        if not isinstance(value, str):
            raise SchemaValidationError(
                f"{path}: expected string, got {type(value).__name__}"
            )
    elif expected == "integer":
        # bool is a subclass of int in Python — exclude it explicitly.
        if not isinstance(value, int) or isinstance(value, bool):
            raise SchemaValidationError(
                f"{path}: expected integer, got {type(value).__name__}"
            )
    elif expected == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaValidationError(
                f"{path}: expected float, got {type(value).__name__}"
            )
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise SchemaValidationError(
                f"{path}: expected boolean, got {type(value).__name__}"
            )
    elif expected == "timestamp":
        if not isinstance(value, str) or not _ISO_TIMESTAMP_RE.match(value):
            raise SchemaValidationError(
                f"{path}: expected ISO 8601 UTC timestamp, got {value!r}"
            )
    elif expected == "enum":
        allowed = spec["values"]
        if value not in allowed:
            raise SchemaValidationError(
                f"{path}: value {value!r} not in allowed enum {allowed}"
            )
    elif expected == "list[string]":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SchemaValidationError(
                f"{path}: expected list of strings, got {value!r}"
            )
    elif expected == "object":
        if not isinstance(value, dict):
            raise SchemaValidationError(
                f"{path}: expected object/dict, got {type(value).__name__}"
            )
    else:
        raise SchemaValidationError(
            f"{path}: unknown type {expected!r} in schema (validator gap)"
        )
