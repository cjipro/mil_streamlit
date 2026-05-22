# FrictionBench v0.1 — submission protocol

**Filed under PULSE-88.**

## How to submit

1. Write a `submission_manifest.yaml` matching [`submission_manifest_schema.yaml`](submission_manifest_schema.yaml).
   (See [`example_submission_manifest.yaml`](example_submission_manifest.yaml) for a worked example.)
2. Build a Docker image that exposes a `POST /detect` endpoint per the
   contract below. Push the image to a public registry.
3. Open a submission PR / form against the benchmark org adding your
   manifest. The harness pulls your image, streams sessions, scores you.

One submission per system per benchmark version (`v0.1`). Cherry-picking is
forbidden — see [#integrity-rules](#integrity-rules).

## /detect endpoint contract

Submitter Docker image must expose `POST /detect` accepting a stream of
canonical Pulse events (PULSE-87 schema) and emitting detections.

### Request

`POST /detect`

Content-Type: `application/x-ndjson`

One canonical event per line, exactly matching `pulse/schema/canonical_schema.yaml`:

```json
{"envelope": {...}, "identity": {...}, "context": {...}, "event": {...}}
{"envelope": {...}, "identity": {...}, "context": {...}, "event": {...}}
...
```

Events arrive in session-interleaved order. The detector MUST handle
out-of-order arrival within a session via `context.sequence_no` (PULSE-87
ordering rule).

### Response

Streamed `application/x-ndjson`. Each line is one detection emission:

```json
{
  "session_id": "<from event.identity.session_id>",
  "screen_id": "<TAQ screen id the detector is flagging>",
  "signature_id": "<one of: dwell_after_error | multi_back_press | abandon_before_submit | none>",
  "cohort_tags": ["<tag>", ...],
  "root_cause": "<one of: template | release | timing | cohort | none>",
  "confidence": 0.0-1.0,
  "time_to_detect_seconds": <float — wall-clock seconds from first matching event in this session to this emission>
}
```

Emit `signature_id: "none"` to declare "I looked at this session and chose
not to flag it" — that is the correct response for cell 10 negatives and
the 754 negative-screen sessions.

The harness counts an emission as a detection iff `signature_id != "none"`.

## LIGO first-detection model

Detection MUST be emitted at the moment the signal first crosses the
detector's internal threshold — NOT at the end of the session, NOT after a
retrospective sweep.

Why: real-world Pulse fires while the customer is still in-session; a
detector that needs to wait for session-end is useless for real
deployment. The benchmark rewards systems that decide early.

`time_to_detect_seconds` is the wall-clock elapsed from the first event in
this session that the detector saw, to the detection emission. Lower is
better; tied scores break on TTD.

## Integrity rules

- **One submission per system per benchmark version.** You may submit
  again only against a new benchmark version (v0.2, v0.3, ...).
- **No cherry-picking.** You cannot submit, see the score, tweak, resubmit
  against the same version. The first submission against v0.1 is your v0.1
  score.
- **No private test-set access.** The test set is open-source. There is no
  hidden hold-out; if you want a hold-out you generate one yourself from
  the open generator.
- **Reproducibility.** Your Docker image must run deterministically: the
  harness will run your image twice on the same input bundle and reject
  the submission if the two runs disagree above 0.1% session count.

## Submitter declarations (per manifest)

Required:

- **Track:** `deterministic` or `llm_augmented` (see `leaderboard/tracks.yaml`)
- **System name + version:** stable identifier for the leaderboard row
- **Runtime architecture summary:** ≤300 words on how detection works
- **Pipeline / model / template versions:** for reproducibility
- **License:** SPDX identifier for the submitted system
- **Contact:** for verification / re-run requests
- **Real-set reporting:** even if "real set unavailable at v0.1" (see
  [`transfer/TRANSFER_EVALUATION.md`](../transfer/TRANSFER_EVALUATION.md))

For LLM-Augmented track only:

- **Provider:** OpenAI / Anthropic / local-Ollama / etc.
- **Model + model_version:** exact identifier
- **Cost per investigation:** $/investigation, reported on the leaderboard
- **Latency per investigation:** median + p95 milliseconds

These declarations are themselves public; bad-faith declarations are a
verification failure (the harness re-runs and checks).

## Scoring contract

The harness runs scoring per [`scoring/score.py`](../scoring/score.py).
That code is open-source — submitters can run it locally before submitting
to estimate their score against the published bundle.

## Versioning

The submission protocol is itself versioned. v0.1 of the protocol pins to
v0.1 of the test set. Protocol changes (e.g. v0.2 adds a `streaming_chunk_size`
declaration) force a benchmark-version bump and a re-submission cycle.

## What's NOT in the protocol at v0.1

- Streaming back-pressure semantics (the harness will work it out per submission for now)
- Multi-tenant submissions (one submission per system; team-tagged variants are separate systems)
- Live-monitoring of submissions in flight (results published after run completes)
