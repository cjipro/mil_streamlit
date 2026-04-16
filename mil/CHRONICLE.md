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
incident_type: "app_platform_refresh_outage"
inference_approved: true
confidence_score: 0.55
confidence_score_note: "Capped at 0.55 — root cause inferred from pattern evidence, not officially disclosed by HSBC. Hussain approved 2026-04-09."
affected_count: UNCONFIRMED
journey_tags:
  - J_LOGIN_01     # customers unable to access accounts
  - J_SERVICE_01   # app and online banking unavailable

verified_facts:
  - "Date: 27 August 2025. Outage began approximately 11:00 BST."
  - "HSBC UK customers unable to access accounts via mobile app and online banking."
  - "First Direct (HSBC-owned) also affected — shared infrastructure confirmed."
  - "Error code ERR03 displayed to customers, or 'information unavailable' messages."
  - "HSBC posted first public acknowledgement at approximately 11:45 BST."
  - "Services restored the same afternoon. Duration approximately 5 hours (resolved ~15:15 BST)."
  - "DownDetector peak: 4,765 reports at 11:45 BST. Over 4,000 within first hour."
  - "HSBC issued an apology and confirmed services restored."
  - "No customer financial losses reported."
  - "No specific FCA or PRA enforcement action publicly documented for this incident."
  - "HSBC underwent an 18-month mobile app redesign — described as biggest overhaul since app launch in 2012. Rolled out to all 7M registered UK mobile banking customers by end of May 2025."
  - "Post-redesign app updates continued through June 2025 (v3.57.0, v3.58.4, v3.59.0)."
  - "GlobalData analysis linked outage to 'legacy infrastructure fragility in digital banking' exposed by digital transformation activity."
  - "HKMA ruled out cyberattack — confirmed internal system problem."
  - "HSBC had 32 IT incidents totalling 176 hours of downtime between Jan 2023 and Feb 2025 (FCA data)."
  - "HSBC submitted correspondence to Treasury Committee dated 30 April 2025 regarding IT failures — content not public."

blind_spots:
  - "Actual affected customer count not publicly disclosed by HSBC"
  - "Specific app version or backend deployment that triggered ERR03 not confirmed"
  - "HSBC did not issue a post-incident technical report"

unverified_fields:
  customer_count:
    status: "REMOVED — figure previously cited (14.5M) was HSBC's total customer base, not a confirmed affected count. Field set to UNCONFIRMED per Hussain review 2026-03-28."
  root_cause:
    claim: "Legacy authentication/access control infrastructure stressed by post-redesign deployment activity"
    source: "Inferred from: GlobalData analysis + 18-month app redesign timeline + ERR03 auth failure pattern + First Direct shared infrastructure failure"
    status: "INFERRED — not officially disclosed. Confidence capped at 0.55. Approved by Hussain 2026-04-09."

causal_chain:
  - "2023–2025: HSBC undertakes 18-month mobile app redesign — biggest overhaul since 2012"
  - "End of May 2025: redesigned app fully rolled out to 7M registered UK mobile customers"
  - "June 2025: continued post-launch updates (v3.57, v3.58, v3.59)"
  - "27 August 2025 ~11:00 BST: app and online banking becomes inaccessible — ERR03 errors"
  - "First Direct (HSBC subsidiary on shared infrastructure) also fails simultaneously"
  - "ERR03 pattern consistent with authentication or access control layer failure"
  - "GlobalData: failure exposes 'legacy infrastructure fragility' under digital transformation pressure"
  - "4,765 DownDetector peak at 11:45 BST — DownDetector as first public signal"
  - "HSBC acknowledges publicly 11:45 BST"
  - "Services restored ~15:15 BST — approximately 5 hours total"
  - "HSBC apology issued. Root cause not disclosed publicly."
  - "[INFERRED] New app layer on legacy auth infrastructure — same failure class as CHR-001 (TSB), different scale"

outcome:
  regulatory: "No specific FCA/PRA action publicly documented for this incident. FCA general scrutiny of bank IT resilience ongoing. HSBC accumulated 176 hours downtime 2023–2025."
  reputational: "Negative press. Parliamentary scrutiny of banking IT resilience. DownDetector spike."
  financial: "No compensation figures published."
  customer: "Impact scale UNCONFIRMED — DownDetector peak 4,765 reports. Actual count not disclosed."

