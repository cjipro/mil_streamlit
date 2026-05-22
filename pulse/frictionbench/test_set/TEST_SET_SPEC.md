# FrictionBench v0.1 — test set spec

**Filed under PULSE-88.**

The v0.1 test set is the 12-cell matrix derived from TAQ App. Frozen at this
version; never compared across versions. Future versions (v0.2, v0.3, ...)
expand cells, expand signatures, expand screens.

## Matrix

3 active v1 signatures × 4 v1 friction-target screens = 12 cells. Each cell
gets 1000 synthetic sessions.

| # | Friction-target screen | Active signature | Ground truth |
|---|---|---|---|
|  1 | `loans.apply.step3` | `dwell_after_error` | engineered positive |
|  2 | `loans.apply.step3` | `multi_back_press` | engineered positive |
|  3 | `loans.apply.step3` | `abandon_before_submit` | engineered positive |
|  4 | `international.beneficiary.setup` | `dwell_after_error` | engineered positive |
|  5 | `international.beneficiary.setup` | `multi_back_press` | engineered positive |
|  6 | `international.beneficiary.setup` | `abandon_before_submit` | engineered positive |
|  7 | `cards.credit.apply.eligibility` | `dwell_after_error` | engineered positive |
|  8 | `cards.credit.apply.eligibility` | `multi_back_press` | engineered positive |
|  9 | `cards.credit.apply.eligibility` | `abandon_before_submit` | engineered positive |
| 10 | `investments.premier.portfolio.overview` | `dwell_after_error` | **engineered NEGATIVE** (long dwell = interest, not friction) |
| 11 | `investments.premier.portfolio.overview` | `multi_back_press` | engineered positive (real friction) |
| 12 | `investments.premier.portfolio.overview` | `abandon_before_submit` | engineered positive (real friction) |

Cell 10 is the load-bearing negative. Long dwell on a Premier portfolio is
attention, not friction; a system that flags it as friction is **misreading
behaviour**. This is the case TAQ inventory flags as the v1 behavioural-noise
test (per `taq-app/inventory/journeys.yaml#investments`).

## Per-cell session mix

Each cell contains 1000 sessions split:

- **650 positive examples** — sessions where the signature should fire
  (or in cell 10, sessions where long dwell happens for interest reasons)
- **250 negative examples** — sessions on the same screen where the
  signature should NOT fire (close-call cases, threshold-adjacent)
- **100 noise distractor sessions** — sessions on the same screen with
  unrelated friction patterns (other signatures present, target signature
  absent)

Mix ratios held constant across cells for comparability.

## Negative-screen sessions

Separate from the 12 cells: 754 sessions across the 754 other screens in the
TAQ inventory (`journeys.yaml#totals.estimated_screen_total` minus the 4 v1
friction targets). Used exclusively for false-positive scoring; the detector
should fire on ~zero of these.

Per the v1 success criterion (CLAUDE.md Pulse Design Direction lock):
**detect on the 4 v1 friction targets, produce ~zero false positives on the
754 other screens.** That's what the test set operationalises.

## Ground truth

Each session ships with a ground-truth record matching
[`ground_truth_schema.yaml`](ground_truth_schema.yaml). At v0.1 the schema is:

- `session_id` — synthetic session UUID
- `cell_id` — 1-12 for the active cell, or `negative_screens` for the
  non-target-screen pool
- `screen_id` — TAQ screen identifier
- `signature_id` — active signature for the cell (or `none` for negatives)
- `should_fire` — true if a correct detector would flag this session
- `root_cause` — template / release / timing / cohort (the cause label the
  detector should converge on)
- `cohort_tags` — cohort tags the detector should identify in its result
- `confidence_target` — calibrated probability the detector should report
  if its model is well-calibrated (used by the Brier score axis)

## Reproducibility

The test set is **generatable from TAQ App** via the synthetic-data harness
(see [`generator_spec.md`](generator_spec.md)). Anyone with TAQ App access
can regenerate the test set byte-identically given the same seed.

The published frozen v0.1 corpus + ground-truth file + generator seed are
all shipped together. No part of the corpus is private.

## Version freeze

v0.1 is frozen. Bug fixes that change ground-truth labels require a v0.1.1
bump and a re-score of every submission. Cells and counts and ratios are
locked at the version boundary.

Future versions expand the matrix:

- **v0.2** — adds 2 more v1 signatures (TAQ App `signatures.yaml` ratifies them)
- **v0.3** — adds 4 more friction-target screens (TAQ inventory expands them)
- **v1.0** — locks the v1 12-cell + extensions matrix for the year
- **v2.0** — multi-task expansion (7 question classes × 18 journeys)

The version-freeze discipline is the same as MLPerf and CASP: any leaderboard
score is meaningful only against a single version's frozen substrate.
