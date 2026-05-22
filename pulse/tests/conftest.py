"""Shared test fixtures for the pulse engine suite.

Isolation for the pipeline-derived friction mart: `build_pipeline_session_friction`
and `run_pipeline` write the shared fixed-path `session_friction_pipeline.parquet`,
which `read.py` prefers over the detection-corpus fixture. Remove it around every
test so a test that builds it cannot bleed into the corpus-mart serving tests (and
so a stale file left by a manual pipeline run cannot either).
"""

from __future__ import annotations

import pytest

from pulse.serving.marts import PIPELINE_SESSION_FRICTION_PARQUET


@pytest.fixture(autouse=True)
def _isolate_pipeline_friction_mart():
    PIPELINE_SESSION_FRICTION_PARQUET.unlink(missing_ok=True)
    yield
    PIPELINE_SESSION_FRICTION_PARQUET.unlink(missing_ok=True)
