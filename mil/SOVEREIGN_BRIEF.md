# SOVEREIGN BRIEF
## Market Intelligence Layer — Trust Manifesto

**Classification:** Sovereign Private
**Version:** 1.0
**Owner:** Hussain Ahmed
**Created:** 2026-03-28
**Status:** Active

---

## ARTICLE ZERO

> "This system shall prioritise the expression of its own ignorance over the
> delivery of any unverified certainty. Honesty in calibration is the only
> product; all inferences are secondary to the preservation of the Designed
> Ceiling."

Article Zero is the constitutional foundation of MIL. It does not change.
It does not yield to leadership requests. It does not yield to demo pressure.
It does not yield to what the model believes it knows.

Every component of MIL — every agent, every scraper, every training pair,
every Inference Card — answers to Article Zero before it answers to anything else.

---

## THE AIR-GAP DEFINITION

MIL is sovereign. The Air-Gap is not a limitation — it is the most strategically
important feature in the architecture.

**What MIL is:**
- A proactive Early Warning System built on 100% public market signals
- A standalone intelligence engine operating on local sovereign hardware
- An Agentic Conscience for the App Refresh
- An external complement to CJI Pulse's internal telemetry

**What MIL is not:**
- A social listening tool
- A self-healing production system
- An autonomous decision engine
- A system with access to internal banking systems, customer records, or PII

**The Air-Gap in technical terms:**

```
MIL contains zero import statements referencing internal banking systems.
CJI Pulse contains zero import statements referencing MIL modules.

The only permitted data crossing:
  MIL writes → mil/outputs/mil_findings.json
  CJI Pulse reads → mil/outputs/mil_findings.json

Nothing else crosses the boundary. Ever.
```

This is Nico Zhao's Law — Zero Entanglement. It is enforced by the build
validator as a hard failure, not a warning.

---

## ZERO ENTANGLEMENT — MIL IMPORT RULE

**Encoded in MIL_SCHEMA.yaml. Enforced by build validator.**

```
No file under mil/ may import from:
  pulse/, poc/, app/, dags/, or any internal data module.

No file outside mil/ may import from mil/ directly.

Permitted data exchange:
  Read mil/outputs/mil_findings.json only.

Violation: fails build validator. Not a warning. A hard failure.
```

The adapter at `app/pages/07_mil.py` is a routing shim only. It contains
zero MIL logic and zero imports from internal data modules. It calls into
`mil/command/app.py`. The information flow is one direction: MIL out,
never internal in.

---

## IDENTITY SHIELD — P5 EXTENSION

The client (TAQ Bank) must never appear in MIL outputs, CHRONICLE entries,
scraper config, signal queries, training pairs, or any MIL file.

This is an extension of the CJI Pulse P5 rule
(`client_identity_sealed_taq_only`) to the MIL sovereign system.

**Scope:**
- `mil/config/apps_config.yaml` — client does not appear in competitor list
- `mil/CHRONICLE.md` — if any entry involves the client, substitute TAQ Bank
- Signal queries — no search terms referencing the client
- Training pairs — no client references in Input, Reasoning Chain, or Recommended Action
- All MIL outputs and Inference Cards — client does not surface

**Response to violation:**
WARN_P5 emitted. Finding held. Human review required before release.

---

## THE DESIGNED CEILING

The Designed Ceiling is the most strategically important feature in the blueprint.
It is not a limitation. It is the honest expression of calibrated ignorance.

When MIL reaches the boundary of what public data alone can confirm, it stops
and says so explicitly:

> "I have detected a [CAC score]% confidence match to the [CHRONICLE entry]
> failure pattern on the [journey] journey. To confirm whether this is affecting
> our vulnerable customer cohort, I require access to Internal HDFS Data.
> Request Phase 2."

Every time a stakeholder clicks the Exit Strategy button, they are registering
a demand for Phase 2. Every click is logged with timestamp, finding_id, and
user_id to `mil/data/click_log.jsonl`. This log is never deleted. It is the
Phase 2 business case — a documented record of demand, not a projection.

---

## DYNAMIC BLIND SPOT REGISTER

Everything the system cannot see. Updated as new blind spots are discovered.
Agents must reference this register when constructing Inference Cards.

| # | Blind Spot | Impact | Status | Review |
|---|-----------|--------|--------|--------|
| BS-001 | Internal telemetry | Cannot confirm whether external signals reflect our internal journey performance | Permanent — Phase 2 integration required | N/A |
| BS-002 | Customer identity | Signals are anonymous — cannot link complaint to cohort (age, vulnerability) | Permanent in Phase 1 | N/A |
| BS-003 | Transaction-level data | App Store reviews do not specify which transaction type failed | Permanent in Phase 1 | N/A |
| BS-004 | iOS vs Android split | Platform split not always visible in review signals | Partial — version field in App Store mitigates | Ongoing |
| BS-005 | Facebook public page signals | Architecture ready. Scraping method unconfirmed. Demographic gap in 35-55 complaint data until resolved. | OPEN — deferred to Day 30 review alongside QLoRA gate | Day 30 |
| BS-006 | TAQ Bank (client) signals | Client excluded from monitoring per P5 Identity Shield. Any historical TAQ Bank pattern is masked before storage. | Permanent | N/A |
| BS-007 | Non-English signals | Reddit and Twitter signals in non-English languages not classified | Low impact for UK-focused competitors | Monitor |
| BS-008 | HSBC CHR-003 root cause | HSBC August 2025 outage root cause not publicly confirmed. Similarity matching carries confidence penalty. | OPEN — Hussain to confirm if additional source available | CHRONICLE review |
| BS-009 | CHRONICLE twitter_archive fields | Twitter Premium+ archive search pending for all three CHRONICLE entries | OPEN — action at earliest opportunity | Weekly review |

