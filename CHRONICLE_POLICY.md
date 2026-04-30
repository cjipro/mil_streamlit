# CHRONICLE policy

CHRONICLE is the immutable failure ledger that anchors every CJI inference. This document explains what an entry is, what the verification standard requires, how new entries get proposed, and the governance rules around amendment.

The banking pack lives at [`mil/CHRONICLE.md`](mil/CHRONICLE.md). The schema and policy described here apply to any CHRONICLE pack — banking, insurance, telecoms, retail, or otherwise.

---

## Why CHRONICLE matters

CJI's CAC formula does not rate a finding on signal volume alone. The `Sim_hist` term measures cosine similarity to the nearest CHRONICLE entry — a finding that does not anchor to a verified historical failure pattern is suspect by construction.

```
C_mil = (alpha * Vol_sig + beta * Sim_hist) / (delta * Delta_tel + 1)
```

This is Article Zero applied to inference: a strong-signal finding without precedent is exactly the case where the system should withhold judgement, not the case where it should call confident risk.

CHRONICLE is the moat. The ledger is what makes a CJI inference different from a sentiment-analysis dashboard.

---

## What an entry is

A CHRONICLE entry documents a single verifiable failure event — usually a documented outage, regulator-investigated incident, or court-of-record incident. It is not a synthesis, not an opinion, and not a forecast.

Every entry carries:

| Field | Meaning |
|---|---|
| `chronicle_id` | Unique immutable identifier — `CHR-NNN` |
| `date` / `date_window` | The incident date or window |
| `bank` (or sector-equivalent subject) | The institution involved |
| `incident_type` | Classification tag |
| `journey_tags[]` | Which customer journeys were affected |
| `verified_facts[]` | Each fact must trace to a named public source |
| `causal_chain` | What led to what (structured) |
| `outcome` | Regulatory, financial, reputational |
| `confidence` | HIGH / MEDIUM / LOW per dimension |
| `public_sources[]` | Verified public sources (name + approximate date) |
| `review_flags[]` | Fields requiring human sign-off before inference uses them |
| `inference_approved` | `true` if inference may trace to this entry |
| `confidence_score` | Numeric ceiling on traced inferences (0.0–1.0) |

See `mil/CHRONICLE.md` for canonical examples — `CHR-001 TSB 2018` is the reference shape.

---

## The verification standard

A CHRONICLE entry is held to a high evidentiary bar because every downstream inference inherits its claims.

### Required

- **Named public sources.** "Reuters reported" is acceptable; "industry contacts confirmed" is not. Every `verified_fact` must trace to a source readable by anyone.
- **Regulatory or court records when available.** Where a regulator has investigated, cite the regulator's published findings — they are the highest-confidence sources available.
- **Specific numbers, not estimates.** "1.9 million customers locked out" not "millions of customers". If the source gives a range, record the range.
- **Dated facts.** Every claim is anchored to when it was reported, not when the entry was written.

### Permitted with marking

- **`[REVIEW REQUIRED]` fields.** A field that cannot be verified at entry-write time is marked `[REVIEW REQUIRED]` and may not enter inference. Subsequent verification can clear the flag — the original entry is untouched.
- **`confidence_score < 1.0`.** A genuinely uncertain entry caps the confidence of any inference that anchors on it. Use this when public reporting is partial. CHR-002 (Lloyds 2025) is an example: APPROVED WITH CAP at 0.6.
- **`inference_approved: false`.** An entry whose facts are too thin to use for inference, but whose existence in the ledger is itself useful as documentation. CHR-003 (HSBC 2025) is an example: INFERENCE HOLD pending root-cause confirmation.

### Forbidden

- **Speculation as fact.** "TSB chose big-bang because of cost pressure" is acceptable as a `causal_chain` step (chains are inferential by design); "TSB executives knew the migration would fail" is not, unless a regulator has found it as fact.
- **Quotes from non-public sources.** Internal documents, leaked memos, off-the-record briefings do not enter CHRONICLE.
- **Composite incidents.** Each entry is one event. If two outages share a root cause, they are two entries with cross-references.

