# MIL CHRONICLE
## Immutable Banking Failure Ledger

**Classification:** Sovereign Private
**Owner:** Hussain Ahmed
**Created:** 2026-03-28
**Update cadence:** Weekly — every Friday review
**Immutability rule:** Existing entries may not be amended. New entries append only.
**Article Zero applies:** Every entry must trace to verified public sources.
**REVIEW STATUS:** PARTIALLY APPROVED — 2026-03-28 Hussain Ahmed sign-off.
- CHR-001 (TSB 2018): APPROVED — inference may trace to this entry.
- CHR-002 (Lloyds 2025): APPROVED WITH CAP — confidence_score capped at 0.6, verified_facts: PARTIAL.
- CHR-003 (HSBC 2025): INFERENCE HOLD — inference_approved: false. Affected count unconfirmed. Confidence_score: 0.4.

---

> Every inference made by MIL must trace back to a CHRONICLE entry.
> If it cannot be traced — it does not get trained on, and it does not get reported.
> Unverified fields are marked `[REVIEW REQUIRED]`. No inference may use an unverified field.

---

## CHRONICLE ENTRY SCHEMA

Each entry carries:
- `chronicle_id` — unique immutable identifier
- `date` — incident date or window
- `bank` — institution name
- `incident_type` — classification tag
- `public_sources[]` — verified public sources (name + approximate date)
- `verified_facts[]` — facts confirmed from official or named sources
- `causal_chain` — what led to what (structured)
- `outcome` — regulatory, financial, reputational
- `confidence` — HIGH / MEDIUM / LOW per dimension
- `review_flags[]` — fields requiring Hussain sign-off
- `twitter_archive` — public reaction data from Premium+ full archive search

---

## ENTRIES

---

### CHR-001 — TSB Bank IT Migration Failure

