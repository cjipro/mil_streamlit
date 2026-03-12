# CJI Pulse — Complete Data Strategy
## Sponsored by TAQ Bank
## Version 2.0 — 2026-03-12

---

## What We Are Building

CJI Pulse is a journey intelligence platform that ingests hundreds of millions
of mobile app events every month, derives behavioural signals from them, and
presents findings to journey owners in a way that is trustworthy, auditable,
and actionable. The data dictionary is the foundation of everything. Before a
single pipeline is built, before a single agent is deployed, before a single
dashboard is shown — the dictionary must be right. Every table, every field,
every name, every rule defined here flows through the entire system. Get this
wrong and everything built on top of it inherits the mistake.

This strategy governs how data is named, stored, protected, governed, and used
across the entire CJI Pulse platform. It applies to every table, every field,
every agent, every pipeline, and every output. It is not aspirational. It is
contractual.

---

## The Core Problem We Are Solving

Original systems have naming conventions that are internal, sensitive, and
potentially identifying. A table name tells an informed reader which
organisation it belongs to, which technology stack is in use, and how that
organisation structures its data. A field name tells a reader exactly what
abbreviated notation that original system uses internally. These names must
never appear in CJI Pulse — not in code, not in documentation, not in agent
prompts, not in logs, not in legal submissions.

At the same time we cannot simply ignore original names. We need to trace data
lineage. We need to verify that the field we call Session ID is the same field
the original system uses internally. Without that traceability the system is
unauditable.

The strategy solves both problems simultaneously — through cryptographic
hashing, a three name convention, a substitution registry, two purpose-built
dictionaries generated from one master source, a three-layer governance model
that keeps table contracts lean without losing auditability, and a regulatory
compliance framework that satisfies UK GDPR, FCA Consumer Duty, and the EU AI
Act from day one.

---

## The Three Name Rule

Every table and every field in CJI Pulse has exactly three identities. No
more, no less. Each identity serves a different audience and a different
purpose.

The Human Name is the full descriptive name written in plain English.
Mobile_App_Events_Raw tells anyone exactly what they are looking at. Mobile
means the channel. App means the application. Events means individual
interactions. Raw means this is source data, not derived or processed. No
abbreviations. No codes. No internal jargon. This is the name that appears in
documentation, dashboards, reports, and conversations.

The Agentic Name is the initials of the human name. Mobile_App_Events_Raw
becomes MAER. Customer_Profile_Dim becomes CPD. Call_Centre_Events_Raw becomes
CCER. Short, consistent, and lightweight for code and agent prompts. Fields
follow the same rule — MAER_session_id means the session ID field in the
Mobile App Events Raw table. The prefix tells you the table. The suffix tells
you the field. No ambiguity possible.

The Source Hash is a one-way cryptographic fingerprint of the original table
or field name. Generated using HMAC-SHA256 and a secret key that never enters
this system. The raw original name is never written down, never stored, never
committed, never passed to any agent, never mentioned in any file inside CJI
Pulse. Only the hash exists. During an audit the original system recomputes the
hash using their secret key and compares it to what is stored. If they match
lineage is confirmed. No original names need to be revealed to anyone.

---

## Where Hashes Live

The source hash is stored in exactly two places and nowhere else.

The first is the master data dictionary — at both table level and field level.
Every table entry carries a source_hash, hash_algorithm, hash_scope, and a
flag confirming the hash was generated outside the codebase. Every field entry
carries a source_field_hash with the same metadata. The human dictionary never
contains hashes. The agentic dictionary never contains hashes. No pipeline, no
agent prompt, no log file, no dashboard, no report ever contains a hash.

The second is the audit verification log — part of the provenance system
governed by P14. When lineage is verified during an audit the verification
event is permanently logged. The secret key is used once at verification time
and immediately discarded. It is never stored anywhere inside CJI Pulse.

Hash lifecycle:
- OUTSIDE: Original system runs HMAC-SHA256 against fully qualified original
  name using their secret key. Secret key stays in their vault.
- STORAGE: Hash pasted into master data dictionary only. Original name
  discarded and never written anywhere.
- OPERATION: All pipelines and agents use human names and agentic names only.
  Hash is invisible to them.
- AUDIT: Auditor provides secret key and claimed original name. System
  recomputes hash and compares to stored value. Result logged permanently to
  provenance system.

---

## The Substitution Registry

Some original systems use internal codes and brand names that are recognisable
and identifying. These must be substituted the moment they are encountered —
in data, in code, in documentation, in agent output, anywhere.

The registry stores only the CJI Pulse safe equivalent. The original term is
never recorded inside the system.

Current substitutions locked and active:

| CJI Pulse Term | Reason |
|----------------|--------|
| Habib Bank | Client identity — original name sealed |
| APP | Internal brand code — original code sealed |
| TAQ Bank | Sponsor — the only organisational name that ever surfaces |