pattern_signals:
  - "App platform refresh as failure trigger — same class as TSB migration (CHR-001), smaller scale"
  - "ERR03 error = authentication/access control failure class"
  - "Simultaneous app + online banking + First Direct failure = shared backend infrastructure"
  - "DownDetector as earliest signal source — confirms trust_weight: 0.95 assignment"
  - "Legacy infrastructure stressed by new platform rollout — Vane pattern: internal metrics stable, customers locked out"
  - "5-hour duration — contained but significant"

mil_relevance:
  - "CHR-003 now anchors J_LOGIN_01 and J_SERVICE_01 patterns for all competitors."
  - "ERR03-class errors (access denied, information unavailable, authentication failure) should cross-reference CHR-003."
  - "Platform refresh as outage trigger — any competitor running major app updates warrants CHR-003 similarity check."
  - "DownDetector first mover role confirmed — validates trust_weight: 0.95."
  - "Confidence capped at 0.55 — inference weight should reflect inferred (not confirmed) root cause."

confidence:
  dates: HIGH          # 27 August 2025 confirmed across multiple sources
  impact_figures: LOW  # DownDetector peak confirmed; customer count unconfirmed
  root_cause: MEDIUM   # Inferred from redesign timeline + GlobalData analysis — not officially disclosed
  regulatory_outcome: LOW  # No enforcement action documented

review_flags:
  - "APPROVED — Hussain Ahmed 2026-04-09. inference_approved set to true. confidence_score capped at 0.55."
  - "Root cause is inferred not confirmed. Do not present as established fact in briefing output."
  - "Customer impact count remains UNCONFIRMED. Do not use 14.5M in any MIL inference or output."
  - "incident_type updated from app_online_banking_outage to app_platform_refresh_outage — reflects redesign context."

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
  - source: "GlobalData — HSBC service outage highlights legacy infrastructure fragility in digital banking"
    date: "2025-08"
  - source: "Fintech Futures — Inside HSBC's major 18-month mobile banking app redesign"
    date: "2025"
  - source: "Karmactive.com — NOTE: secondary source; 14.5M figure is total customer base not confirmed affected count"
    date: "2025-08"
  - source: "FStech — Top UK banks accumulate 33 days of IT disruption in 2 years (FCA data: HSBC 32 incidents, 176 hours)"
    date: "2025"

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

---

## CHR-005 — Revolut Login Regression, April 2026

```yaml
chronicle_id: CHR-005
date: "2026-04-04"
bank: "Revolut"
incident_type: login_regression
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-04 to 2026-04-07"

summary: >
  A dense cluster of 25 P0 signals concentrated over a 4-day window indicates a significant
  and sustained pattern of Revolut users being unable to log in to or access their accounts.
  Top keywords — "account", "access", "repeatedly", "logged", "despite", "complete" — suggest
  users were locked out or failing authentication loops despite completing expected steps
  (e.g., biometric or passcode entry). Root cause remains speculative: possible authentication
  infrastructure regression, forced app-update migration issue, or backend session-management
  fault. No single verified public outage notice identified at drafting time.

signal_summary:
  finding_count: 25
  p0_count: 25
  p1_count: 0
  avg_cac: 0.127
  top_keywords: ['account', 'access', 'repeatedly', 'logged', 'despite', 'complete']

verified_facts:
  - "Revolut users experienced widespread login/access failures between approximately 2026-04-04 and 2026-04-07, based on internal signal clustering. APPROVED — Hussain Ahmed 2026-04-16."
  - "Keyword pattern ('repeatedly', 'despite', 'complete') suggests users attempted authentication multiple times without success — silent failure or authentication loop rather than total outage."
  - "Revolut is regulated as an EMI by the FCA (UK). Login failures affecting account access engage FCA operational resilience expectations under PS21/3."

causal_chain:
  - "Step 1: Possible backend change or app update deployed around 2026-04-04 affecting authentication or session management (SPECULATIVE)."
  - "Step 2: Users encounter repeated login failures — authentication steps complete visually but session not established, or accounts flagged/locked unexpectedly."
  - "Step 3: Affected users report via App Store, Reddit, DownDetector — generating the signal cluster captured by MIL."
  - "Step 4: Pattern persists across at least 4 days, suggesting rolling deployment issue or ineffective initial fix."

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved on signal strength and P0 density. Root cause speculative — monitor for public confirmation."
```

