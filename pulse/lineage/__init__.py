"""Pulse lineage chain — append-only hash-chained audit log.

Mirrors MIL-65's auth audit pattern (TypeScript, in production since 2026-04-25)
in Python for the Pulse engine. Same guarantees:
  - Append-only
  - Each row carries the SHA-256 of all prior rows transitively (via prev_row_hash)
  - Tampering with any row breaks every subsequent row hash
  - Verifier reads forward, recomputes, asserts integrity

Filed under PULSE-89.
"""

from pulse.lineage.canonical import canonical_json, sha256_hex
from pulse.lineage.chain import GENESIS, hash_row, recompute_row_hash
from pulse.lineage.verifier import VerifyReport, Violation, verify_chain

__all__ = [
    "GENESIS",
    "VerifyReport",
    "Violation",
    "canonical_json",
    "hash_row",
    "recompute_row_hash",
    "sha256_hex",
    "verify_chain",
]