```yaml
chronicle_id: CHR-001
date: "2018-04-22"
inference_approved: true
confidence_score: 1.0
date_window: "2018-04-22 to 2018-12-01"
bank: "TSB Bank"
incident_type: "core_banking_migration_failure"
journey_tags:
  - J_LOGIN_01       # 1.9M customers locked out
  - J_PAY_01         # payment failures
  - J_SERVICE_01     # account access failure

verified_facts:
  - "Migration date: 22 April 2018. Big bang cutover of ~5.2M customers."
  - "Platform: Proteo4UK, developed by SABIS (subsidiary of Sabadell, TSB's Spanish parent)."
  - "1.9 million customers locked out of their accounts immediately post-cutover."
  - "Some customers could view other customers' account details — data confidentiality failure."
  - "225,492 complaints logged between 22 April 2018 and 7 April 2019."
  - "33,000+ complaints in the second week — more than 10x normal complaint volume."
  - "4,424 defects were open at go-live (of 34,671 total logged since October 2017)."
  - "840 severity 1 or 2 defects remained open on 10 April 2018, 12 days before go-live."
  - "SABIS relied on 85 sub-suppliers. TSB had not ensured SABIS's supplier management was compliant with Group Outsourcing policy."
  - "Two data centres built to support Proteo4UK were specified to be identical but were configured inconsistently."
  - "Full resolution to business-as-usual: December 2018 — approximately 8 months of disruption."
  - "CEO Paul Pester resigned 4 August 2018."
  - "Slaughter and May independent review published 19 November 2019."
  - "FCA fine: £29,750,000. PRA fine: £18,900,000. Combined: £48,650,000. Issued December 2022."
  - "Former CIO Carlos Abarca fined £81,620 by PRA on 13 April 2023 — PRA's first-ever SMCR conduct enforcement."

causal_chain:
  - "TSB sold off from Lloyds (2013) → continued paying ~£10M/month in platform licence fees to Lloyds"
  - "Cost pressure drove accelerated migration timeline"
  - "Big bang approach chosen — all 5.2M customers moved simultaneously in one weekend"
  - "Platform built by SABIS (85 sub-suppliers) — outsourcing governance insufficient"
  - "TSB failed to adequately assess SABIS's capability to manage large-scale UK delivery"
  - "34,671 defects logged during build; 4,424 still open at go-live"
  - "Two data centres inconsistently configured despite specification requiring identical setup"
  - "Platform fails under real customer load — spike in volumes beyond contingency resources"
  - "1.9M customers locked out; some customers see other customers' account data"
  - "Complaint volume overwhelms support infrastructure"
  - "CEO resigns August 2018"
  - "FCA/PRA joint enforcement: £48.65M fine, December 2022"
  - "Former CIO individually fined under SMCR, April 2023"

outcome:
  regulatory: "£48.65M combined FCA/PRA fine. First individual SMCR enforcement action by PRA."
  reputational: "Sustained brand damage. Parliamentary Treasury Committee hearings. CEO resignation."
  financial: "TSB provisioned approximately £330M for customer remediation and operational costs."
  customer: "225,492 complaints. 8 months of degraded service."

pattern_signals:
  - "Telemetry showed migration completion; customer lockouts were not visible in system metrics"
  - "Leadership acted on reported uptime while customers were locked out — inference gap confirmed"
  - "Classic Vane pattern: stable internal metrics, catastrophic customer reality"
  - "The completion rate obituary arrived 8 months after the sentiment spike"

mil_relevance:
  - "Primary architectural case study. Defines what MIL is built to prevent."
  - "CHR-001 is the reference anchor for J_LOGIN_01, J_PAY_01, and J_SERVICE_01 pattern matching."
  - "Any competitor signal matching big-bang migration + complaint spike + latency anomaly should auto-reference CHR-001."

confidence:
  dates: HIGH
  impact_figures: HIGH
  root_cause: HIGH
  regulatory_outcome: HIGH

public_sources:
  - source: "TSB Board — Slaughter and May Independent Review press release"
    date: "2019-11-19"
  - source: "Bank of England / PRA Final Notice, TSB Bank plc"
    date: "2022-12-20"
  - source: "PRA Enforcement Notice — Carlos Abarca"
    date: "2023-04-13"
  - source: "Computer Weekly — multiple articles covering migration and fine"
    date: "2018–2023"
  - source: "FCA/PRA joint enforcement statement"
    date: "2022-12-20"
  - source: "The Register — Slaughter and May findings"
    date: "2019-11-19"
  - source: "IT Pro — CEO resignation coverage"
    date: "2018-08-04"

twitter_archive:
  status: "PENDING_HUSSAIN"
  query_window: "2018-04-22 to 2018-04-30"
  suggested_keywords: ["TSB", "TSB bank", "TSB down", "TSB locked out", "TSB app"]
  review_flag: "Hussain to run Premium+ full archive search and supply results"
```

---

### CHR-002 — Lloyds Banking Group — Transaction Data Exposure