---

---

## CHR-006 — Revolut Payment/Transfer Regression, April 2026

```yaml
chronicle_id: CHR-006
date: "2026-04-04"
bank: "Revolut"
incident_type: payment_failure_cluster
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-04 to 2026-04-07"

summary: >
  A dense cluster of 24 P0 signals detected across Revolut's 'Make a Payment / Transfer'
  journey between 4–7 April 2026. Keywords — "transfer", "issue", "failure", "complete",
  "payment", "rewards" — suggest degraded payment/transfer completion, with possible secondary
  impact on rewards/cashback crediting. Likely co-incident with CHR-005 (Revolut login
  regression, same date window), suggesting a broader infrastructure or deployment event.
  Root cause remains speculative — no verified public outage notice or press statement
  identified at time of approval.

signal_summary:
  finding_count: 24
  p0_count: 24
  p1_count: 0
  avg_cac: 0.138
  top_keywords: ['transfer', 'issue', 'failure', 'complete', 'customer', 'payment', 'rewards']

verified_facts:
  - "Revolut users experienced payment/transfer failures between approximately 2026-04-04 and 2026-04-07, based on internal signal clustering. APPROVED — Hussain Ahmed 2026-04-16."
  - "Keyword co-occurrence of 'rewards' alongside payment-failure terms suggests secondary effect on cashback/rewards crediting for affected transactions."
  - "Coincidence with CHR-005 (login regression, same window) suggests a single underlying infrastructure or deployment event."
  - "Revolut holds a UK banking licence (granted July 2024) and is subject to FCA and PRA supervision."

causal_chain:
  - "Step 1: Possible backend or payment-rail issue degraded Revolut's ability to complete outbound transfers during 2026-04-04 to 2026-04-07 (SPECULATIVE)."
  - "Step 2: Affected customers encountered transfer failures, incomplete transactions, or significant delays."
  - "Step 3: Secondary effects impacted rewards/cashback crediting for failed or retried transactions (SPECULATIVE)."
  - "Step 4: Signals cluster tightly with CHR-005 login failures — likely same root deployment event."

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved on signal strength and P0 density. Date corrected from 2025 to 2026. Co-incident with CHR-005 — monitor for common root cause."
```

---

---

## CHR-007 — Revolut Service/Account Access Regression, April 2026

```yaml
chronicle_id: CHR-007
date: "2026-04-04"
bank: "Revolut"
incident_type: login_regression
inference_approved: true
confidence_score: 0.35
date_window: "2026-04-04 to 2026-04-09"

summary: >
  23 P0 signals across 6 consecutive days pointing to Revolut app crashes and login
  failures during account/service access. Keywords — "crashing", "login", "access",
  "security", "after" — suggest auth flow regression following a security-related update.
  Likely co-incident with CHR-005 and CHR-006 (same Revolut April 2026 event window).
  Extended 6-day window suggests slow rollback or phased fix.

signal_summary:
  finding_count: 23
  p0_count: 23
  p1_count: 0
  avg_cac: 0.153
  top_keywords: ['access', 'complete', 'security', 'after', 'revolut', 'crashing', 'login']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Co-incident with CHR-005/006 — same Revolut April 2026 event, Service Access facet."
```

---

## CHR-008 — Monzo Payment/Transfer Friction, April 2026

```yaml
chronicle_id: CHR-008
date: "2026-04-02"
bank: "Monzo"
incident_type: payment_failure_cluster
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-02 to 2026-04-06"

summary: >
  20 P0 signals across 5 days indicating Monzo payment/transfer journey disruption.
  Keywords — "customer", "transfer", "complete", "payment", "reports" — suggest customers
  unable to complete payments or transfers. Low CAC (0.134) and low CHR similarity (0.289)
  confirm novel pattern not covered by existing entries.

signal_summary:
  finding_count: 20
  p0_count: 20
  p1_count: 0
  avg_cac: 0.134
  top_keywords: ['customer', 'transfer', 'complete', 'payment', 'reports']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved on signal volume and P0 density."
```

