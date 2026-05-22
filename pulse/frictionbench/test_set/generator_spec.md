# Test-set generator — spec

**Filed under PULSE-88.**

## Why this exists

Reproducibility is the load-bearing benchmark property. A submitter who
can't regenerate the test set can't audit their score. We commit to:

1. The exact synthetic event stream for v0.1 is byte-identical across
   any machine that runs the generator with the v0.1 seed.
2. The generator is open-source.
3. The ground-truth file is shipped alongside the events (no separate
   privileged access).

This is the CASP / MLPerf discipline.

## Source of truth

The generator lives in TAQ App (`taq-app/scripts/frictionbench/`,
to land under TAQ-1 + a FrictionBench-specific sub-ticket). TAQ already
holds the event vocabulary (`contracts/events.yaml`), the journey
taxonomy (`inventory/journeys.yaml`), and the signature schemas
(`contracts/signatures.yaml`). The generator stitches those into the
12-cell × 1000-session synthetic corpus.

Pulse does NOT re-implement the generator. The contract is:

- TAQ ships the generator and the released bundle (events + ground truth)
- Pulse / FrictionBench depends on the released bundle
- Bundle version + SHA-256 pinned in the FrictionBench leaderboard

## Reproducibility seed

Each FrictionBench version carries a single seed (`v0.1` → `SEED=20260517`).
Generator runs with that seed produce byte-identical output. Submitters
can verify by running the generator themselves.

## Bundle contents

The released v0.1 bundle is a tar.gz containing:

```
frictionbench-v0.1/
  README.md                 — version, seed, SHA-256 manifest
  events.jsonl              — 12,754 sessions worth of TAQ events, in canonical Pulse shape
  ground_truth.jsonl        — 12,754 records matching ground_truth_schema.yaml
  negative_screens.jsonl    — events from the 754 non-target-screen sessions
  cell_index.yaml           — cell_id → session_id list mapping
  manifest.yaml             — bundle version, seed, SHA-256 of each file
```

Submitters consume only `events.jsonl` and `negative_screens.jsonl` at
detection time. `ground_truth.jsonl` and `cell_index.yaml` are used by the
scoring script after detection completes.

## Versioning + immutability

Once published, a bundle is **never modified**. Bug fixes producing a
different bundle → version bump (v0.1.1). Every prior leaderboard score
is re-scored against the new bundle automatically; submitters do not
re-submit unless they want to.

The bundle is content-addressed by SHA-256. Any tooling that needs to know
"which v0.1 did this score come from" can reference the manifest hash.

## Generator code constraints

Stated here so the TAQ-side generator implementation honours them:

- **No PII.** Synthetic only. All names / emails / phone numbers / account
  numbers are template-generated from public-domain word lists.
- **No real-bank-derived patterns.** The generator's friction patterns are
  derived from public CASP-style hypotheses + TAQ's own internal
  `cohort_evidence` numbers, not from any real-bank telemetry.
- **Deterministic.** Same seed → same bytes. No wall-clock, no machine
  ID, no environment dependency.
- **License: Apache-2.0.** The bundle, the generator, and the ground truth
  are all open source. Hosted at `frictionbench.org` (TBD) or `cjipro/frictionbench`.
