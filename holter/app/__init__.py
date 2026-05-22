"""Holter production front-end (HOL-65+).

Streamlit app on the proven work-machine stack (Streamlit + FastAPI + DuckDB).
Hosts the design-locked surfaces (HOL-3/4/6) by injecting their locked
HTML/CSS via ``components.html`` (sandboxed iframe → CSS isolation), rather
than rebuilding the bespoke layouts in native widgets. The static renderers
in ``holter/preview/`` remain the design spec + the shared block library.
"""
