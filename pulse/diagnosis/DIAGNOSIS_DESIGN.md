# Pulse Diagnosis methodology v0 — design

CASP-style methodology paper. Published before any production Diagnosis
runs against bank deployments. Same discipline as
[`pulse/risk/RISK_DESIGN.md`](../risk/RISK_DESIGN.md) and
[`pulse/value/VALUE_DESIGN.md`](../value/VALUE_DESIGN.md).

Filed under [PULSE-105].

## What Diagnosis is, in one sentence

Diagnosis is a **computed problem-locus label** — it tells you whether
a high-call / high-escalation pattern on journey X is driven by a
broken support layer (where AI assistance helps), a broken journey
(where AI assistance is symptomatic relief), both, or whether the
control-arm data is too thin to tell.

The output is one of four closed tier-words:
`SUPPORT_PROBLEM` / `JOURNEY_PROBLEM` / `BOTH` / `INCONCLUSIVE`.

## Where Diagnosis sits in the decision flow

Diagnosis runs **before** Value (PULSE-101) and Risk (PULSE-99) tier
scoring:

```
1. Diagnosis        →  is this an AI-deployable problem at all?
2. Risk             →  how exposed are we if we deploy / don't deploy?
3. Value            →  how big is the prize if we deploy correctly?
4. (downstream)     →  combine into the placement decision (HOL-9 / HOL-11)
```

The motivation: the Value + Risk pair tells you *how big the prize is*
and *how exposed you are*. It does NOT tell you *whether the
intervention you're considering addresses the actual problem locus*.
A high-Value × low-Risk cell could still be the wrong place to deploy
AI assistance if the underlying journey is broken — fixing the journey
would dominate. Diagnosis is the gate that prevents this misallocation.

## The canonical comparison

The diagnostic signal is the gap between two arms on the same journey:

```
gap = success_rate(no_assistance_arm) − success_rate(assistance_arm)
```

- **no_assistance arm** — sessions on journey X where the customer
  completed (or attempted to complete) the journey **without engaging
  any support channel** (no Help, no Smart Call, no Message Us). The
  "self-sufficient" NO branch in Hussain's customer-path flowchart.
- **assistance arm** — sessions on journey X where the customer
  **did engage support** at some point in the session (any path through
  Help / Smart Call / Message Us / Called).

The gap measures the success-rate uplift of NOT needing help. A large
positive gap means assistance-using customers are dropping below
baseline — the support layer is failing them, and AI assistance would
unlock real deflection. A small or near-zero gap means the journey
itself is the binding constraint — assistance vs no-assistance doesn't
move the success rate much because the journey is broken either way.

## Classification logic

| Diagnosis | Fires when |
|---|---|
| `INCONCLUSIVE` | `no_assistance_arm.n_sessions < min_control_sessions` (default 100) |
| `SUPPORT_PROBLEM` | `gap ≥ support_problem_gap` (default 0.20) |
| `JOURNEY_PROBLEM` | `gap ≤ journey_problem_gap` (default 0.05) AND `assistance_arm.success_rate < 0.5` |
| `BOTH` | otherwise |

Precedence is `INCONCLUSIVE` → `SUPPORT_PROBLEM` → `JOURNEY_PROBLEM` → `BOTH`.
Thresholds live in [`rubric.yaml`](./rubric.yaml) so the methodology
version captures any change.

## The two-clause JOURNEY_PROBLEM rule

The `JOURNEY_PROBLEM` label requires BOTH a small gap AND a low
assistance-arm success rate. Without the second clause, a journey
where both arms succeed at 95% (small gap of 0.02, assistance arm at
0.94) would be labelled `JOURNEY_PROBLEM` — clearly wrong, because
the journey is succeeding for almost everyone. The assistance-arm
ceiling (0.5 by default) ensures we only label a journey "broken"
when assistance-using customers are actually failing.

## Output

`DiagnosisResult` (frozen dataclass) carries:
- `diagnosis` (closed enum tier-word)
- `gap` (the diagnostic signal itself)
- `assistance_arm_n` + `assistance_arm_success_rate` (echoed for audit)
- `no_assistance_arm_n` + `no_assistance_arm_success_rate` (echoed for audit)
- `methodology_version` (pinned from rubric.yaml)
- `inputs_hash` (SHA-256 over journey identity + both arms)

The audit footprint matches the Risk/Value pattern: same inputs +
same methodology version → identical `DiagnosisResult` byte-for-byte.

## Things this methodology deliberately does NOT do

- **No bank_policy reading at v0.** The thresholds are methodology
  constants, not per-deployment knobs. v0.2 may move
  `min_control_sessions` to per-deployment if real telemetry suggests
  the right floor varies meaningfully by bank size.
- **No LLM inference.** Same architectural lock as Risk and Value.
- **No cohort decomposition.** Diagnosis labels the journey as a whole.
  v0.2 could add per-cohort diagnosis if needed (e.g. SUPPORT_PROBLEM
  for over-50s, JOURNEY_PROBLEM for under-30s on the same journey).
- **No causal-inference assumptions stronger than the comparison
  warrants.** The gap is descriptive, not causal — selection effects
  may differ between the two arms (e.g. assistance-seeking customers
  are systematically less digitally-confident). v0.1 reports the gap
  honestly; v0.2 may add propensity-score adjustment if production
  data supports it.

## Versioning

`methodology_version` in [`rubric.yaml`](./rubric.yaml) bumps on:
- any change to `tier_words` (adding / removing / renaming labels)
- any change to threshold values
- any change to the classification precedence

Decision packs that consume Diagnosis pin `required_pulse_version` —
methodology-version changes surface as compatibility failures at
pack-load time.

## v0.1 acknowledged limits

- **Single control-arm definition** — the no-assistance arm is defined
  as "no support channel engaged in the session." Real telemetry will
  expose edge cases (partial engagement, abandoned-then-resumed sessions)
  that v0.2 will need to address.
- **Fixed thresholds across journeys** — the 0.20 / 0.05 / 0.5 thresholds
  apply uniformly. Some journeys may warrant journey-specific calibration
  (e.g. an authentication journey has different baseline success rates
  than a credit-application journey). v0.2 may move thresholds into
  per-journey overrides.
- **Min control-arm 100** — provisional. Real production volumes will
  refine this.

[PULSE-105]: https://cjipro.atlassian.net/browse/PULSE-105
