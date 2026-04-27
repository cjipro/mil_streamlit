# app.cjipro.com/engineering Data Discipline Posture

**Opening principle:** Manifest is source of truth; code reads the manifest, never the other way round. Governance violations WARN, never FAIL — logged and escalated, but production never blocks on principle debt.

---

## 1. Manifest as Single Source of Truth
**Philosophy:** Every table, field, and agent has one declarative home — data_dictionary_master.yaml and system_manifest.yaml. Code imports, never hardcodes. When business logic changes, the manifest changes first; code stays consistent.

**Falsifiable claim:** All 23 tables are declared in manifest (PULSE-11 / 2026-03-12). Agentic names, source hashes, retention classes, fairness metadata all live in YAML. No hard-coded issue types, journeys, or severity gates exist outside taxonomy_loader.py.

**Drill-down:** [PULSE-11 Dictionary Status](https://jira.internal/browse/PULSE-11) — 17 tables confirmed, 6 pending access. 6 of 23 tables still lack field-level dictionary population (P3 violation logged).

---

## 2. Cryptographic Sealing: Names and Client Identity
**Philosophy:** Original names and client identity never enter the system. HMAC-SHA256 hashes, generated outside codebase, seal the channel. You see agentic names (MAER, CDAC, CPD) and safe substitutes (TAQ Bank, APP code). Originals exist nowhere in logs, prompts, or outputs.

**Falsifiable claim:** P4 (raw_name_sealed_never_surface) and P5 (client_identity_sealed_taq_only) are constitutional. No Pulse query returns original names. Client tables (bsl_custjrny_db, e_scv_db) use substitution registry only.

**Drill-down:** [Substitution Registry & Hash Registry](https://jira.internal/browse/REG-002) — live enforcement in provenance system (P14). REG-001..004 open: DPIA, special-category audit, vulnerability statement, customer-rights statement.

---

## 3. Provenance: Immutable Chronicle per Finding
**Philosophy:** Every inference output (Inference Card V4) carries chronicle_id, signal_ids, classifier_version, teacher_model_version. Hash-chained audit log with daily-rotating salts (MIL-65). 7-year retention, tamper-evident, dual output: SHA-256 hash + natural-language narrative.

**Falsifiable claim:** mil_findings.json is the ONLY exit point from MIL to Pulse (schema v1.0, LIVE status confirmed 2026-04-26). Provenance fields signal_ids and teacher_model_version are structurally present but empty on most findings — deliberately surfaced by V4 to expose calibration debt.

**Drill-down:** [Provenance System & Audit Registry](https://jira.internal/browse/MIL-65) — sample audit event showing hash chain and rotation schedule.

---

## 4. Taxonomy as Configuration, Never Code
**Philosophy:** All issue types, customer journeys, severity gates, and permissible severity ceilings live in domain_taxonomy.yaml. taxonomy_loader.py is the single import point. Breaking changes to taxonomy require version bump and migration plan.

**Falsifiable claim:** 16 issue types currently defined (Positive Feedback through Slow Performance). Each carries max_severity gate (P0 for critical path, P2 for most others). No pipeline file hardcodes issue types; all read via loader.

**Drill-down:** [domain_taxonomy.yaml](https://github.com/cjipro/while-sleeping/blob/main/mil/config/domain_taxonomy.yaml) — current version, category, journey mapping, exclusion rules.

---

## 5. Calibration Discipline: Fortnightly Retrospective
**Philosophy:** Does system output match observable reality? Baseline established 2026-04-18 (Run #34): 30 findings anchored to CHR-003, none dominating. Churn score normalisation break at Run #33 — anomaly thresholds invalid until 14+ normalised runs (circa 2026-05-02). Sensitivity analysis scheduled Day 60.

**Falsifiable claim:** CAC formula (C_mil = (0.40*Vol_sig + 0.40*Sim_hist) / (0.20*Delta_tel + 1)) extracted in mil/inference/cac.py. Independently testable. Weights frozen pending Day 60 sensitivity work. Spot-check accuracy 86% (issue type, Haiku baseline 2026-04-18).

**Drill-down:** [calibration_notes.md](https://github.com/cjipro/while-sleeping/blob/main/mil/data/calibration_notes.md) — baseline findings, three-row retrospective awaiting observability fill. [enrichment_accuracy_log.jsonl](https://github.com/cjipro/while-sleeping/blob/main/mil/data/enrichment_accuracy_log.jsonl) — monthly cadence, model comparison (Haiku 0.86 vs fine_tuned_v1 0.64 on issue type).

---

## 6. Dual-Port HDFS Sovereignty: Pulse (9870) and MIL (9871)
**Philosophy:** Pulse (inbound enrichment & broker) and MIL (inference engine) never share port. Cryptographic attestation on handoff. MIL outputs only via mil_findings.json — single exit, dual-signed, immutable until deletion hold expires.

**Falsifiable claim:** HDFS namenode binds 9870 (Pulse) and 9871 (MIL). No cross-port queries. MIL-only data (taxonomy, model snapshots, raw intermediate signals) never cross to Pulse except as findings. Topology pre-declared in topology.yaml.

**Drill-down:** [Topology & Port Registry](https://jira.internal/browse/INF-001) — current binding, SLA, incident escalation.

---

## 7. DuckDB Analytics Layer: Rebuilt Every Run
**Philosophy:** Every inference run rebuilds mil_analytics.db (9 tables: issue_summary, confidence_distribution, fairness_metrics, signal_lineage, severity_distribution, journey_coverage, model_drift, calibration_drift, exclusion_log). No persistence between runs. Queries always read fresh state.

**Falsifiable claim:** mil_analytics.db schema is deterministic from MIL schema v1.0. Rebuild time less than 2 minutes on 10K finding sample. Silent Wall detector (P20 MVP) monitors fetch-volume, enrichment-failure, severity-distribution drift. Drift Monitor Phase 2 not yet shipped (pending PDS validation).

**Drill-down:** [mil_analytics.db schema & rebuild timing](https://jira.internal/browse/INF-012) — current performance, Phase 2 scope (Fetch Volume Detector, Enrichment Failure Detector, Severity Distribution Detector — all pending).

---

## Section Cut: "Core Data Principles"
A generic "data principles" page would enumerate data quality, security, privacy, compliance. We cut it. This audience reads principles in governance_principles.yaml (21 defined, violation_policy WARN_NOT_FAIL) and expects: Which ones are implemented today? Which are debt? What is the compliance gap? A prettified list signals aspiration. Honest state signals credibility. We show PULSE-11 (6 tables pending dictionary), REG-001..004 (DPIA, special-category audit, vulnerability statement, customer-rights — all open), and MIL drift detector (Phase 2 deferred). That is the brief.

---

## Non-Obvious Differentiator: Fortnightly Calibration Baseline
Most banking data shops run accuracy metrics post-hoc. We run a standing fortnightly retrospective: "Did last run's top findings show up in observable data (App Store, DownDetector, NatWest/Barclays/Santander app rating changes)?" Baseline established 2026-04-18. Three-row check in progress (Apr 5, 10, 15 findings vs observable signal over next 14 days). This is live telemetry binding inference to customer impact — not post-mortems, not guesses. If findings don't match observable reality within 14 days, the weights are wrong and we have concrete evidence to adjust.

---

## The Sentence That Earns or Loses Trust
"Provenance fields signal_ids and teacher_model_version are structurally present but empty on most findings — deliberately surfaced by V4 to show you exactly where calibration debt lives."

A vendor would hide this. We surface it. Banking data engineers respect honesty about what you don't know yet.

---

## Trade-Off Note: Show the Gap Honestly
PULSE-11 reports 6 of 23 tables pending dictionary population. Drift Monitor MVP covers Silent Wall only — fetch-volume, enrichment-failure, severity-distribution detectors not shipped. CAC weights frozen pending Day 60 sensitivity run. A polished brief would bury these or frame them as "planned improvements." We lead with them because your data team will find them anyway, and candor on gaps is worth 10 apologetic excuses later.