```yaml
chronicle_id: CHR-002
date: "2025-03-12"
bank: "Lloyds Banking Group (Lloyds, Halifax, Bank of Scotland)"
incident_type: "api_defect_data_exposure"
inference_approved: true
confidence_score: 0.60
verified_facts_status: PARTIAL
journey_tags:
  - J_SERVICE_01     # transaction data visible to wrong customers
  - J_LOGIN_01       # account access affected

verified_facts:
  - "Date: 12 March 2025. Defect introduced by overnight IT update pushed 11–12 March 2025."
  - "A software defect in the API handling transaction data caused customers to see other customers' transactions."
  - "Up to 447,936 customers across Lloyds, Halifax, and Bank of Scotland were potentially exposed."
  - "114,182 customers actively clicked on and may have viewed detailed transaction data."
  - "Exposed data potentially included account details, National Insurance numbers, and payment references."
  - "Defect identified and resolved within the same day — 12 March 2025."
  - "No customers identified as suffering financial losses."
  - "Lloyds paid £139,000 in compensation to 3,625 customers for distress and inconvenience."
  - "FCA notified within 72 hours. ICO stated it was 'making enquiries'. No final enforcement as of public record."
  - "Parliamentary Treasury Committee wrote to Lloyds describing incident as 'alarming'."
  - "Context: UK Treasury Committee data showed 158 IT failures across major UK banks, January 2023–February 2025, totalling 803+ hours of disruption."

causal_chain:
  - "Overnight IT update deployed 11–12 March 2025"
  - "Software defect introduced in transaction data API layer"
  - "API returns wrong customers' transaction data in mobile app sessions"
  - "447,936 customers potentially exposed; 114,182 actively view affected data"
  - "Some data includes NI numbers, account details, payment references"
  - "Lloyds identifies and resolves defect within same day"
  - "FCA notified within 72 hours; ICO begins enquiries"
  - "Parliament describes incident as 'alarming'"
  - "£139,000 compensation paid to 3,625 customers"
  - "Regulatory investigations open — no final determination as of record date"

outcome:
  regulatory: "FCA and ICO investigations open. No final enforcement action in public record."
  reputational: "Parliamentary criticism. 'Alarming' classification from Treasury Committee."
  financial: "£139,000 compensation to 3,625 customers."
  customer: "447,936 potentially exposed. 114,182 confirmed clicked on affected data."

pattern_signals:
  - "Software update as failure trigger — not migration, not external attack"
  - "API layer as exposure vector — customer data crossed account boundaries"
  - "Same-day resolution but exposure had already occurred"
  - "Vane pattern reversed here: failure was acute, not gradual — but regulatory pressure builds slowly"

mil_relevance:
  - "API-layer defect pattern. Relevant to any competitor signal involving post-update complaints or data visibility issues."
  - "CHR-002 anchors J_SERVICE_01 signals involving 'saw someone else's account' or 'wrong transactions'."
  - "Demonstrates that regulated outcome (ICO/FCA) lags customer-visible harm by weeks to months."

confidence:
  dates: HIGH
  impact_figures: HIGH       # 447,936 and 114,182 from official sources
  root_cause: MEDIUM         # 'software defect' confirmed; deeper technical cause not publicly disclosed
  regulatory_outcome: MEDIUM # Investigations open; no final determination

review_flags:
  - "Root cause is confirmed as 'software defect in API' but HSBC-level technical detail not available. Flag for Hussain: is additional detail available from internal or industry sources?"

public_sources:
  - source: "The Register — Lloyds app glitch exposed transactions to almost 500K users"
    date: "2026-03-27"
  - source: "Computer Weekly — MPs ask Lloyds Bank for more information about 'alarming' breach"
    date: "2025"
  - source: "GB News — Banking app outage update: Lloyds confirms major compensation news"
    date: "2025"
  - source: "Computing.co.uk — Lloyds and Halifax resolve banking glitch after hours of disruption"
    date: "2025-03-12"
  - source: "Meyka / FStech — March 12 incident coverage"
    date: "2025-03"

twitter_archive:
  status: "PENDING_HUSSAIN"
  query_window: "2025-03-12 to 2025-03-14"
  suggested_keywords: ["Lloyds app", "Lloyds bank down", "Lloyds wrong account", "Halifax app", "Halifax transactions"]
  review_flag: "Hussain to run Premium+ full archive search and supply results"
```

---

### CHR-003 — HSBC UK — App and Online Banking Outage