---

## CHR-009 — Lloyds Payment/Transfer Friction, April 2026

```yaml
chronicle_id: CHR-009
date: "2026-04-02"
bank: "Lloyds"
incident_type: payment_failure_cluster
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-02 to 2026-04-06"

summary: >
  15 P1 signals across 5 days indicating Lloyds payment/transfer friction. Keywords —
  "transfer", "after", "banking" — suggest failures or degraded performance when attempting
  transfers, possibly following an app update or backend migration. Low CAC (0.082) and
  low CHR-001 similarity (0.17) confirm novel pattern.

signal_summary:
  finding_count: 15
  p0_count: 0
  p1_count: 15
  avg_cac: 0.082
  top_keywords: ['transfer', 'after', 'banking']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. All P1 — lower severity than Revolut/Monzo clusters but persistent over 5 days."
```

---

## CHR-010 — NatWest Service/Account Access Pattern, April 2026

```yaml
chronicle_id: CHR-010
date: "2026-04-02"
bank: "NatWest"
incident_type: app_friction_pattern
inference_approved: true
confidence_score: 0.15
date_window: "2026-04-02 to 2026-04-06"

summary: >
  15 P0 signals indicating NatWest customers unable to access accounts or core services.
  Keywords — "customer", "reports", "never" — suggest repeated unresolved complaints.
  Lowest confidence of the batch (0.15) — novel pattern with no strong CHR anchor (sim=0.206).
  Multi-anchor (CHR-002, CHR-001, CHR-003) at low similarity confirms distinct cluster.

signal_summary:
  finding_count: 15
  p0_count: 15
  p1_count: 0
  avg_cac: 0.129
  top_keywords: ['customer', 'reports', 'never']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved at low confidence. Monitor for corroborating public signals."
```

---

## CHR-011 — Lloyds Service/Account Access Pattern, April 2026

```yaml
chronicle_id: CHR-011
date: "2026-04-04"
bank: "Lloyds"
incident_type: app_friction_pattern
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-04 to 2026-04-07"

summary: >
  14 P0 signals across 4 days on Lloyds Account/Service Access journey. Keywords —
  "comment", "explicitly", "states" — suggest user-generated complaints explicitly
  describing inability to access accounts. Very low CHR similarity (0.119) confirms
  novel pattern not mapped to prior chronicles.

signal_summary:
  finding_count: 14
  p0_count: 14
  p1_count: 0
  avg_cac: 0.241
  top_keywords: ['comment', 'explicitly', 'states']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Date corrected from 2025 to 2026. Novel pattern — watch for repeat."
```

---

## CHR-012 — HSBC UK Payment/Transfer Friction, April 2026

```yaml
chronicle_id: CHR-012
date: "2026-04-11"
bank: "HSBC UK"
incident_type: payment_failure_cluster
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-11 to 2026-04-13"

summary: >
  13 P0 signals across 3 days on HSBC UK payment/transfer journey. Keywords — "large",
  "withdrawal", "transaction", "complete", "payments" — suggest difficulty completing
  large-value transfers or withdrawals. Tight 3-day window and 100% P0 density notable.
  Low CHR similarity (0.235) confirms novel pattern.

signal_summary:
  finding_count: 13
  p0_count: 13
  p1_count: 0
  avg_cac: 0.176
  top_keywords: ['large', 'withdrawal', 'transaction', 'complete', 'payments']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Large-value transaction angle is notable — potential FCA operational resilience relevance."
```

---

## CHR-013 — NatWest Payment/Transfer Friction, April 2026

```yaml
chronicle_id: CHR-013
date: "2026-04-12"
bank: "NatWest"
incident_type: payment_failure_cluster
inference_approved: true
confidence_score: 0.35
date_window: "2026-04-12 to 2026-04-14"

summary: >
  10 signals (5 P0, 5 P1) across 3 days on NatWest payment/transfer journey. Keywords —
  "customer", "payment", "significant", "transfer", "complete" — suggest inability to
  complete payments. Mixed P0/P1 severity indicates graduated impact. Partial CHR-004
  anchor (0.31) — related but distinct enough to warrant own entry.

signal_summary:
  finding_count: 10
  p0_count: 5
  p1_count: 5
  avg_cac: 0.35
  top_keywords: ['customer', 'payment', 'significant', 'transfer', 'complete']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Mixed severity — monitor whether P0 count grows in coming days."
```

