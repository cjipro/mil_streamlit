# MIL-165 — paste into Jira UI

**Project:** MIL
**Issue Type:** Task
**Status target:** BACKLOG (To Do)

---

## Summary

Public /journey page on cjipro.com — provenance trail sourced from MIL planning docs

---

## Description

### Concept

A public "let's learn together" page on cjipro.com sourced from MIL planning documents. Three movements, one page:

1. **How it was conceived** — drawn from original MIL planning documents (manifests, schemas, governance principles, the SOVEREIGN_BRIEF Article Zero / Air-Gap / Blind Spot Register thinking, Day-90 vision)
2. **What's been achieved** — measured against original plans (Phase 0/1/2 shipped, MIL pipeline live, briefings live, auth stack live, alpha partners onboarded)
3. **Where it's heading** — open questions, the OSS release, the year ahead

### Voice

First-person plural ("we"), confessional, no marketing veneer, no "lessons learned" corporate gloss. Reads like a working notebook a stranger is welcome to look over. Rhymes with `/engineering` page (MIL-160) — confessional for AI/Data, clinical for Security/Software.

### Audience

Layered. Single page, three readers find their thread:
- Prospective bank customers (credibility / seriousness signal)
- Prospective OSS forkers (technical credibility / decision provenance)
- Prospective consulting leads (how Hussain thinks and works)

### Source documents — MIL ONLY

Pulse internals (TAQ Bank, P5 governance, OBRE/REGS audit findings, internal client systems, AF-001..004) explicitly OUT of scope and stay private.

In scope:
- `mil/SOVEREIGN_BRIEF.md` — Article Zero / Air-Gap / Blind Spot Register manifesto
- `mil/MIL_SCHEMA.yaml` — canonical MIL schema
- `mil/CHRONICLE.md` — banking failure ledger
- `mil/config/apps_config.yaml` — full signal stack
- `manifests/system_manifest.yaml` (MIL components only)
- `manifests/data_strategy_v2.md` (MIL-relevant sections only)
- `manifests/governance_principles.yaml` (MIL-relevant only)
- Day-90 vision quote from CLAUDE.md
- Phase 0/1/2 ticket completion records

### Output

`mil/publish/site/journey/index.html` — new directory under existing site root. Published via `mil/publish/publish_site.py` (MIL-50 infra).

---

## Strategic open questions (parked — log only, decide later)

Today's session (2026-04-30) and yesterday's vision-lock (2026-04-29) raised these. They are PARKED, not blocking the page build.

### 1. License
Apache 2.0 strongly recommended. Today's discussion confirmed: "open source enough" = OSI-approved (Apache/MIT), NOT BSL/SSPL/MongoDB-style. Hyperscaler-appropriation risk not real for this codebase; commercial-gate complexity hurts adoption + credibility. Output: `LICENSE` + `NOTICE` at repo root.

### 2. Trademark policy
CJI / CJI Briefing / CJI Sonar / CJI Reckoner / CJI Pulse / CJI Lever / CJI Chronicle stay proprietary. Mozilla-style trademark doc. Forkers can use the engine; customer-facing surfaces must rebrand. Allowed: "Powered by CJI", "CJI-compatible". Disallowed: re-shipping a fork as "CJI X". Trademark registration tracked separately (MIL-97, IP counsel, money-gated).

### 3. CHRONICLE split
Three options:
- **(a) Engine + banking CHR-001..019 free / future Domain Packs paid** (recommended — banking is loss-leader, future verticals recurring revenue)
- **(b) Engine free / ALL CHRONICLE entries paid** (high friction, fork is empty)
- **(c) Engine + 5 sample entries free / full CHRONICLE paid** (compromise)

### 4. Partner model
- **Contributor** — submits CHRONICLE entries, gets attribution, no money
- **Domain Pack author** — ships taxonomy + calibration + seed CHRONICLE for new vertical, retains rights, revenue share if pack is paid
- **Reseller / consultant** — stands up CJI for clients, branded under their banner, revenue share