---

## Two Dictionaries From One Source

The master data dictionary is the single source of truth. Never read directly
by humans or agents. Two dictionaries generated automatically and kept
permanently in sync.

The Human Dictionary contains only the gold fields — approximately nine to
fifteen fields per table. All names are plain English human names. No original
names, no agentic codes, no hashes, no substituted terms. Reviewed and signed
off by business owners.

The Agentic Dictionary contains every field across every table, enriched with
everything an agent needs. Each field entry contains: agentic name, plain
English description, which journeys it is relevant to, what purposes it is
explicitly permitted to serve (e.g. journey_analytics, fraud_detection,
cohort_analysis, regulatory_reporting, pipeline_monitoring), quality tier,
freshness requirements, known issues, versioning history, and fairness
metadata. Agents use only agentic names. A field not listed under a given
permitted purpose is effectively invisible to any agent operating under that
purpose. This directly implements P10 — purpose_bound_least_privilege.

---

## Table Contracts Are Intentionally Lean

CJI Pulse table contracts are intentionally lean. Every governance marker must
be assessed centrally, but only those mandatory or materially relevant to a
specific table appear in that table's contract. All other markers must be
recorded in the applicability register as No or Not Applicable. Never silently
omitted.

Mandatory core — always present in every table contract:
- table purpose
- business owner
- technical owner
- grain
- keys
- lineage source hash
- data classification
- permitted purposes
- freshness SLA
- quality expectations
- retention class
- contract version

Present only where materially relevant:
- PII masking rules
- consent dependency
- cross-border restrictions
- fairness metadata
- slowly changing dimension rules
- human approval gates
- write-back controls
- customer-facing output controls
- actionability and intervention rules
- special legal or regulatory restrictions

---

## The Three-Layer Governance Model

Layer 1 — The Marker Library
One row per marker only. Records: marker name, definition, owner role, review
cycle, default rule, evidence required, version, effective dates. Primary
owner: Data Governance Lead. Mandatory reviewers: Privacy Lead, AI Governance
Lead, Architecture Lead.

Layer 2 — Applicability Profiles
One row per table type, not per table. Profiles: raw_event_table,
session_table, dimension_table, reference_table, output_table, pii_table,
cross_border_table. Records whether a marker is normally Yes, No, or Not
Applicable for that profile. Each decision records its basis: Client Directed,
Policy Required, Standard Default, or Governance Assessed. TAQ Bank formal
sign-off required only for: business risk appetite decisions, exceptions to
agreed defaults, high-risk use cases, customer-impacting overrides, material
scope changes.

Layer 3 — The Table Exceptions Register
Used only when a specific table departs from its profile. Records: table,
marker, default profile decision, exception, basis, approver, date. Volume
should be low. If it grows large, profiles need updating.

---

## Reassessment Triggers

Mandatory reassessment when any of the following occurs:
- New constitutional principle adopted
- Regulation changes
- New data source or field class appears
- PII newly discovered in a table
- Purpose identifier changes
- Table changes type or grain
- Table becomes customer-facing or decision-influencing
- Cross-border processing introduced
- Risk tier increases
- Data quality issue crosses defined threshold
- Incident, near-miss, override trend, or audit finding
- Annual review date reached

Scheduled reviews: quarterly for Marker Library and profiles. Annual full
attestation confirming all inherited defaults remain valid.

---

## PII Is Never Ignored

Every PII field recorded in the dictionary with its display name and flagged
clearly. Never dropped, never hidden, never omitted. PII fields carry zero
permitted purposes for agent consumption. Masked at earliest pipeline stage.
Masked value — ANONYMISED_STRING — is what flows through the system.

---

## Regulatory Compliance — DPIA and Data Protection

CJI Pulse processes personal data. A DPIA is required and must be registered
before the platform processes live customer data.

Individual monitoring — journey behaviour analysed at session and cohort level
only. Individual surveillance is not a permitted purpose and cannot be added
without governance approval.

Special category data — Customer_Profile_Dim must be fully audited before the
DPIA special category question can be answered definitively. Open item.

Vulnerability data — CJI Pulse explicitly handles vulnerability signals. A
formal vulnerability data processing statement is maintained as a governed
artifact documenting legal basis and safeguards.

Automated decisions and profiling — no fully automated decision-making without
human review. P7 mandates human-in-the-loop for all customer-outcome decisions.
Customers have the right to contest any automated decision. This right is
documented explicitly in the governance layer and supported by full decision
provenance under P14.

New technology — LLMs, agentic workflows, local model inference are new
technologies. P19 requires every external model, tool, and package to be
registered with provenance, data-use restrictions, assurance evidence, and exit
strategy before production deployment.