---

## How new entries get proposed

The pipeline surfaces candidates automatically.

```
Step 4a — Research trigger
  P0/P1 findings whose CHRONICLE anchor falls below sim_threshold
  → mil/data/research_queue.jsonl

py mil/researcher/research_agent.py
  Clusters research_queue by competitor + journey
  Calls Opus (governance tier) to draft proposed CHRONICLE entries
  → mil/data/chr_proposals/{competitor}_{journey}_{ts}.md
  → mil/data/chr_proposals/summary_{ts}.md
```

Flags:
- `--dry-run` — cluster report only, no LLM calls
- `--competitor <name>` — filter to a single subject
- `--force` — bypass the `CHR_COVERAGE` registry skip (use when existing CHR entries don't cover a subject's journey)

Proposals are draft documents. They are not entries. Human review converts a proposal into an entry by:

1. Independently verifying every `verified_fact` against named public sources.
2. Marking unverifiable fields `[REVIEW REQUIRED]` and setting `inference_approved` accordingly.
3. Choosing a confidence cap if reporting is partial.
4. Appending to `mil/CHRONICLE.md` with the next sequential `chronicle_id`.
5. Reserving the `CHR-NNN` slot in `mil/researcher/research_agent.py` `CHR_COVERAGE` registry.
6. Committing to git — the commit is the audit trail.

---

## Append-only

Existing entries may not be amended. This is the constitutional rule.

If new information emerges that contradicts an existing entry, the resolution is **not** to edit the entry. The resolution is:

- For *correction of a clear error* (e.g. a fact was misattributed to the wrong source): add a new entry that supersedes, and mark the original entry `inference_approved: false` — the original stays in the ledger as documented history.
- For *new evidence on a still-active incident*: write a new entry with the new evidence. CHRONICLE is a record of what was understood when, not a perpetually-updated wiki.
- For *fields originally marked `[REVIEW REQUIRED]` that have since been verified*: these may be cleared in place, because clearing a review-flag does not change the substantive claim — it only confirms it. This is the only permitted mutation.

The git history of `mil/CHRONICLE.md` is itself part of the ledger. Force-pushes against `main` that rewrite CHRONICLE history are not permitted.

---

## Pack composition

A CHRONICLE pack is a sector-specific bundle of entries plus the configuration that surrounds them.

| Component | What |
|---|---|
| `mil/CHRONICLE.md` | The entry corpus itself |
| `mil/config/domain_taxonomy.yaml` | Issue types, customer journeys, severity gates relevant to the sector |
| `mil/config/apps_config.yaml` (subjects section) | Subjects monitored — for CJI's banking pack, the six UK retail banks |
| `mil/config/clients.yaml` | Subjects for which Sonar PDB renders |

A fork that wants to retarget CJI to a different sector replaces these four files. The engine code does not need to change.

The reference banking pack ships 19 entries (CHR-001..019) covering UK retail banking incidents from 2018 to present. CHR-001 (TSB 2018) is the foundational entry — it is the most heavily documented banking IT failure in the UK record and serves as the "ground-truth" calibration anchor.

---

## How distribution works (status: undecided)

The free/paid split for CHRONICLE entries is a strategic decision in flight. The current state:

- The **engine** code is open and forkable.
- The **banking CHRONICLE pack** that the reference instance ships with is currently in this repository.
- Whether future CHRONICLE packs (insurance, telecoms, retail) ship as free assets, as licensed packs from domain-pack authors, or as a paid subscription is being decided.

This document will be updated when the decision lands. Until then, contributors authoring entries should expect that their work is governed by the same verification standard regardless of distribution model.

---

## Article Zero, restated

> *"This system shall prioritise the expression of its own ignorance over the delivery of any unverified certainty. Honesty in calibration is the only product; all inferences are secondary to the preservation of the Designed Ceiling."*

CHRONICLE is the operational embodiment of this rule. An entry that cuts a corner on verification undermines every inference that subsequently anchors on it — and undermines the system's claim to honesty as a deliverable.

The ledger is small, slow-growing, and reviewed by a human. That is the design.
