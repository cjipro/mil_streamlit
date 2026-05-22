"""Pulse scenarios — worked end-to-end product demonstrations.

Each scenario exercises the v0 engine spine (Diagnosis → Risk → Value →
CLARK-style Action) against a real bank question. Scenarios are
reproducible: scenario.yaml carries the input fixtures, run.py
orchestrates the engine calls, output is asserted by tests.

Currently houses:
- agentic_ai_placement/ — which app journeys should get AI assistant
  chat as the bank moves from digital→AI assistant (PULSE-106)
"""