New and derived data types — ghost intent flags, silent exit flags, abandonment
sequences, vulnerability cohort signals are materially different uses of
existing data. Legal basis for each new derived field type documented explicitly
in the governance layer.

Data sharing — Phase 1 operates within a single environment. No personal data
sent externally. No data leaves the organisation. No data sent outside the UK
in Phase 1.

---

## Regulatory Actions — Open Items

Four actions must be completed before CJI Pulse processes live customer data:

1. Register a formal DPIA with the data protection function
2. Complete audit of Customer_Profile_Dim — special category data question
   cannot be answered until this is done
3. Publish formal vulnerability data processing statement as a governed artifact
4. Publish explicit customer rights statement covering right to contest
   automated decisions and document legal basis for each new derived field type

These are tracked as sprint tickets.

---

## The Table Naming Convention

Raw source: {Channel}_{Type}_Raw — e.g. Mobile_App_Events_Raw
Reference: {Domain}_Ref — e.g. Operation_Codes_Ref
Derived: {Channel}_{Type}_Session — e.g. Mobile_App_Events_Session
Dimension: {Domain}_Dim — e.g. Customer_Profile_Dim
Output: {Domain}_Output

Agentic name = initials of human name. Four or five characters maximum.

---

## Current Table Registry

| Human Name | Agentic Name | Type | Source Hash | Status |
|------------|-------------|------|-------------|--------|
| Mobile_App_Events_Raw | MAER | Raw Source | HASH_PENDING_ORIGINAL | Audited |
| Mobile_App_Events_Ref | MAER_F | Reference | HASH_PENDING_ORIGINAL | Audited |
| Operation_Codes_Ref | OCR | Reference | HASH_PENDING_ORIGINAL | Audited |
| Mobile_App_Events_Session | MAES | Derived | HASH_PENDING_ORIGINAL | Rebuild |
| Mobile_App_Events_Session_Bucketed | MAESB | Derived | HASH_PENDING_ORIGINAL | Rebuild |
| Customer_Profile_Dim | CPD | Dimension | HASH_PENDING_ORIGINAL | Pending audit |
| Call_Centre_Events_Raw | CCER | Raw Source | HASH_PENDING_ORIGINAL | Pending |
| Branch_Visit_Events_Raw | BVER | Raw Source | HASH_PENDING_ORIGINAL | Pending |
| Customer_Satisfaction_Raw | CSR | Raw Source | HASH_PENDING_ORIGINAL | Pending |
| Web_App_Events_Raw | WAER | Raw Source | HASH_PENDING_ORIGINAL | Deferred |

All source hashes are HASH_PENDING_ORIGINAL — generated outside the system by
the original system using their secret key. Never generated inside this
codebase. Never generated by Claude Code. Never generated by any script in
this repository.

---

## Principles Are Guardrails Not Blockers

Twenty-one constitutional principles govern every decision. Not optional. Do
not change without explicit governance approval permanently logged in provenance
system.

A principle violation never stops the system from running. It raises a
structured warning with a principle reference code, logs a permanent audit
event to the provenance system, notifies the responsible owner, and flags for
human review. The violation does not expire, does not disappear, and cannot be
silently ignored. Must be fully resolved or formally overridden with documented
governance approval before the next release. No third option. Every violation
has a human decision attached to it.

---

## Living and Breathing

The dictionary grows continuously. Every field entry versioned. Old definitions
archived not overwritten. Open audit findings tracked directly in the
dictionary. The dictionary is honest about what it does not know as well as
what it does.

---

## The TAQ Bank Rule

TAQ Bank is the only organisational name that appears in any output, dashboard,
agent response, report, or conversation. Any other client or organisational
name encountered anywhere is replaced immediately and permanently with its safe
CJI Pulse equivalent from the Substitution Registry. The original name is
sealed and never surfaces at any price.

---

## In Summary

One master source. Two dictionaries. Three names per table and field.
One-way HMAC-SHA256 hashes for all original names — stored only in master
dictionary and audit verification log, generated only outside the codebase.
Substitution registry for all identifying codes and client names. Three-layer
governance model — Marker Library, Applicability Profiles, Table Exceptions
Register — keeping contracts lean without losing auditability. Applicability
decisions recorded as Yes/No/Not Applicable with decision basis. Mandatory
reassessment triggers from day one. Full regulatory compliance framework. Zero
original names ever stored. Zero client names ever surfaced except TAQ Bank.
Twenty-one principles as permanent guardrails — warn, record, demand resolution,
never block. Four open regulatory actions tracked as sprint tickets.

Simple enough for anyone to understand. Rigorous enough for FCA oversight,
UK GDPR compliance, EU AI Act readiness, and production agentic deployment
at scale.

---
Version 2.0 — 2026-03-12 — Sponsored by TAQ Bank — Governed by 21
Constitutional Principles
---
