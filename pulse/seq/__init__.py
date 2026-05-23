"""pulse.seq — behavioral-sequence model spike (PULSE-130).

Models customer journeys as token sequences and trains a small offline
Transformer on them. **Dev/research lane** — NOT the Pulse procurement runtime
(which stays classical-ML + statistics per the locked design). A Transformer is
non-LLM, so the non-LLM-runtime lock doesn't bar it; but it's a black-box deep
model, so productionising into the serving path would need a model-governance
story (explainability / validation / drift) that is out of scope for this spike.

Run order:
    py pulse/seq/preflight.py          # offline env gate — must pass on the node
    py pulse/seq/pipeline.py           # tokenize → stream → train
"""
