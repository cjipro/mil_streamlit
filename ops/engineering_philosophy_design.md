# /engineering page — design decisions

Source of truth for MIL-159 panel synthesis. MIL-160 builds against this file.

## Opener line (LOCKED 2026-04-27)

> **This system prefers honest ignorance to unverified certainty — every claim ships with an evidence id, every gap ships with a ticket number.**

**Why this line:**
- Covers all four panel lenses simultaneously (AI Article Zero / SW Zero Entanglement / Data provenance / Cyber AICPA-verifiability).
- Sets up the page's three-bucket structure (ADDRESSED / PLANNED / CONSIDERED) in one sentence: "evidence id" → ADDRESSED, "ticket number" → PLANNED + CONSIDERED.
- Weaponises candour as a differentiator — unanimous panel recommendation.

## Information architecture (LOCKED — pending opener)

See preceding panel synthesis for the full bucket contents:

- **Header strip:** opener line + last-reviewed date + scope line
- **ADDRESSED** — production today, every bullet has an evidence id
- **PLANNED** — committed work in flight, every bullet has a ticket number
- **CONSIDERED** — not committed, signal-driven post-MVP, every bullet names what would unblock it
- **Footer strip:** four "Did You Know" callouts (one per discipline)

## Section voice rule (LOCKED 2026-04-27)

Confessional tone in AI / Data sections (lean into shelved QLoRA, empty provenance fields, calibration debt). Clinical tone in Security / Software sections (immutable invariants, regex deny-lists, validator hard-fails). Section voice follows section subject — no smoothed-out single voice across the page.

## Drill-down convention (LOCKED 2026-04-27)

Every bullet on the page carries two links: **the code** (filename + line range, anchored to GitHub) and **the rationale** (Jira ticket or `ops/runbooks/` entry). Two clicks max from page to truth. No third link, no marketing landing, no PDF.

## All decisions LOCKED — ready for MIL-160 build

---

# Page copy draft — `app.cjipro.com/engineering`

> Drafted against locked IA. MIL-160 renders this content into the Worker. No marketing copy. Every bullet carries two links: **`[code]`** (filename + line range, GitHub) and **`[why]`** (Jira ticket or runbook).

## Header strip

**Engineering posture**

> *This system prefers honest ignorance to unverified certainty — every claim ships with an evidence id, every gap ships with a ticket number.*

Last reviewed: 2026-04-27 · Scope: public-signal market intelligence; air-gapped from internal banking systems by design.

---

## Addressed — in production today

> *Confessional voice in §AI and §Data; clinical voice in §Security and §Software. Every bullet resolves to evidence.*

### §AI · Synthesis, never source-of-truth

- **Article Zero is constitutional, not a values statement.** The system halts and emits a refusal when public signal cannot resolve a claim. This is named in the trust manifesto and enforced at every model boundary. `[code: mil/SOVEREIGN_BRIEF.md]` `[why: mil/CHRONICLE.md]`
- **Model selection is governed by decision stakes, not cost.** Four tiers. CHR proposals + autopsies on Opus. Daily decisions on Sonnet. Classification at scale on Haiku / Refuel-8B. Labour on Qwen3 local. Switches are audited (ARCH-004 → ARCH-006, with date and reason in the YAML). `[code: mil/config/model_routing.yaml]` `[why: ARCH-006 entry, 2026-04-25]`
- **Synthesis output is verifier-cleared before it ships.** Sonnet drafts; Haiku audits citations and verbatim quotes (smart-quote-normalised). Failure retries once or returns a refusal. The output is logged regardless. `[code: mil/chat/verifier.py]` `[why: MIL-42, MIL-43]`
- **Every inference traces to a CHRONICLE entry.** If the trace fails, the inference does not get trained on and does not get reported. Nineteen entries today, append-only. `[code: mil/CHRONICLE.md]` `[why: MIL-31]`
- **A trained specialist was shelved with held-out evidence.** Two QLoRA runs lost to the qwen3:14b baseline (83.3% vs 93.3% overall, 75% vs 83.3% on P0). Severity stays on the enrichment route. The decision is logged, the report is published. `[code: mil/specialist/heldout_eval_report.md]` `[why: ARCH-005, 2026-04-20]`

