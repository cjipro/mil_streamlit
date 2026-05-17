# FrictionBench v0.1 — leaderboard governance

**Filed under PULSE-88.**

## Who runs the leaderboard

**v1: CJI.** The benchmark org is CJI for the first iteration. The leaderboard
is hosted at `frictionbench.org` (TBD — placeholder pending domain decision)
and run from `cjipro/frictionbench` (or equivalent public repo).

**v2: MITRE-style independent body.** Once 5+ external submissions land or
12 months pass (whichever first), governance migrates to an independent
body. CASP precedent: the benchmark earns credibility only when an
independent body owns the leaderboard. CJI continues to submit but cannot
score itself.

## Submission verification

Every submission is verified before its score appears on the leaderboard:

1. **Image pull.** Harness pulls the submitted Docker image from the public
   registry. Failure to pull = submission rejected with reason.
2. **Manifest validation.** Manifest YAML is validated against
   [`submission_manifest_schema.yaml`](../submission/submission_manifest_schema.yaml).
   Schema failures rejected.
3. **Determinism check.** Image runs twice over the same v0.1 bundle.
   >0.1% session disagreement = rejection.
4. **Track membership check.** For `deterministic` track, runtime
   dependency scan rejects images linking against known LLM SDKs.
5. **Score computation.** Open-source scoring script ([`scoring/score.py`](../scoring/score.py))
   runs on the detection emissions vs ground truth. Same code anyone can
   re-run locally.

A submission passing all 5 checks lands on the leaderboard within 24 hours.

## Verification re-runs

Any third party can re-score any submission by:

1. Pulling the same v0.1 bundle (content-addressed by SHA-256)
2. Pulling the submitter's Docker image
3. Running the open-source scoring script

A reproducibility disagreement is grounds for re-investigation, not
immediate disqualification — the harness runs the submission a third time
to confirm.

## Versioning + immutability

- **Test set frozen per benchmark version.** v0.1 is v0.1 forever; never
  modified.
- **Bug fixes bump the version.** v0.1.1 re-scores every prior submission
  against the new bundle. Submitters are notified; nothing requires
  resubmission unless the submitter wants to update.
- **Comparing across versions is meaningless.** A score on v0.1 has no
  direct comparison to v0.2. Leaderboards segment by version.

## Cadence

**Continuous, not biennial.** Submissions are scored on demand;
leaderboard refreshes nightly. This is a deliberate departure from
CASP (biennial cycles) — friction detection is closer to MLPerf in
deployment urgency than to protein folding.

## One-submission-per-version rule

A system gets one shot per benchmark version. The submission is the
submission; cherry-picking is forbidden. If you want to iterate against
v0.1, you generate your own private test set from the open generator;
the leaderboard score is the one shot.

This is the AlphaFold discipline: CASP submissions are one-shot blind.
We mirror that.

## Public artifacts

Every leaderboard entry exposes:

- `system_name`, `system_version`, `track`
- Aggregate score (with FP penalty applied)
- Per-axis breakdown
- False-positive count on the 754 negative-screen pool
- Time-to-detect distribution (median + p95)
- Synthetic-real gap (or "real set unavailable" annotation)
- Submission manifest (publicly viewable)
- Docker image reference (publicly pullable)
- Submission date + verification status

Submissions are NEVER anonymous on the leaderboard. Naming is the credit /
accountability lever.

## What v0.1 governance does NOT decide

- **Conflict-of-interest disclosure rules** — v2 governance change once the
  body owning the leaderboard is independent of CJI.
- **Commercial use of the benchmark name** — v2.
- **Trademark + marketplace governance** — v2.

These wait for the v2 governance transition, deliberately.
