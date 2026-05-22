"""Holter — the bundled UI for CJI Pulse.

Holter is the *face* of Pulse, not a parallel system. Engine logic lives
in `pulse/`; every Holter surface consumes Pulse via its public API and
must not reimplement engine behaviour.

Surfaces (per HOL-1 identity lock, 2026-05-17):

- workspace/ — Surface 2: Investigation Workspace (Panel + HoloViz). HOL-3.
- home/      — Surface 1: Pulse Home (Streamlit). HOL-4.
- monitor/   — Surface 3: Pulse Monitor (Panel + Bokeh). HOL-7 (gated).
- mlops/     — Surface 4: MLOps Console (Streamlit + FastAPI). HOL-6.
- api/       — Surface 5: Pulse Platform API (FastAPI + Pydantic). HOL-5.
- shared/    — cross-surface components, theme, auth.

See `~/.claude/plans/adaptive-mapping-popcorn.md` for the canonical plan.
"""