### §Data · Manifest is source of truth

- **Code reads the manifest, not the other way round.** Issue types, journeys, severity gates, source registry, trust weights — all in YAML. Pipeline files cannot hardcode taxonomy. `[code: mil/config/domain_taxonomy.yaml]` `[why: MIL-32]`
- **Dual-port HDFS sovereignty.** MIL on 9871. Pulse on 9870. Never shared. The only data crossing from MIL is `mil/outputs/mil_findings.json`, and a build validator hard-fails any code that imports across the boundary. `[code: scripts/validate_mil_import_rule.py]` `[why: MIL-6, MIL-36]`
- **Provenance Chain on every inference card.** Four fields per finding: `chronicle_id`, `signal_ids`, `class_ver`, `teacher_ver`. Where data is missing today (e.g. `signal_ids` empty on most findings) we render `—`, not zero. The gap is visible by design. `[code: mil/publish/templates/_inference_card.html.j2]` `[why: MIL-39, FCA Consumer Duty 2.0]`
- **90-day rolling benchmarks with scipy linregress.** No all-time-history dilution. Streak carry-forward is bounded by a two-day gap tolerance. Churn score normalised 0–100. `[code: mil/data/benchmark_engine.py]` `[why: MIL-27]`
- **Calibration is a fortnightly retrospective, not post-hoc.** Findings vs observable signal over a 14-day window. Baseline established 2026-04-18. CAC weights frozen pending Day-60 sensitivity work. `[code: mil/data/calibration_notes.md]` `[why: MIL-27]`
- **Spot-check accuracy log under monthly cadence.** Issue type ≥85% target, severity class ≥90% target. Below-target sample exits non-zero. `[code: mil/tests/enrichment_spot_check.py]` `[why: mil/data/enrichment_accuracy_log.jsonl]`

### §Security · Immutable from day one, never claimed beyond what's verifiable

- **Hash-chained immutable audit log + daily-rotating salts.** Every auth decision rows into D1 with `prev_hash` + `row_hash`. PII (sub, IP, UA) hashed via daily-rotated salt. Re-verifiable end-to-end via the verifier CLI. `[code: mil/auth/audit/]` `[why: MIL-65, mil/auth/audit/README.md]`
- **Session cookie is a code-enforced contract.** `__Secure-cjipro-session` — name, flags, domain, Max-Age locked in TypeScript. Drift between issuer (magic-link) and validator (edge-bouncer) breaks tests. `[code: mil/auth/magic_link/src/cookie_spec.ts]` `[why: mil/auth/COOKIE_SPEC.md, MIL-64]`
- **Magic-link state HMAC-signed with 10-min TTL + return_to allowlist.** Constant-time compare. Open-redirect attempts rejected at validation, not at the OAuth dance. `[code: mil/auth/magic_link/src/state.ts]` `[why: MIL-61]`
- **Forward-use detection (audit-tag, never block).** IP /24 + UA family compare across `/authorize` → `/callback`. Differs → audit event `magic_link.forwarded_use_detected`. Corp NAT does not false-positive. `[code: mil/auth/magic_link/src/forward_detect.ts]` `[why: MIL-146]`
- **Differentiated deny states.** In-queue (pending signup) → 200 page with status. Not-on-allowlist → 403 page with request-access CTA. D1-unavailable → fallback. No enumeration leak. `[code: mil/auth/edge_bouncer/src/index.ts]` `[why: MIL-153]`
- **Firm-slug is admin-set only.** A compromised partner IdP cannot self-assign rival firm context. `confirmDetails()` rejects firm_* keys at runtime. `[code: mil/auth/approvals/src/partner_profiles.ts]` `[why: MIL-152]`
- **SCIM auto-deprovision always fires; auto-approve is opt-in per WorkOS org.** Removal is the load-bearing property. New-user provisioning audits-only by default. `[code: mil/auth/approvals/src/auto_approve.ts]` `[why: mil/auth/MIL71_SCIM.md]`
- **Per-tenant audit export with salt-aware hash recompute.** Partners pull their own auth events scoped to their organization id; partners cannot cross-correlate users across orgs. `[code: mil/auth/approvals/src/audit_export.ts]` `[why: mil/auth/MIL72_AUDIT_EXPORT.md]`
- **AICPA-verifiability rule on every public claim.** "SOC 2 readiness assessment underway" — never "in progress". `[code: mil/publish/site/security.html]` `[why: MIL-135 polish]`

