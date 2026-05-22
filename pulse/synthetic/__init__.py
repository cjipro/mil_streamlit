"""Synthetic data generation for the Pulse pipeline.

Self-contained synthetic source generators that feed the MA_D → MA_S → marts
pipeline with zero dependency on the TAQ App or real-bank access. The output is
the same canonical Pulse event shape the engine reads everywhere else, so the
pipeline exercises the real adapter + schema path.

Owned by while-sleeping (PULSE-28; engine relocated under PULSE-128).
"""
