# Pulse Diagnosis — rubric (worked examples)

Machine-readable rubric: [`rubric.yaml`](./rubric.yaml). Reference
scorer: [`score.py`](./score.py). Methodology paper:
[`DIAGNOSIS_DESIGN.md`](./DIAGNOSIS_DESIGN.md).

Filed under [PULSE-105].

## Tier words (closed enum)

| Word | Meaning |
|---|---|
| `SUPPORT_PROBLEM` | journey works fine for most; support layer fails to deflect customers who need help → they call. AI assistance unlocks real deflection. |
| `JOURNEY_PROBLEM` | journey itself is broken; needing help is symptomatic. AI assistance is a band-aid. |
| `BOTH` | combination — order matters: fix the journey first, deploy AI second. |
| `INCONCLUSIVE` | control-arm sample too small to call it (n < min_control_sessions). |

Tier-words are unordered labels (unlike Risk/Value's severity ladder) — they
identify problem-locus classes, not severity levels.

## Worked examples

### Example 1 — clear SUPPORT_PROBLEM

`make_a_payment` journey: self-sufficient customers succeed 92% of the time;
assistance-using customers succeed only 58%. Gap = 0.34.

```
journey:               make_a_payment / payment_initiation
no_assistance:         n=2400, success=0.92
assistance_using:      n=540,  success=0.58
gap = 0.92 − 0.58    = 0.34
```

Gap (0.34) ≥ support_problem_gap (0.20) → **SUPPORT_PROBLEM**.

Interpretation: the journey works fine when customers can self-serve;
the support layer is failing the 540 customers who do need help. AI
assistance has real headroom to recover them.

### Example 2 — clear JOURNEY_PROBLEM

`apply_for_loan` journey: both arms are struggling. Self-sufficient
customers succeed 35%; assistance-using customers succeed 31%. Gap = 0.04
and assistance-arm success rate is well below 0.5.

```
journey:               apply_for_loan / credit_application
no_assistance:         n=1100, success=0.35
assistance_using:      n=820,  success=0.31
gap = 0.35 − 0.31    = 0.04
```

Gap (0.04) ≤ journey_problem_gap (0.05) AND assistance success (0.31) < 0.5
→ **JOURNEY_PROBLEM**.

Interpretation: the journey is the binding constraint; help isn't helping
because the underlying flow is broken for both populations. Deploying AI
assistance here would mask the journey defect, not fix it.

### Example 3 — BOTH

`international_transfer` journey: assistance-using customers succeed at
65% vs 78% no-assistance. Gap of 0.13 — not large enough for
SUPPORT_PROBLEM, but assistance-arm success of 0.65 is too high to call
JOURNEY_PROBLEM either.

```
journey:               international_transfer / payment_initiation
no_assistance:         n=900, success=0.78
assistance_using:      n=310, success=0.65
gap = 0.78 − 0.65    = 0.13
```

Gap is in the BOTH band (between 0.05 and 0.20) → **BOTH**.

Interpretation: support layer is contributing AND the journey has friction.
Deploying AI assistance gives some uplift; fixing the journey gives more.
Sequence the journey fix first.

### Example 4 — INCONCLUSIVE (small control arm)

`niche_product_journey` journey: only 45 sessions in the no-assistance arm.

```
journey:               niche_product_journey / account_management
no_assistance:         n=45,  success=0.71   ← below min_control_sessions=100
assistance_using:      n=320, success=0.50
gap = 0.71 − 0.50    = 0.21
```

Gap looks like a SUPPORT_PROBLEM at 0.21, BUT no_assistance.n (45) < 100
→ **INCONCLUSIVE**.

Interpretation: 45 sessions isn't enough to trust the 0.71 baseline. The
diagnosis returns INCONCLUSIVE *rather than raising* — downstream code
(e.g. the Agentic AI placement matrix in PULSE-106) sees INCONCLUSIVE and
knows to flag the journey for "needs more data" rather than presenting a
spurious recommendation.

### Example 5 — borderline NOT labelled JOURNEY_PROBLEM (two-clause rule)

`account_overview` journey: both arms succeed at ~95%. Gap is tiny.

```
journey:               account_overview / account_management
no_assistance:         n=8000, success=0.95
assistance_using:      n=410,  success=0.94
gap = 0.95 − 0.94    = 0.01
```

Gap (0.01) ≤ journey_problem_gap (0.05), BUT assistance success (0.94)
≥ 0.5 → falls through to **BOTH** (the catch-all when neither precedence
condition fires cleanly).

Interpretation: this is a healthy journey with a healthy support layer.
`BOTH` here is the right honest label — neither problem class describes
it well. The downstream consumer sees `BOTH` + the gap (0.01) + both
success rates (0.95 / 0.94) and concludes "no intervention warranted."
A future v0.2 may add a `NOMINAL` / `HEALTHY` tier-word to label this
case more crisply.

### Example 6 — same inputs, same diagnosis (determinism)

`diagnose_problem_locus()` is a pure function. Calling it twice with the
same journey + arms returns `DiagnosisResult` instances with identical
`diagnosis`, `gap`, `methodology_version`, AND `inputs_hash`. A test
asserts this round-trip — symmetric with Risk and Value.

## Why classification, not a continuous score

Diagnosis answers a categorical product question ("is this an AI-deployable
problem?"). A continuous "support-iness" score would over-claim precision
the data doesn't support and would force every downstream consumer to
pick its own threshold. The closed 4-tier enum makes the decision flow
crisp: each downstream surface (HOL-9 badges, HOL-11 placement matrix,
PULSE-106 worked example) renders one of four well-defined labels.

[PULSE-105]: https://cjipro.atlassian.net/browse/PULSE-105
