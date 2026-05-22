"""Shared test fixtures for the pulse engine suite.

Isolation for the pipeline-derived friction mart: `build_pipeline_session_friction`
and `run_pipeline` write the shared fixed-path `session_friction_pipeline.parquet`,
which `read.py` prefers over the detection-corpus fixture. Remove it around every
test so a test that builds it cannot bleed into the corpus-mart serving tests (and
so a stale file left by a manual pipeline run cannot either).
"""

from __future__ import annotations

import pytest

from pulse.serving.marts import MARTS_DIR, PIPELINE_SESSION_FRICTION_PARQUET

# Shared fixed-path derived marts that a test may build and read.py prefers —
# clean them around every test so they can't bleed across tests.
_DERIVED_MARTS = [
    PIPELINE_SESSION_FRICTION_PARQUET,
    MARTS_DIR / "decisions.parquet",
    MARTS_DIR / "decisions_lineage.jsonl",
    MARTS_DIR / "chronicle_candidates.jsonl",
]


@pytest.fixture(autouse=True)
def _isolate_pipeline_marts():
    for p in _DERIVED_MARTS:
        p.unlink(missing_ok=True)
    yield
    for p in _DERIVED_MARTS:
        p.unlink(missing_ok=True)