### §Software · Abstractions minimal, contracts explicit, runbooks for everything load-bearing

- **Adapter pattern for publish + vault.** GitHub Pages / Local / Null adapters select by YAML. Vault backend (HDFS / Local / Null) follows the same shape. Clone operators retarget without code changes. `[code: mil/publish/adapters.py, mil/vault/backends.py]` `[why: MIL-35, MIL-36]`
- **Sensitive-path deny-list at the API boundary.** Public Pages repo refuses any path matching auth code, runbooks, source-code extensions, `.env*`, top-level docs. 56 tests. Caller cannot accidentally leak credentials — the adapter rejects before disk write. `[code: mil/tests/test_publish_deny_list.py]` `[why: MIL-110, ops/runbooks/mil-110_repo_split.md]`
- **Five TypeScript Workers, vitest-tested, ~300 assertions.** edge_bouncer / magic_link / app_cjipro / sonar_redirect / approvals. Every material rollout has a runbook. `[code: mil/auth/{edge_bouncer,magic_link,app_cjipro,sonar_redirect,approvals}/]` `[why: ops/runbooks/]`
- **Generated-TS-artefact pattern.** Partner email-domain map, subject picker, font block — all generated from one YAML / fetch script source of truth, regenerated on predeploy. No hand-edited `.generated.ts`. `[code: mil/auth/app_cjipro/scripts/gen_partner_domains.py]` `[why: MIL-155]`
- **Self-hosted typography. No CDN dependency on cjipro.com / login.cjipro.com / app.cjipro.com.** Source Serif 4 + Inter on the marketing site and Workers; Plus Jakarta Sans + DM Mono on briefings. Bank-corp-proxy reachability is a first-class requirement. `[code: mil/publish/fonts_pipeline/fetch_fonts.py]` `[why: MIL-136, MIL-157, MIL-158]`
- **Two-repo public/private contract with dual-push.** `mil_streamlit` (private, system of record) + `mil-briefing` (public, rendered HTML only). Dual-push to GitHub canonical + GitLab read-mirror; rebase-recovery is a written procedure, not folklore. `[code: docker-compose.yml + .gitlab-ci.yml]` `[why: ops/runbooks/mil-110_repo_split.md]`

---

## Planned — committed work, ticket-tracked

> *Confessional in AI/Data, clinical in Security/Software.*

