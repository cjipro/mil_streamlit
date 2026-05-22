# Decision-pack registry

**HOL-7 hard launch gate:** ≥40 decision packs covering the FrictionBench
12-cell matrix × multiple signature/cohort variants. This file is the map.

## Status

| Cell | Screen | Signature | Pack | State |
|---:|---|---|---|---|
|  1 | `loans.apply.step3` | `dwell_after_error` | [`loans_apply_step3__dwell_after_error/`](./loans_apply_step3__dwell_after_error/) | **deep** |
|  2 | `loans.apply.step3` | `multi_back_press` | [`loans_apply_step3__multi_back_press/`](./loans_apply_step3__multi_back_press/) | **deep** |
|  3 | `loans.apply.step3` | `abandon_before_submit` | [`loans_apply_step3__abandon_before_submit/`](./loans_apply_step3__abandon_before_submit/) | **deep** |
|  4 | `international.beneficiary.setup` | `dwell_after_error` | [`international_beneficiary_setup__dwell_after_error/`](./international_beneficiary_setup__dwell_after_error/) | **deep** |
|  5 | `international.beneficiary.setup` | `multi_back_press` | [`international_beneficiary_setup__multi_back_press/`](./international_beneficiary_setup__multi_back_press/) | **deep** |
|  6 | `international.beneficiary.setup` | `abandon_before_submit` | [`international_beneficiary_setup__abandon_before_submit/`](./international_beneficiary_setup__abandon_before_submit/) | **deep** |
|  7 | `cards.credit.apply.eligibility` | `dwell_after_error` | [`cards_credit_apply_eligibility__dwell_after_error/`](./cards_credit_apply_eligibility__dwell_after_error/) | **deep** |
|  8 | `cards.credit.apply.eligibility` | `multi_back_press` | [`cards_credit_apply_eligibility__multi_back_press/`](./cards_credit_apply_eligibility__multi_back_press/) | **deep** |
|  9 | `cards.credit.apply.eligibility` | `abandon_before_submit` | [`cards_credit_apply_eligibility__abandon_before_submit/`](./cards_credit_apply_eligibility__abandon_before_submit/) | **deep** |
| 10 | `investments.premier.portfolio.overview` | `dwell_after_error` | [`investments_premier_portfolio_overview__dwell_after_error/`](./investments_premier_portfolio_overview__dwell_after_error/) | **deep** — **load-bearing negative** (detector must NOT fire; samples show the suppression discriminator at work) |
| 11 | `investments.premier.portfolio.overview` | `multi_back_press` | [`investments_premier_portfolio_overview__multi_back_press/`](./investments_premier_portfolio_overview__multi_back_press/) | **deep** |
| 12 | `investments.premier.portfolio.overview` | `abandon_before_submit` | [`investments_premier_portfolio_overview__abandon_before_submit/`](./investments_premier_portfolio_overview__abandon_before_submit/) | **deep** |
| —  | (bundle — all signatures × all screens) | — | [`example_pack/`](./example_pack/) | test-fixture only (pinned by `pulse/tests/test_decision_pack_metadata.py`) |

**Coverage status:** 12 of 12 FrictionBench cells built (deep shape each).
HOL-7 gate: ≥40 templates — currently **13** including the test-fixture
bundle. Remaining ≈27 to clear the gate via the cohort/remediation variant
axis (see "Path to the 40-pack gate" below).

## Naming convention

```
<screen-id-with-dots-as-underscores>__<signature-id>/
```

Double underscore separates screen from signature. `pack_name` inside
`metadata.yaml` matches the directory name.

## Pack shape (what's inside each directory)

```
<pack_name>/
├── metadata.yaml         # validator-enforced contract (see ../metadata_schema.yaml)
├── hypothesis.yaml       # detector declaration — shape preview, PULSE-93 will tighten
├── templates/            # 3 altitudes; rendered by TemplateSynthesisProvider at v1
│   ├── bank.md.j2        # exec headline — maximum compression
│   ├── journey.md.j2     # default altitude — narrative + evidence summary
│   └── signal.md.j2      # individual-event detail — maximum expansion
└── samples/              # fixture-rendered outputs (illustrative — what v1 will produce)
    ├── bank.md
    ├── journey.md
    └── signal.md
```

`metadata.yaml` is the only file the engine validates today. `hypothesis.yaml`
and `templates/` are shape previews — they get loaded by the v1 synthesis
layer when PULSE-93 lands (`pulse/synthesis/base.py::TemplateSynthesisProvider`
currently raises `NotImplementedError`).

## Path to the 40-pack gate

Twelve cells × ~3-4 variants per cell ≈ 40. Variant axes under consideration
(not yet locked):

- **cohort focus** — age_band / device_class / first_time_visitor / advised_vs_self_directed
- **remediation category** — template_fix / validation_clarity / cohort_routing / disclosure_design
- **regulatory framing** — Consumer Duty foreseeable harm / EU AI Act high-risk / FCA SM&CR accountability

The 12 cells × 3 signatures fix the *what*; variants fix the *for whom* and
*how to act*. The 40-pack target is a coverage floor, not a number target —
HOL-7 unlocks when the registry honestly covers the buyer-relevant variants
of each cell.

## Build order

1. ~~Showcase: 3 deep packs on `loans.apply.step3`~~ ✓ done
2. ~~Cell coverage: remaining 9 cells, deep shape each~~ ✓ done
3. Cohort variants: ~27 more packs to clear 40, after cohort axis is locked.
4. HOL-7 unlock: when the registry passes the gate test.