---

## HUMAN OPERATING MODEL

The Clark Protocol and P1 countersign rules require a daily rhythm.
Without it, ownership becomes ambiguous and escalation fails silently.

### Daily Rhythm

| Time | Who | Action |
|------|-----|--------|
| 07:00 | Journey Owner | Reads Morning Briefing. Flags any finding needing same-day investigation. |
| 07:30 | Hussain Ahmed | Reviews P1 queue. Countersigns or challenges. Must action within 4-hour window. |
| 09:00 | Journey Owner | Confirms investigation ownership for any flagged items. Assigns or defers — logged. No unowned investigations. |
| 11:00 | System (auto) | P1 auto-downgrade check. If no human has reviewed a P1 by 11:00, auto-downgrade to P2 with EXP_UNREVIEWED flag. Hussain receives direct alert. |
| 17:00 | Hussain Ahmed | Reviews Exit Strategy click log. Notes which findings hit the Designed Ceiling. Every click is a Phase 2 demand signal. |

### Weekly Rhythm

| When | Who | Action |
|------|-----|--------|
| Every Friday | Hussain Ahmed | CHRONICLE review — any new verified public banking failures to add? |
| Every Friday | Hussain Ahmed | Weekly digest reviewed. Unanchored Signals digest reviewed — candidates for new CHRONICLE entries. |
| Every Friday | Programme | Something deployed, board moved, problem solved. The Friday rule applies to MIL as it does to CJI Pulse. |

**Hard rule:** The system never escalates itself. It only records that an escalation was missed.
Human ownership of every action is non-negotiable.

---

## OWNERSHIP REGISTER

Every component has a named owner. Components without owners get abandoned.

| Component | Owner |
|-----------|-------|
| CHRONICLE.md | Hussain Ahmed |
| MIL_SCHEMA.yaml | Hussain Ahmed |
| SOVEREIGN_BRIEF.md | Hussain Ahmed |
| Hypothesis Library | Hussain Ahmed |
| CAC Calibration | Hussain Ahmed |
| Voice Intelligence (Harvester) | Hussain Ahmed |
| Morning Briefing | Hussain Ahmed |
| P1 Countersign Queue | Hussain Ahmed |
| Exit Strategy Click Log | Hussain Ahmed |
| CHRONICLE Weekly Review | Hussain Ahmed |
| Unanchored Signals Digest | Hussain Ahmed |

---

## PUBLISHING SOVEREIGNTY STATEMENT

MIL publishes sanitised findings output only.

No raw signals, no training data, no internal telemetry, and no customer data
are published. Every published finding carries its confidence score, blind spot
register, and CHRONICLE trace.

The inference engine remains sovereign and local. The published static page
(`publish.py` → GitHub Pages + Cloudflare Access) is the external-facing surface.
The local dashboard (port 8501) is the internal surface. Two surfaces, one
underlying findings file: `mil/outputs/mil_findings.json`.

---

## QLORA GATE — POST-DAY 30

QLoRA fine-tuning is not in the 30-day build window. Five conditions must all
pass before `mil/specialist/train_qwen.py` is executed. Owner: Hussain Ahmed sign-off.

| # | Gate Condition | Status |
|---|---------------|--------|
| 1 | 14+ days real signal data collected (measured, not assumed) | PENDING |
| 2 | Synthetic pairs validated against 3 or more real findings (human-reviewed) | PENDING |
| 3 | CAC weights calibrated on real corpus (not before first 30 days of real data) | PENDING |
| 4 | Adversarial Attacker Agent passes evaluation (`mil/specialist/adversarial_attacker.py`) | PENDING |
| 5 | Collision Lock confirmed active (`mil/specialist/collision_lock.py`) | PENDING |

---

## FACEBOOK SCRAPING DECISION — DEFERRED

Facebook public page scraping is architecturally complete (stub in
`mil/harvester/voice_intelligence_agent.py`). The scraping method is
unconfirmed. Revisit at Day 30 review alongside QLoRA gate conditions.

Options under consideration:
- Playwright/headless browser (reliable, adds browser dependency)
- `facebook-scraper` library (lighter, potentially fragile)

Until resolved: BS-005 in Blind Spot Register is active. The 35-55
demographic gap in complaint data is acknowledged and logged.

---

*Build the honest version. Not the impressive one.*
*— CJI Pulse Canonical Statement 22*