Hybrid recommended, staged: Contributor now → Domain Pack author after first non-banking pack → Reseller after Phase 2 forkability proven.

### 5. Hosted vs forkable — REFRAMED 2026-04-30

End-state: OSS repo (codename TBC) is upstream; **cjipro.com is the canonical fork and face of the business.**

Build order:
- Build cjipro.com as working SaaS first (primary track, revenue-generating)
- OSS extraction in parallel — fully forkable, no commercial gate
- Once cjipro.com works, retroactively present it as if it were forked from upstream TBC
- Anyone can then fork TBC and get the same engine cjipro.com runs on

Customer self-selection:
- Bank wants self-host / on-prem / regulator-friendly → fork OSS
- Bank wants it-just-works / someone-to-call → subscribe to cjipro.com

Consultant goal (end-2026): credibility through working artefact (cjipro.com + working OSS fork-of-itself), not blog-series-shipped-early.

---

## OSS release operational questions (parked)

### 6. OSS release timing
Public now (build in the open, every commit visible, maximally credible) vs public at release (clean drop, controllable narrative). Today `cjipro/mil_streamlit` is already public on GitHub — de facto in "public now" territory.

### 7. Story-logging mechanism — partly addressed by THIS ticket
Pending fuller answer:
- (a) curated artefact published when product is cloneable
- (b) private blog/Notion until ready
- (c) `docs/journey/` directory in repo, git history is the log
- (d) public `/journey` page on cjipro.com (THIS TICKET — partial answer)

### 8. Panel composition for OSS strategy
Today's discussion deferred the originally-proposed 20-seat panel. Strategy is mostly locked. Panel reserved for specific future decisions (CHRONICLE split lock-in, Domain Pack taxonomy, partner-model staging).

### 9. Revenue streams to evaluate
- Consultancy / professional services (Hussain end-2026 goal — primary career path)
- Hosted SaaS at cjipro.com (primary build track)
- CHRONICLE Domain Packs (insurance, telecoms, retail, etc.)
- Certified support contracts
- Training / certification programmes
- Trademark licensing
- Marketplace fees on third-party Domain Packs
- Embedded enterprise features (open-core model)

---

## Page-specific questions resolved

- Audience: layered, all three readers
- Tone: confessional, rhymes with /engineering
- Source filter: MIL planning docs only (Pulse internals private)
- Voice: "let's learn together"
- Sections: How conceived / What's been achieved / Where it's heading

## Page-specific questions still open

### 10. Cadence and source for entries
Curated-from-planning-docs-only vs curated + fresh-going-forward vs fully-living-document.

### 11. Depth and density
3-5 deep narrative entries vs 10-15 terse log entries vs hybrid (deep narrative for movements 1-3 + shorter notes section).

### 12. Build sequence
Outline first → review → HTML (recommended — tone is load-bearing) vs first-draft-HTML → iterate.

### 13. Update mechanism
Manually-edited HTML in `mil/publish/site/journey/index.html` vs generated-from-source. Manual recommended for v1.

---

## Acceptance criteria (when built)

- Page lives at `cjipro.com/journey`
- Three movements present (How conceived / What's been achieved / Where it's heading)
- Tone verified to match `/engineering` page voice
- Sources cited inline where appropriate
- No Pulse-internal material leaks (filter pass before publish)
- Mobile-readable, matches existing site chrome (Source Serif 4 + Inter, MIL-136)
- Linked from `cjipro.com` landing page footer

---

## Related tickets

- MIL-160 — engineering page (voice precedent + clinical/confessional dual-tone pattern)
- MIL-127 — doc split (companion work for OSS legibility)
- MIL-110 — OSS engine vs hosted reference (strategic context, due for rewrite under new vision)
- MIL-97 — trademark registration (IP counsel, money-gated)

---

## Status

BACKLOG. Build pending — not started. Filed 2026-04-30 to log open questions and capture vision-lock context before it ages.
