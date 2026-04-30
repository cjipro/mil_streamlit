# Hodos Governance

This document explains how decisions get made in Hodos and how the
project is run today. The model is deliberately thin — Hodos is a
small project, and the governance scales with the project's actual
needs, not its hopes.

## Maintainer

Hodos is maintained by **Hussain Ahmed** (hello@cjipro.com).

The maintainer makes final decisions on what merges, what ships,
and when. Disagreement is welcome on issues and pull requests; the
maintainer has the final call.

If the maintainer pool ever grows beyond one person, the process
for adding new maintainers will be documented here. Until then,
this section is short by design.

## Release cadence

Hodos uses semantic versioning (semver: MAJOR.MINOR.PATCH).

- **PATCH** releases (x.y.Z) ship as needed for bug fixes and
  security updates.
- **MINOR** releases (x.Y.0) ship when a meaningful set of features
  has accumulated. No fixed schedule.
- **MAJOR** releases (X.0.0) ship when a breaking change to a
  public interface is necessary.

Breaking changes are avoided when possible. When unavoidable, they
will be announced in advance via release notes, with a deprecation
period of at least one MINOR release before removal.

## Decision-making

For ordinary changes (bug fixes, small features, doc improvements):
the maintainer reviews the pull request and merges if it meets the
bar. Lazy consensus — if no one objects, the change ships.

For larger changes (new public interfaces, architectural decisions,
breaking changes): an issue or RFC discussion happens first. The
maintainer decides after the discussion has run its course.

For changes that would affect the project's direction or licensing:
those go beyond ordinary contribution and should be raised directly
with the maintainer at hello@cjipro.com.

## What's in scope, what's not

Hodos is a general framework for customer-journey intelligence. In
scope:

- Signal harvesting from public sources
- Schema and taxonomy infrastructure for journey-level analysis
- CAC inference and CHRONICLE-anchored RAG
- Briefing generation and publishing
- Authentication and access scaffolding for hosted deployments

Out of scope:

- Specific real-world incident data (this lives in private CJI-side
  ledgers, not in Hodos)
- Specific customer brand surfaces (CJI brand assets, CJI's partner
  data — these are CJI-product concerns, not Hodos concerns)
- General-purpose tools that would belong in their own projects
  (e.g., a generic ETL framework — not in scope here)

For more on what's Hodos vs CJI, see HODOS_NAMING.md.

## Changes to this document

Updates to GOVERNANCE.md follow the same review process as code
changes — open a pull request, discuss, merge. Material governance
changes will be announced in release notes.