```yaml
chronicle_id: CHR-003
date: "2025-08-27"
bank: "HSBC UK (and First Direct)"
incident_type: "app_online_banking_outage"
inference_approved: false
confidence_score: 0.40
affected_count: UNCONFIRMED
journey_tags:
  - J_LOGIN_01     # customers unable to access accounts
  - J_SERVICE_01   # app and online banking unavailable

verified_facts:
  - "Date: 27 August 2025. Outage began approximately 11:00 BST."
  - "HSBC UK customers unable to access accounts via mobile app and online banking."
  - "First Direct (HSBC-owned) also affected."
  - "Error code ERR03 displayed to customers, or 'information unavailable' messages."
  - "HSBC posted first public acknowledgement at approximately 11:45 BST."
  - "Services restored the same afternoon. Duration approximately 5 hours."
  - "Over 4,000 complaints logged on DownDetector within the first hour."
  - "HSBC issued an apology and confirmed services restored."
  - "No customer financial losses reported."
  - "No specific FCA or PRA enforcement action publicly documented for this incident."
  - "HSBC submitted correspondence to Treasury Committee dated 30 April 2025 regarding IT failures — content not public."

blind_spots:
  - "Actual affected customer count not publicly disclosed by HSBC"
  - "Root cause not publicly disclosed by HSBC — ERR03 error code unexplained"

unverified_fields:
  customer_count:
    status: "REMOVED — figure previously cited (14.5M) was HSBC's total customer base, not a confirmed affected count. Field set to UNCONFIRMED per Hussain review 2026-03-28."
  root_cause:
    claim: "Authentication or access control failure; possible system upgrade"
    source: "Analyst speculation in secondary sources"
    status: "[REVIEW REQUIRED] — HSBC did not publicly disclose root cause. ERR03 error code not officially explained. Causal mechanism is UNCONFIRMED in public record."

causal_chain:
  - "~11:00 BST 27 August 2025: HSBC app and online banking becomes inaccessible"
  - "ERR03 errors displayed to customers attempting to log in"
  - "First Direct (HSBC subsidiary) also affected — suggests shared infrastructure component"
  - "4,000+ DownDetector reports within first hour"
  - "HSBC acknowledges publicly at 11:45 BST"
  - "Services restored same afternoon — approximately 5 hours total"
  - "HSBC issues public apology"
  - "Root cause: NOT DISCLOSED PUBLICLY"
  - "[REVIEW REQUIRED] Causal chain below the acknowledgement step is inferred not confirmed"

outcome:
  regulatory: "No specific FCA/PRA action publicly documented. General FCA scrutiny of bank IT resilience ongoing."
  reputational: "Negative press. DownDetector spike. No long-term reputational assessment available."
  financial: "No compensation figures published."
  customer: "Impact scale UNCONFIRMED — see unverified_fields.customer_count above."

pattern_signals:
  - "ERR03 error pattern — authentication/access failure class"
  - "Simultaneous app + online banking failure suggests shared auth or API gateway component"
  - "DownDetector as earliest signal source — confirmed first mover role"
  - "~5 hour duration — shorter than TSB/Lloyds incidents but same access denial pattern"

mil_relevance:
  - "CHR-003 anchors J_LOGIN_01 patterns for HSBC-competitor signal matching."
  - "ERR03 type errors (access denied, information unavailable) should cross-reference CHR-003."
  - "DownDetector as first mover confirmed — validates trust_weight: 0.95 assignment."
  - "NOTE: Root cause is unconfirmed. CAC similarity matching against CHR-003 should apply a confidence penalty until root cause is established. Flag in inference output."

confidence:
  dates: HIGH          # 27 August 2025 confirmed across multiple sources
  impact_figures: LOW  # 14.5M is total customer base, not affected count
  root_cause: LOW      # HSBC did not disclose — UNCONFIRMED
  regulatory_outcome: LOW  # No enforcement action documented

review_flags:
  - "CRITICAL: Customer impact count is unconfirmed. Do not use 14.5M figure in any MIL inference or output."
  - "Root cause is not established in public record. CHR-003 similarity matching carries MEDIUM confidence penalty until root cause is known."
  - "Hussain: is any non-public or industry source available to establish root cause?"

public_sources:
  - source: "ITV News — HSBC resolves online banking and app outage"
    date: "2025-08-27"
  - source: "LBC — Major UK banking app down as thousands left without account access"
    date: "2025-08-27"
  - source: "Yahoo Finance / HSBC UK statement — HSBC apologises"
    date: "2025-08-27"
  - source: "Finextra — Customers fume as HSBC goes down"
    date: "2025"
  - source: "PYMNTS.com — HSBC Customers Frustrated Following Website and App Outage"
    date: "2025"
  - source: "Karmactive.com — NOTE: secondary source; 14.5M figure is total customer base not confirmed affected count"
    date: "2025-08"

twitter_archive:
  status: "PENDING_HUSSAIN"
  query_window: "2025-08-27 to 2025-08-28"
  suggested_keywords: ["HSBC down", "HSBC app", "HSBC not working", "First Direct down", "ERR03"]
  review_flag: "Hussain to run Premium+ full archive search and supply results"
```

---

### CHR-004 — Barclays App Friction Pattern Analysis

