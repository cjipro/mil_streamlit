# CJI and Hodos — what's what

This repository contains **Hodos**, an open-source engine for
customer-journey intelligence.

A separate, closed product called **CJI** is built on top of Hodos.
This document explains the boundary between the two, so contributors,
forkers, and readers understand what's open-source (Hodos) and what
isn't (CJI).

## In one sentence

Hodos is the general framework. CJI is one specific application of
the framework. CJI is powered by Hodos.

## The names

**Hodos** is from the Greek *ὁδός*, meaning "way", "path", or
"method". The name reflects the framework's job: providing the
methods by which customer-journey patterns become intelligible.
Hodos doesn't carry an industry, doesn't carry a brand, doesn't
carry a particular customer.

**CJI** stands for "Customer Journey Intelligence". CJI is a
specific commercial product focused initially on UK retail
banking, operated at cjipro.com. CJI uses Hodos as its engine and
adds:

- A curated CHRONICLE of real-world banking incidents and the
  patterns they reveal
- A specific brand surface (CJI Briefing, CJI Reckoner, CJI Sonar,
  CJI Pulse, CJI Lever, CJI Chronicle)
- Partner contracts with named firms
- A hosted instance with managed infrastructure

## What's in this repository (Hodos)

- Engine code: harvesting, taxonomy, inference, CHRONICLE schema,
  publishing, chat layers
- A CHRONICLE schema and synthetic example entries (showing how to
  populate your own CHRONICLE — not real-world banking analyses)
- Sample data corpora (synthetic, demonstration only)
- Authentication and access scaffolding
- Documentation, build tooling, tests

## What's NOT in this repository (CJI)

- The CJI CHRONICLE entries (CHR-001..019 and beyond — real banking
  incident analyses)
- CJI brand surface (cjipro.com marketing site, login flows, etc.)
- CJI partner data (alpha cohort identities, briefings sent to
  specific firms)
- CJI hosted-instance configuration (Cloudflare bindings, WorkOS
  organisation IDs, D1 database UUIDs)
- The CJI brand marks (CJI / CJI Briefing / CJI Reckoner / CJI Sonar
  / CJI Pulse / CJI Lever / CJI Chronicle) — see TRADEMARK.md

## Why the historical lineage is reversed in the narrative

Honestly: Hodos is being distilled out of CJI as the project
matures. CJI came first, as a working banking application; the
patterns inside it are gradually being abstracted into Hodos as a
framework that any vertical could use.

The public framing — "CJI is powered by Hodos" — describes the
intended end-state, where Hodos has its own identity, its own
example applications beyond CJI, its own contributors, and its own
release cadence. That end-state is being earned, not claimed. If
you read this document a year from now and the framing reads
naturally, the work paid off.

## What this means for you

**If you're a contributor to Hodos:** your work goes into the
framework. You will be attributed in the Hodos NOTICE / GitHub
credits. You do NOT gain rights to or attribution in CJI's
CHRONICLE — that is a separate product. See CONTRIBUTING.md.

**If you're a forker:** you can take Hodos and build your own
customer-journey application for any domain (insurance, telecoms,
retail, energy, your own choice). Your application is yours; you
don't owe anything back. Naming rules: see TRADEMARK.md.

**If you're a CJI partner:** nothing in this repository affects
your relationship with CJI. The CJI hosted product, the CHRONICLE
entries you read, the briefings you receive — those are CJI's
concerns and are governed by your CJI-side terms.

## Questions

For anything ambiguous about the CJI/Hodos boundary, email
hello@cjipro.com. The honest answer to "is this thing CJI or
Hodos?" is sometimes "we haven't decided yet" — and that's fine,
just ask.
