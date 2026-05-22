# FrictionBench v0.1 — spec

**Public, reproducible benchmark for journey-friction detection systems.**

Filed under PULSE-88. v0.1 spec; no scores published yet.

## What this is

A standardised test set + scoring rubric + submission protocol. Anyone can
submit a detection system; results are scored open-source and published
openly. **The benchmark is the strategic asset.** Publishing the spec
positions the team defining it as the category lead — the CASP / RetroCast /
InvestorBench pattern.

## CASP-style discipline: publish before publishing results

The spec, scoring rubric, and test-set release schedule ship **before** any
Pulse scores are published. CASP existed before AlphaFold won it; that
ordering is what made AlphaFold's win credible. Same discipline here.

If we publish "Pulse passes FrictionBench" without first publishing
FrictionBench, the benchmark looks ad-hoc and the result looks marketing.
Sequencing matters.

## Two architectural tracks (scored separately)

| Track | Eligibility | Notes |
|---|---|---|
| **Deterministic** | Zero LLM inference in the runtime path. Classical ML, statistics, rules, classical NLP, template synthesis permitted. | Pulse v1 competes here. |
| **LLM-Augmented** | LLM inference anywhere in the runtime path (detection, synthesis, or both). Must declare provider + model + version. | Separate leaderboard. |

Why: architectural tribes have different cost / latency / determinism profiles.
Mixing them on a single leaderboard conflates apples and oranges. Keeping them
separate lets the field compare them rigorously and lets buyers pick the
profile they need.

See [`leaderboard/tracks.yaml`](leaderboard/tracks.yaml) for membership rules.

## Headline numbers

- **Test cells:** 12 (3 active signatures × 4 v1 friction-target screens)
- **Sessions per cell:** 1000 (positive + negative + noise distractor mix)
- **Negative-screen sessions:** 754 (false-positive scoring substrate)
- **Test set version:** v0.1 (frozen; never compared across versions)
- **Submission cadence:** continuous; leaderboard refreshed nightly
- **Submissions per system per version:** one (cherry-picking forbidden)

See [`test_set/TEST_SET_SPEC.md`](test_set/TEST_SET_SPEC.md) for the full matrix.

## Scoring at a glance

Per-detection scoring on 6 axes (each scored independently, equal-weighted
average at v0.1):

1. Screen identification
2. Signature classification
3. Cohort identification
4. Cause identification
5. Confidence calibration
6. Time-to-detect

False-positive penalty: −0.05 per false positive on the 754 negative-screen
sessions, floored at 0.

See [`scoring/RUBRIC.md`](scoring/RUBRIC.md) for worked examples and
[`scoring/score.py`](scoring/score.py) for the open-source scoring script.

## Synthetic-to-real transfer evaluation

Each submission also reports accuracy on a curated set of N≥50
real-bank-derived labelled examples (anonymised, contract-controlled).

**The headline metric is the gap, not either number on its own.** Systems
with large synthetic-real gaps are flagged "synthetic-overfitted" on the
leaderboard. Per Eugene Yan / Shreya Shankar panel critique: the gap is the
load-bearing metric.

The real-labelled set is empty at v0.1 (contract-gated on the
work-machine side). The methodology is published regardless; submissions can
declare "real set unavailable" at v0.1 without being disqualified.

See [`transfer/TRANSFER_EVALUATION.md`](transfer/TRANSFER_EVALUATION.md).

## Submission

Submitters provide a Docker image exposing a `/detect` endpoint matching the
Pulse canonical event schema (PULSE-87). LIGO-style first-detection model:
detection emitted at the moment the signal first crosses threshold, scored
on time-to-detect × accuracy.

See [`submission/SUBMISSION_PROTOCOL.md`](submission/SUBMISSION_PROTOCOL.md).

## Governance

Public leaderboard, open-source scoring scripts, versioned test sets.
v1: CJI maintains the board. v2: MITRE-style independent body.

See [`leaderboard/GOVERNANCE.md`](leaderboard/GOVERNANCE.md).

## What v0.1 is NOT

Out of scope per ticket — these are separate work:

- The actual scoring harness (Docker streaming runner, leaderboard server, nightly refresh)
- The real-bank labelled set (contract-gated)
- Marketplace / commercial governance (v2)
- Multi-task expansion: 7 question classes × 18 journeys = 126 sub-benchmarks (v2)

## References

- ML-Ops panel consensus items 4, 6, 7 (2026-05-17)
- CASP, RetroCast, InvestorBench, FinBen — prior-art benchmark patterns
- AlphaFold "publish before results" sequencing pattern
- LIGO first-detection model
- TAQ App `inventory/journeys.yaml` (4 v1 friction targets)
- TAQ App `contracts/signatures.yaml` (3 active v1 signatures with cohort_evidence)
- PULSE-87 (canonical schema — `/detect` endpoint contract)
- PULSE-89 (lineage + audit chain — submissions stamp lineage on every detection)
