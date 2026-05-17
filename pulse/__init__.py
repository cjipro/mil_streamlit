"""Pulse engine — canonical decision-intelligence runtime.

Filed under PULSE-87 (canonical engine schema, v1 design spine 2026-05-17).

Tree layout (relocates to cjipro/pulse-app when that repo is created):
    pulse/
      schema/        — canonical_schema.yaml + validate()
      adapters/      — Adapter ABC + per-source implementations
      contracts/     — per-source field-mapping YAMLs
      tests/         — round-trip + deny-list contract tests
"""

__version__ = "0.1.0"
