# Decision-pack metadata — design

**Filed under PULSE-89.**

## Why metadata is a contract

Every decision pack ships with a `metadata.yaml` at its root that the engine
loads + validates at registration time. Rejection means the pack does not
run. This is the only place we declare:

- which engine version the pack expects (`required_pulse_version`)
- which synthesis mode the pack uses (`synthesis_mode`)
- which compliance frameworks the pack claims fitness for (`compliance_attestations`)
- whether the pack invokes fairness methods on convergent investigations (`fairness_methods_required`)

The metadata is the audit anchor: any investigation produced by a pack
carries the pack's `pack_version` in its lineage row. Reviewers can pull
the metadata at that version to see what the pack claimed at the time the
output was produced.

## v1 immutability: synthesis_mode

`synthesis_mode` accepts two values in the type system: `deterministic` and
`llm_augmented`. The validator in `pulse.decision_packs.validate_metadata()`
**rejects `llm_augmented` in v1**.

This is deliberate. The forward-compatible value exists in the schema so v2
can adopt it without a schema bump, but the v1 validator REFUSES it so no
pack can opportunistically switch modes. Enabling LLM augmentation requires:

1. Shipping `LLMSynthesisProvider` (see `pulse/synthesis/SYNTHESIS_DESIGN.md`)
2. Removing the v1 immutability check (a code change reviewers can grep for)
3. Submitting the pack to the FrictionBench LLM track (see PULSE-88)
4. Governance review (security + audit + regulatory) recorded against the pack version

Each step is auditable. None can happen silently.

## Required fields (validated)

| Field | Type | Notes |
|---|---|---|
| `pack_name` | string | Stable identifier; engine registry key |
| `pack_version` | semver | `MAJOR.MINOR.PATCH` |
| `required_pulse_version` | semver range | e.g. `>=1.0.0,<2.0.0` |
| `synthesis_mode` | enum | `deterministic` in v1 |
| `authors` | list[string] | Maintainer attribution |
| `license` | string | SPDX identifier (e.g. `Apache-2.0`) |
| `fairness_methods_required` | boolean | True for regulator-facing or high-stakes packs |
| `compliance_attestations` | list[object] | One entry per framework the pack claims fitness for |

## Compliance attestation entries

Each entry declares one framework:

| Field | Notes |
|---|---|
| `name` | Framework identifier (e.g. `fca_consumer_duty_2.0`) |
| `status` | `self_declared` / `independently_assessed` / `certified` |
| `last_reviewed` | ISO date (`YYYY-MM-DD`) |

The status hierarchy reflects audit weight:

- **self_declared** — pack author asserts fitness, no external review. Cheap; the default starting point.
- **independently_assessed** — external reviewer signed off (review record attached separately).
- **certified** — formal certification body attestation (certificate attached separately).

Reviewers should treat `self_declared` as starting evidence, not conclusion.

## Optional fields

- `description` — one-paragraph human summary
- `notes` — free-form maintainer notes (changelog snippets, deprecation warnings)

## Worked example

See `example_pack/metadata.yaml`. Used as a test fixture.