---

## CHR-014 — HSBC UK Service/Account Access — App Crashes, April 2026

```yaml
chronicle_id: CHR-014
date: "2026-04-11"
bank: "HSBC UK"
incident_type: app_friction_pattern
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-11 to 2026-04-15"

summary: >
  6 P0 signals across 5 days on HSBC UK Account/Service Access journey. Keywords —
  "repeated", "crashes", "application", "customer", "reports" — suggest recurring app
  crashes when accessing accounts. Smallest verified cluster but 5-day persistence
  elevates concern. Co-incident with CHR-012 (HSBC payments, same window).

signal_summary:
  finding_count: 6
  p0_count: 6
  p1_count: 0
  avg_cac: 0.129
  top_keywords: ['repeated', 'crashes', 'application', 'customer', 'reports']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Co-incident with CHR-012 — HSBC may have had a broader April event."
```

---

## CHR-015 — Monzo Service/Account Access — Device Issue, April 2026

```yaml
chronicle_id: CHR-015
date: "2026-04-12"
bank: "Monzo"
incident_type: app_friction_pattern
inference_approved: true
confidence_score: 0.35
date_window: "2026-04-12 to 2026-04-16"

summary: >
  5 consecutive P0 signals (Apr 12–16) on Monzo Account/Service Access journey. Keywords —
  "significant", "customer", "device" — suggest device-specific authentication or login
  issue, potentially tied to app update, device-binding change, or biometric/PIN regression.
  Still active as of today (Apr 16). Monitor for continuation.

signal_summary:
  finding_count: 5
  p0_count: 5
  p1_count: 0
  avg_cac: 0.148
  top_keywords: ['significant', 'customer', 'device']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Active signal — window may extend beyond today. Re-check tomorrow."
```

---

## CHR-016 — HSBC UK Login Regression, April 2026

```yaml
chronicle_id: CHR-016
date: "2026-04-14"
bank: "HSBC UK"
incident_type: login_regression
inference_approved: true
confidence_score: 0.35
date_window: "2026-04-14 to 2026-04-16"

summary: >
  3 consecutive P0 signals (Apr 14–16) on HSBC UK Login journey. Keywords — "complete",
  "block", "preventing" — suggest login flow cannot be completed, consistent with backend
  auth outage, client-side blocking defect, or overly aggressive fraud/security rule change.
  Still active as of today (Apr 16). Co-incident with CHR-012 and CHR-014 — HSBC broader
  April event picture emerging.

signal_summary:
  finding_count: 3
  p0_count: 3
  p1_count: 0
  avg_cac: 0.35
  top_keywords: ['complete', 'block', 'preventing']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Smallest cluster but active today. Part of broader HSBC April pattern (CHR-012, CHR-014, CHR-016)."
```

---

---

## CHR-017 — Barclays Service/Account Access Friction, April 2026

```yaml
chronicle_id: CHR-017
date: "2026-04-02"
bank: "Barclays"
incident_type: account_access_friction_pattern
inference_approved: true
confidence_score: 0.35
date_window: "2026-04-02 to 2026-04-04"

summary: >
  40 P0 signals across Barclays Account/Service Access journey (Apr 2–4 2026). Keywords —
  "access", "registration", "complete", "working", "customer reports" — suggest customers
  unable to complete account registration or access existing accounts via mobile app or
  online banking. Low CHR similarity (0.258) confirms novel pattern not explained by
  CHR-001/002/003. Root cause speculative: possible authentication regression, degraded
  registration flow, or app update impacting onboarding.

signal_summary:
  finding_count: 40
  p0_count: 40
  p1_count: 0
  avg_cac: 0.144
  top_keywords: ['customer', 'access', 'reports', 'complete', 'registration', 'working']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Primary anchor for J_SERVICE_01 — replaces generic CHR-004 coverage for this journey."
```

---

## CHR-018 — Barclays Payment/Transfer Friction, April 2026

