"""Import-time safety gate.

Cerno is classical ML + statistics + SQL only. Deep learning and LLM
libraries must never appear in the runtime path. This module enforces
that contract by scanning sys.modules at import time.
"""

from __future__ import annotations

import sys

# Banned at import-time. These are the deep-learning + LLM API libraries
# that would break the procurement-passable / no-LLM-at-runtime contract.
# Outbound HTTP libs (requests/httpx/urllib3) are not blocked here because
# the test runner or its plugins may load them transitively; CI enforces
# the broader no-network rule via the .gitlab-ci.yml job.
BANNED: tuple[str, ...] = (
    "torch",
    "transformers",
    "sentence_transformers",
    "openai",
    "anthropic",
)


class SafetyViolation(ImportError):
    """Raised when assert_safe() detects a banned module in sys.modules."""


def assert_safe() -> None:
    """Refuse to proceed if any banned module is loaded.

    Called automatically from cerno/__init__.py at import time.
    Operators can call again at any point to re-verify.
    """
    found = [name for name in BANNED if name in sys.modules]
    if found:
        raise SafetyViolation(
            "cerno safety gate: banned modules present in sys.modules: "
            f"{found}. Cerno is a classical-ML/SQL engine; deep-learning + "
            "LLM libs are not allowed in the runtime path."
        )