- **V1 publisher retirement → V4-only render path.** V1 currently anchors V2/V3/V4 (load-bearing coupling — known and named). Retirement queues V4 standalone. `[why: MIL-125]`
- **Tenant strings extracted to one config file.** Today: domain literals, `Barclays` strings, WorkOS Org/Client IDs scattered across adapters and YAML. After: a single tenant config a clone operator can edit. `[why: MIL-116, MIL-119, MIL-120]`
- **Repo collapse + rename to `cji-pro`.** Hard-gated to ≥2026-05-01 (3-day post-ENFORCE soak). `[why: MIL-73]`
- **Refresh-token rotation.** Today: 1-hour cookie + ~10-min JWT exp is tighter than typical enterprise (4h / 24h) but forces silent re-auth on long sessions. Server-side state machine queued. Hard-gated to ≥2026-05-01. `[why: MIL-74]`
- **Passkey Phase B event taxonomy.** Webhook ingest is live; the typed event mapping (`passkey.registered`, `passkey.used`, etc.) is drafted post-observation. `[why: mil/auth/MIL67_PASSKEYS.md]`
- **Prompts moved to file with versioned eval sets.** Today: synthesis prompts are inline strings in commentary / briefing-email / chat. After: file-based, hash-versioned, per-prompt eval. `[why: MIL-126]`
- **Frozen enrichment validation corpus.** A 100-record held-out set with locked labels, replayed on every enrichment-route change. Today: model swaps validated by manual spot-check. `[why: MIL-123]`
- **Day-60 CAC sensitivity analysis.** Weight grid across α/β/δ. Re-rerun against the larger corpus accumulated post-Day-30. `[why: mil/data/calibration_notes.md]`
- **Drift Monitor Phase 2 detectors.** Silent Wall ships today (MIL-48). Fetch-volume, enrichment-failure, severity-distribution detectors queue against operational signals. `[why: mil/monitoring/drift_monitor.py]`
- **PULSE-11 dictionary completion.** 17 of 23 tables confirmed; 6 pending field population. `[why: PULSE-11]`

---

## Considered — post-MVP, signal-driven, not committed

> *Each line names what would unblock it. Nothing here is on the roadmap; everything here is on the radar.*

- **SOC 2 Type 1 attestation.** Today: readiness assessment underway (AICPA-verifiable phrasing, deliberately). Unblock: budget + auditor selection. `[why: MIL-100]`
- **Formal pen test on the alpha surface.** Today: in-house defence-in-depth + Cloudflare WAF. Unblock: alpha cohort scale + scoping. `[why: no ticket — radar]`
- **DPIA REG-001..004.** Pulse-side; gates live-customer-data work. MIL is public-only and does not trigger them. Unblock: Phase 2 commitment + ICO coordination. `[why: REG-001..004, governance_principles.yaml]`
- **QLoRA specialist re-attempt.** Today: shelved on evidence (4B trained model loses to qwen3:14b baseline). Unblock: bitsandbytes stability on RTX 5070 Ti Blackwell, or larger training hardware. `[why: ARCH-005, mil/specialist/heldout_eval_report.md]`
- **Designed-Ceiling escalation automation.** Today: Hussain reads the click log on Fridays. Unblock: alpha cohort volume that justifies SLA tracking. `[why: mil/data/click_log.jsonl]`
- **Phase 2 internal-data integration.** The whole CJI Pulse 90-day plan; surfaces internal telemetry under DPIA. Unblock: Day-90 evidence pack + buyer commitment. `[why: PULSE-83]`

---

## Footer · One non-obvious claim per discipline

> *Four "Did You Know" callouts. The panel's most distinctive claims, rendered as small cards.*

1. **§AI** — Evidence-based model switching is audited in YAML. Haiku → qwen3:14b → Sonnet 4.6, with date and reason on each switch. Most AI shops cannot produce this audit trail. `[why: mil/config/model_routing.yaml]`
2. **§Software** — Secrets are rejected by name pattern at the publish-adapter API boundary, not at the filesystem or CI gate. A caller bug fails before disk write. `[why: MIL-110, 56 tests]`
3. **§Data** — Provenance fields `signal_ids` and `teacher_model_version` are structurally present but empty on most findings. We surface the empty fields by design — calibration debt is visible, not hidden. `[why: MIL-39 V4 Provenance Chain]`
4. **§Security** — `firm_slug` is admin-set only. A compromised partner IdP + malicious user cannot self-assign rival firm context. Most SaaS vendors delegate firm assignment to the partner's IdP. `[why: MIL-152]`

---

*Reviewed and locked: 2026-04-27. Source: panel synthesis (MIL-159). Build: MIL-160.*

## Source files

- `ops/panel_briefs/proposal_ai_engineering.md`
- `ops/panel_briefs/proposal_software_engineering.md`
- `ops/panel_briefs/proposal_data_engineering.md`
- `ops/panel_briefs/proposal_cyber_security.md`