```yaml
chronicle_id: CHR-018
date: "2026-04-02"
bank: "Barclays"
incident_type: payment_failure_cluster
inference_approved: true
confidence_score: 0.35
date_window: "2026-04-02 to 2026-04-04"

summary: >
  40 signals (35 P0, 5 P1) across Barclays Make a Payment/Transfer journey (Apr 2–4 2026).
  Keywords — "payment", "transfer", "funds", "failure", "friction" — indicate sustained
  payment processing degradation or outage. 3-day persistence suggests phased rollout issue
  or slow rollback. Nearest anchor CHR-001 at 0.39 similarity (just below 0.4 threshold)
  confirms distinct pattern warranting own entry.

signal_summary:
  finding_count: 40
  p0_count: 35
  p1_count: 5
  avg_cac: 0.190
  top_keywords: ['significant', 'friction', 'customer', 'transfer', 'funds', 'money', 'payment', 'failure']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Primary anchor for J_PAY_01 Barclays. 87.5% P0 density — high severity pattern."
```

---

## CHR-019 — Barclays Login Regression, April 2026

```yaml
chronicle_id: CHR-019
date: "2026-04-02"
bank: "Barclays"
incident_type: login_regression
inference_approved: true
confidence_score: 0.25
date_window: "2026-04-02 to 2026-04-04"

summary: >
  36 P0 signals across Barclays Log In/Account Access journey (Apr 2–4 2026). Keywords —
  "inability", "prevents", "login", "complete", "registration", "accounts" — suggest users
  locked out of essential banking services, unable to complete login or registration flows.
  Low CAC (0.126) confirms signals are novel and not explained by CHR-001/002. Root cause
  speculative: app update authentication regression, backend identity service degradation,
  or registration flow change blocking returning users.

signal_summary:
  finding_count: 36
  p0_count: 36
  p1_count: 0
  avg_cac: 0.126
  top_keywords: ['describes', 'being', 'accounts', 'inability', 'prevents', 'essential', 'complete', 'login']

confidence:
  dates: MEDIUM
  impact_figures: LOW
  root_cause: LOW
  regulatory_outcome: N/A

approval:
  approved_by: "Hussain Ahmed"
  approved_date: "2026-04-16"
  notes: "Approved. Primary anchor for J_LOGIN_01 Barclays. All 36 findings P0 — critical inference gap now resolved."
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
| CHR-003 root cause confirmed | HSBC 2025 | [x] INFERRED — app platform refresh outage. APPROVED — Hussain Ahmed 2026-04-09. confidence_score=0.55 |
| CHR-003 Twitter archive populated | HSBC 2025 | [ ] PENDING_HUSSAIN |
| **M2 countersign** | NatWest MIL-F-20260402-047 | [x] COUNTERSIGNED — Hussain Ahmed 2026-04-02 |
| CHR-004 enrichment review | Barclays 2026 | [x] APPROVED — Hussain Ahmed 2026-04-02 |
| CHR-005 Revolut Login | Revolut 2026-04-04 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-006 Revolut Payments | Revolut 2026-04-04 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-007 Revolut Service Access | Revolut 2026-04-04 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-008 Monzo Payments | Monzo 2026-04-02 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-009 Lloyds Payments | Lloyds 2026-04-02 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-010 NatWest Service Access | NatWest 2026-04-02 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-011 Lloyds Service Access | Lloyds 2026-04-04 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-012 HSBC Payments | HSBC 2026-04-11 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-013 NatWest Payments | NatWest 2026-04-12 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-014 HSBC Service Access | HSBC 2026-04-11 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-015 Monzo Service Access | Monzo 2026-04-12 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-016 HSBC Login | HSBC 2026-04-14 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-017 Barclays Service Access | Barclays 2026-04-02 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-018 Barclays Payments | Barclays 2026-04-02 | [x] APPROVED — Hussain Ahmed 2026-04-16 |
| CHR-019 Barclays Login | Barclays 2026-04-02 | [x] APPROVED — Hussain Ahmed 2026-04-16 |

---

## WEEKLY REVIEW PROTOCOL

Every Friday:
1. Review for any new verified public banking failures to add
2. Review Unanchored Signals digest — candidates for new CHRONICLE entries
3. Twitter archive fields — action any pending searches
4. Update REVIEW CHECKLIST above as items are confirmed

**New entries are appended only. Existing entries are never amended.**
**This is the immutability rule. It does not yield to convenience.**
