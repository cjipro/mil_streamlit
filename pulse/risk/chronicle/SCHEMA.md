# Chronicle entry schema (CHR-friction-NNN)

Each entry lives at `pulse/risk/chronicle/entries/CHR-friction-NNN.yaml`.
Files are loaded by [`load_chronicle_library()`](./validate.py) at engine
startup. Malformed entries fail closed — the engine refuses to start.

Filed under [PULSE-100].

## Two-stage trust model

Mirrors MIL Chronicle's curator-signoff pattern.

1. **Authored** — entries ship with `verification_status: pending_human_review`.
   The matcher excludes them from Risk-tier escalation.
2. **Verified** — a curator with UK-banking enforcement expertise
   corroborates every fact against the cited public sources and flips
   `verification_status` to `verified`. Only verified entries influence
   Risk scoring.

Risk methodology callers can pass `include_pending=True` to
`match_signature()` for diagnostic / dev tooling, but never in production.

## Naming

`chronicle_id` matches `CHR-friction-NNN` (e.g. `CHR-friction-001`). The
filename is the chronicle_id plus `.yaml`. Numbering is monotonically
increasing — never reuse a retired ID. Existing entries are append-only;
amendments require a new entry and a retired-status note (mirrors MIL's
immutability rule).

## Required fields

### `chronicle_id` (string, required)

`CHR-friction-NNN` (three or more digits).

### `institution` (string, required)

The institution name as the regulator published it. Naming an institution
when citing a public Final Notice is not a PII breach — the regulator
already named them. Naming an institution without a citation IS a breach;
the `public_sources` requirement enforces this.

### `regulator` (enum, required)

One of: `FCA`, `PRA`, `ICO`, `EBA`, `ECB`, `BAFIN`, `AMF`, `CSSF`.
Extending the list requires a Pulse engine release (it's load-bearing for
the matcher's regulator-taxonomy joins).

### `year` (integer or `YYYY` string, required)

Year the **enforcement action** landed (not the year of the underlying
incident — that's `incident_year`, optional).

### `incident_year` (integer or `YYYY` string, optional)

Year the underlying friction incident occurred. Useful when the
incident-to-enforcement lag is the load-bearing pattern (e.g. TSB 2018
incident → 2022 fine).

### `friction_pattern` (mapping, required)

The shape that makes the entry matchable.

- **`signature_id`** (non-empty string) — Pulse friction signature
  (e.g. `dwell_after_error`, `multi_back_press`, `abandon_before_submit`,
  `unclear_validation_message`). Curators retroactively classify
  enforcement cases into the engine's signature vocabulary.
- **`journey_category`** (enum) — `choke_point` / `context_loss` /
  `behavioural_noise` / `regulator` / `infrastructure`. Matches the
  taxonomy in [`pulse/contracts/journey_taxonomy.yaml`](../../contracts/journey_taxonomy.yaml).
- **`screen_class`** (non-empty string) — broad screen/journey class
  (e.g. `credit_application`, `mortgage_arrears`, `payment_initiation`,
  `account_login`).
- **`severity`** (enum) — `P0` / `P1` / `P2`.

### `enforcement_action` (mapping, required)

- **`type`** (enum) — `fine` / `redress` / `restriction` /
  `individual_sanction` / `s166_review` / `voluntary_undertaking`.
- **`fine_gbp`** (number or null, optional) — fine amount in GBP.
- **`redress_gbp`** (number or null, optional) — redress amount in GBP.
- **`individual_named`** (bool, optional) — did the action name a
  responsible individual (e.g. under SMCR)?

### `remediation_imposed` (list of strings, optional)

Imposed remedies (e.g. `s166_skilled_person_review`,
`board_oversight_required`, `redress_scheme`, `procedural_change`).

### `public_sources` (list of mappings, required, non-empty)

Every entry requires at least one verifiable public-source citation.

Each entry:
- **`source`** (non-empty string) — publisher + title
  (e.g. "FCA Final Notice — TSB Bank plc").
- **`date`** (YYYY-MM-DD or YYYY-MM string, or PyYAML date) — publication date.
- **`url`** (string, optional but strongly recommended).

### `notes` (string, optional)

Short prose explaining the friction pattern and its connection to the
enforcement action. Renders into the briefing's Chronicle citation line.

### `verification_status` (enum, required)

`pending_human_review` / `verified` / `rejected`. See "Two-stage trust
model" above.

## PII deny-list

The validator walks every string in the entry and rejects values containing
PII deny-list tokens (`@` for emails, `sort code`, `account number`,
`date of birth`, `national insurance number`). Public enforcement notices
never carry these — a hit means the curator copy-pasted from the wrong
source. Same discipline as
[`real_bank_contract.yaml`](../../contracts/real_bank_contract.yaml).

## Loading from Python

```python
from pulse.risk.chronicle import load_chronicle_library, match_signature

library = load_chronicle_library("pulse/risk/chronicle/entries/")
matches = match_signature(
    library,
    signature_id="dwell_after_error",
    screen_class="credit_application",
    severity="P0",
)
for m in matches:
    print(f"{m.chronicle_id}: {m.regulator} action {m.year} ({m.enforcement_type})")
```

[PULSE-100]: https://cjipro.atlassian.net/browse/PULSE-100
