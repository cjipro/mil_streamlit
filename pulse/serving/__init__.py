"""Pulse serving layer (PULSE-127).

The read side that feeds the front-end. Materialises a per-session friction
mart by running the detection runtime (PULSE-126) over the taq-synthetic
corpus, writes it to Parquet, and exposes DuckDB read functions the FastAPI
Platform API (HOL-5) serves to the Streamlit surfaces (HOL-65+).

Boundary: synthetic taq corpus only — generated in-process from the detection
harness. The real_bank corpus runs on the work machine via the crossing
contract and never enters this repo (only this read API + the taq path do).
"""