```yaml
chronicle_id: CHR-004
date: "2026-04-02"
inference_approved: true
confidence_score: 0.50
date_window: "2025-01-01 to 2026-04-02"
bank: "Barclays"
incident_type: "app_friction_pattern_analysis"

summary: >
  MIL enrichment of 817 Barclays App Store and Google Play reviews (schema v3,
  claude-haiku-4-5-20251001) reveals a persistent low-level friction pattern.
  83.6% of reviews are positive (Positive Feedback), but the remaining 16.4%
  cluster around Feature Broken (42), App Crashing (16), and Slow Performance (9).
  Severity distribution: P0=18, P1=20, P2=779. No acute outage signal detected.
  Pattern is consistent with sustained feature debt rather than a discrete incident.

signal_summary:
  total_records: 817
  positive_feedback_pct: 83.6
  p0_count: 18
  p1_count: 20
  p2_count: 779
  top_issue_types:
    - "Feature Broken: 42"
    - "App Crashing: 16"
    - "Slow Performance: 9"
    - "App Not Opening: 8"
    - "Payment Failed: 7"
    - "Notification Issue: 7"
    - "Customer Support Failure: 6"
  top_journeys:
    - "Make a Payment: 28"
    - "Transfer Money: 28"
    - "Check Balance or Statement: 27"
    - "Manage Card: 17"
    - "Get Support: 29"

mil_relevance:
  - "Barclays is the client's primary brand competitor — all signals are self-intelligence."
  - "No CHR-001/TSB-class collapse pattern detected. This is maintenance-level friction, not pre-incident signal."
  - "Payment Failed (7) and Transfer Failed (4) warrant monitoring — low volume but high severity journey."
  - "Feature Broken (42) is the dominant complaint — consistent with incremental release debt."
  - "CHR-004 provides Barclays-specific baseline for future regression detection."

inference_notes:
  - "CAC ceiling triggers on Barclays are expected given CHR-001/CHR-002 sim scores."
  - "Do not conflate Barclays friction with competitor-class risk — this is YOUR APP signal."
  - "Confidence capped at 0.50 pending Hussain review and approval."

confidence:
  dates: HIGH
  impact_figures: HIGH
  root_cause: MEDIUM
  regulatory_outcome: N/A

review_flags:
  - "PENDING HUSSAIN: Review enrichment results and approve inference_approved=true if satisfied."
  - "Payment + Transfer journey signals are low volume — monitor for trend, not incident."
  - "Feature Broken cluster may warrant CHR cross-reference after 30 days of trend data."

public_sources:
  - source: "App Store reviews — app_store_barclays_enriched.json (79 records, claude-haiku-4-5-20251001)"
    date: "2026-04-02"
  - source: "Google Play reviews — google_play_barclays_enriched.json (738 records, claude-haiku-4-5-20251001)"
    date: "2026-04-02"
```

---

## HUSSAIN REVIEW CHECKLIST

Before any MIL inference traces to these entries, Hussain must confirm:

| Item | Chronicle | Status |
|------|-----------|--------|
| CHR-001 facts verified | TSB 2018 | [x] APPROVED — 2026-03-28 Hussain |
| CHR-001 Twitter archive populated | TSB 2018 | [ ] PENDING_HUSSAIN |
| CHR-002 facts verified | Lloyds 2025 | [x] APPROVED WITH CAP — confidence_score 0.6, PARTIAL — 2026-03-28 Hussain |
| CHR-002 root cause — any additional source available? | Lloyds 2025 | [ ] Open |
| CHR-002 Twitter archive populated | Lloyds 2025 | [ ] PENDING_HUSSAIN |
| CHR-003 customer impact count confirmed | HSBC 2025 | [x] REMOVED — set to UNCONFIRMED — 2026-03-28 Hussain |
| CHR-003 root cause confirmed | HSBC 2025 | [ ] UNCONFIRMED — inference_approved: false |
| CHR-003 Twitter archive populated | HSBC 2025 | [ ] PENDING_HUSSAIN |
| **M2 countersign** | NatWest MIL-F-20260402-047 | [x] COUNTERSIGNED — Hussain Ahmed 2026-04-02 |
| CHR-004 enrichment review | Barclays 2026 | [x] APPROVED — Hussain Ahmed 2026-04-02 |

---

## WEEKLY REVIEW PROTOCOL

Every Friday:
1. Review for any new verified public banking failures to add
2. Review Unanchored Signals digest — candidates for new CHRONICLE entries
3. Twitter archive fields — action any pending searches
4. Update REVIEW CHECKLIST above as items are confirmed

**New entries are appended only. Existing entries are never amended.**
**This is the immutability rule. It does not yield to convenience.**
