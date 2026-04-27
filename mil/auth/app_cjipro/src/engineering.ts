// MIL-160 — /engineering page on app.cjipro.com.
//
// Renders the panel synthesis from MIL-159 as an authenticated page
// for the demo audience (Head of AI Engineering at a UK bank, SE
// background, controls-focused). CSP-clean: no inline JS, no event
// handlers. Fonts come from the shared FONTS_BLOCK (MIL-158). The
// page lives behind the ENFORCE gate in index.ts — anonymous visitors
// see /sign-in via the bouncer redirect.
//
// Source of truth for content + IA: ops/engineering_philosophy_design.md.
// If you edit copy here, update the design doc in lockstep — that file
// IS the panel decision, this file is just the renderer.
//
// Drill-down convention: every bullet carries two anchors. `[code]`
// resolves to a file path on GitHub; `[why]` resolves to a Jira ticket
// or a runbook on GitHub. Two clicks max from page to truth.

import { FONTS_BLOCK } from "../../fonts_block/src/fonts_block.generated";

const REPO_BLOB = "https://github.com/cjipro/mil_streamlit/blob/main";
const JIRA_BROWSE = "https://cjipro.atlassian.net/browse";

interface Bullet {
  text: string;
  codePath?: string;   // e.g. "mil/SOVEREIGN_BRIEF.md"
  codeLabel?: string;  // optional override for the link text
  why: string;         // "MIL-65" | "ops/runbooks/foo.md" | "ARCH-006 entry, 2026-04-25"
  whyHref?: string;    // explicit href if `why` is a non-Jira label
}

interface Section {
  id: string;
  eyebrow: string;       // "§AI" / "§Data" / etc
  title: string;
  voice: "confessional" | "clinical";
  bullets: Bullet[];
}

interface Callout {
  eyebrow: string; // "§AI"
  text: string;
  why: string;
  whyHref?: string;
}

interface TableRow {
  discipline: string;
  strengths: string;
  pipeline: string;
  idealWorld: string;
}

const ADDRESSED_SECTIONS: Section[] = [
  {
    id: "ai",
    eyebrow: "§AI",
    title: "Synthesis, never source-of-truth",
    voice: "confessional",
    bullets: [
      {
        text: "Article Zero is constitutional, not a values statement. The system halts and emits a refusal when public signal cannot resolve a claim. This is named in the trust manifesto and enforced at every model boundary.",
        codePath: "mil/SOVEREIGN_BRIEF.md",
        why: "mil/CHRONICLE.md",
        whyHref: `${REPO_BLOB}/mil/CHRONICLE.md`,
      },
      {
        text: "Model selection is governed by decision stakes, not cost. Four tiers — CHR proposals + autopsies on Opus, daily decisions on Sonnet, classification at scale on Haiku / Refuel-8B, labour on Qwen3 local. Switches are audited (ARCH-004 → ARCH-006, with date and reason in the YAML).",
        codePath: "mil/config/model_routing.yaml",
        why: "ARCH-006 entry, 2026-04-25",
        whyHref: `${REPO_BLOB}/mil/config/model_routing.yaml`,
      },
      {
        text: "Synthesis output is verifier-cleared before it ships. Sonnet drafts; Haiku audits citations and verbatim quotes (smart-quote-normalised). Failure retries once or returns a refusal. The output is logged regardless.",
        codePath: "mil/chat/verifier.py",
        why: "MIL-43",
      },
      {
        text: "Every inference traces to a CHRONICLE entry. If the trace fails, the inference does not get trained on and does not get reported. Nineteen entries today, append-only.",
        codePath: "mil/CHRONICLE.md",
        why: "MIL-31",
      },
      {
        text: "A trained specialist was shelved with held-out evidence. Two QLoRA runs lost to the qwen3:14b baseline (83.3% vs 93.3% overall, 75% vs 83.3% on P0). Severity stays on the enrichment route. The decision is logged, the report is published.",
        codePath: "mil/specialist/heldout_eval_report.md",
        why: "ARCH-005, 2026-04-20",
        whyHref: `${REPO_BLOB}/mil/specialist/heldout_eval_report.md`,
      },
    ],
  },
  {
    id: "data",
    eyebrow: "§Data",
    title: "Manifest is source of truth",
    voice: "confessional",
    bullets: [
      {
        text: "Code reads the manifest, not the other way round. Issue types, journeys, severity gates, source registry, trust weights — all in YAML. Pipeline files cannot hardcode taxonomy.",
        codePath: "mil/config/domain_taxonomy.yaml",
        why: "MIL-32",
      },
      {
        text: "Dual-port HDFS sovereignty. MIL on 9871. Pulse on 9870. Never shared. The only data crossing from MIL is mil/outputs/mil_findings.json, and a build validator hard-fails any code that imports across the boundary.",
        codePath: "scripts/validate_mil_import_rule.py",
        why: "MIL-36",
      },
      {
        text: "Provenance Chain on every inference card. Four fields per finding: chronicle_id, signal_ids, class_ver, teacher_ver. Where data is missing today (e.g. signal_ids empty on most findings) we render an em-dash, not zero. The gap is visible by design.",
        codePath: "mil/publish/templates/briefing_v4.html.j2",
        why: "MIL-39",
      },
      {
        text: "90-day rolling benchmarks with scipy linregress. No all-time-history dilution. Streak carry-forward is bounded by a two-day gap tolerance. Churn score normalised 0–100.",
        codePath: "mil/data/benchmark_engine.py",
        why: "MIL-27",
      },
      {
        text: "Calibration is a fortnightly retrospective, not post-hoc. Findings vs observable signal over a 14-day window. Baseline established 2026-04-18. CAC weights frozen pending Day-60 sensitivity work.",
        codePath: "mil/data/calibration_notes.md",
        why: "mil/data/calibration_notes.md",
        whyHref: `${REPO_BLOB}/mil/data/calibration_notes.md`,
      },
      {
        text: "Spot-check accuracy log under monthly cadence. Issue type ≥85% target, severity class ≥90% target. Below-target sample exits non-zero.",
        codePath: "mil/tests/enrichment_spot_check.py",
        why: "mil/data/enrichment_accuracy_log.jsonl",
        whyHref: `${REPO_BLOB}/mil/data/enrichment_accuracy_log.jsonl`,
      },
    ],
  },
  {
    id: "security",
    eyebrow: "§Security",
    title: "Immutable from day one, never claimed beyond what's verifiable",
    voice: "clinical",
    bullets: [
      {
        text: "Hash-chained immutable audit log + daily-rotating salts. Every auth decision rows into D1 with prev_hash + row_hash. PII (sub, IP, UA) hashed via daily-rotated salt. Re-verifiable end-to-end via the verifier CLI.",
        codePath: "mil/auth/audit/src/verify_cli.ts",
        why: "MIL-65",
      },
      {
        text: "Session cookie is a code-enforced contract. __Secure-cjipro-session — name, flags, domain, Max-Age locked in TypeScript. Drift between issuer (magic-link) and validator (edge-bouncer) breaks tests.",
        codePath: "mil/auth/magic_link/src/cookie_spec.ts",
        why: "MIL-64",
      },
      {
        text: "Magic-link state HMAC-signed with 10-min TTL + return_to allowlist. Constant-time compare. Open-redirect attempts rejected at validation, not at the OAuth dance.",
        codePath: "mil/auth/magic_link/src/state.ts",
        why: "MIL-61",
      },
      {
        text: "Forward-use detection (audit-tag, never block). IP /24 + UA family compare across /authorize → /callback. Differs → audit event magic_link.forwarded_use_detected. Corp NAT does not false-positive.",
        codePath: "mil/auth/magic_link/src/forward_detect.ts",
        why: "MIL-146",
      },
      {
        text: "Differentiated deny states. In-queue (pending signup) → 200 page with status. Not-on-allowlist → 403 page with request-access CTA. D1-unavailable → fallback. No enumeration leak.",
        codePath: "mil/auth/edge_bouncer/src/index.ts",
        why: "MIL-153",
      },
      {
        text: "firm_slug is admin-set only. A compromised partner IdP cannot self-assign rival firm context. confirmDetails() rejects firm_* keys at runtime.",
        codePath: "mil/auth/approvals/src/partner_profiles.ts",
        why: "MIL-152",
      },
      {
        text: "SCIM auto-deprovision always fires; auto-approve is opt-in per WorkOS org. Removal is the load-bearing property. New-user provisioning audits-only by default.",
        codePath: "mil/auth/approvals/src/auto_approve.ts",
        why: "mil/auth/MIL71_SCIM.md",
        whyHref: `${REPO_BLOB}/mil/auth/MIL71_SCIM.md`,
      },
      {
        text: "Per-tenant audit export with salt-aware hash recompute. Partners pull their own auth events scoped to their organization id; partners cannot cross-correlate users across orgs.",
        codePath: "mil/auth/approvals/src/audit_export.ts",
        why: "mil/auth/MIL72_AUDIT_EXPORT.md",
        whyHref: `${REPO_BLOB}/mil/auth/MIL72_AUDIT_EXPORT.md`,
      },
      {
        text: 'AICPA-verifiability rule on every public claim. "SOC 2 readiness assessment underway" — never "in progress".',
        codePath: "mil/publish/site/security.html",
        why: "MIL-135",
      },
    ],
  },
  {
    id: "software",
    eyebrow: "§Software",
    title: "Abstractions minimal, contracts explicit, runbooks for everything load-bearing",
    voice: "clinical",
    bullets: [
      {
        text: "Adapter pattern for publish + vault. GitHub Pages / Local / Null adapters select by YAML. Vault backend (HDFS / Local / Null) follows the same shape. Clone operators retarget without code changes.",
        codePath: "mil/publish/adapters.py",
        why: "MIL-35",
      },
      {
        text: "Sensitive-path deny-list at the API boundary. Public Pages repo refuses any path matching auth code, runbooks, source-code extensions, .env*, top-level docs. 56 tests. Caller cannot accidentally leak credentials — the adapter rejects before disk write.",
        codePath: "mil/tests/test_publish_deny_list.py",
        why: "MIL-110",
      },
      {
        text: "Five TypeScript Workers, vitest-tested, ~300 assertions. edge_bouncer / magic_link / app_cjipro / sonar_redirect / approvals. Every material rollout has a runbook.",
        codePath: "mil/auth/",
        codeLabel: "mil/auth/{edge_bouncer,magic_link,app_cjipro,sonar_redirect,approvals}/",
        why: "ops/runbooks/",
        whyHref: "https://github.com/cjipro/mil_streamlit/tree/main/ops/runbooks",
      },
      {
        text: "Generated-TS-artefact pattern. Partner email-domain map, subject picker, font block — all generated from one YAML / fetch script source of truth, regenerated on predeploy. No hand-edited .generated.ts.",
        codePath: "mil/auth/app_cjipro/scripts/gen_partner_domains.py",
        why: "MIL-155",
      },
      {
        text: "Self-hosted typography. No CDN dependency on cjipro.com / login.cjipro.com / app.cjipro.com. Source Serif 4 + Inter on the marketing site and Workers; Plus Jakarta Sans + DM Mono on briefings. Bank-corp-proxy reachability is a first-class requirement.",
        codePath: "mil/publish/fonts_pipeline/fetch_fonts.py",
        why: "MIL-158",
      },
      {
        text: "Two-repo public/private contract with dual-push. mil_streamlit (private, system of record) + mil-briefing (public, rendered HTML only). Dual-push to GitHub canonical + GitLab read-mirror; rebase-recovery is a written procedure, not folklore.",
        codePath: "ops/runbooks/mil-110_repo_split.md",
        why: "ops/runbooks/mil-110_repo_split.md",
        whyHref: `${REPO_BLOB}/ops/runbooks/mil-110_repo_split.md`,
      },
    ],
  },
];

const PLANNED: Bullet[] = [
  {
    text: "V1 publisher retirement → V4-only render path. V1 currently anchors V2/V3/V4 (load-bearing coupling — known and named). Retirement queues V4 standalone.",
    why: "MIL-125",
  },
  {
    text: "Tenant strings extracted to one config file. Today: domain literals, Barclays strings, WorkOS Org/Client IDs scattered across adapters and YAML. After: a single tenant config a clone operator can edit.",
    why: "MIL-119",
  },
  {
    text: "Repo collapse + rename to cji-pro. Hard-gated to ≥2026-05-01 (3-day post-ENFORCE soak).",
    why: "MIL-73",
  },
  {
    text: "Refresh-token rotation. Today: 1-hour cookie + ~10-min JWT exp is tighter than typical enterprise (4h / 24h) but forces silent re-auth on long sessions. Server-side state machine queued.",
    why: "MIL-74",
  },
  {
    text: "Passkey Phase B event taxonomy. Webhook ingest is live; the typed event mapping (passkey.registered, passkey.used, etc.) is drafted post-observation.",
    why: "mil/auth/MIL67_PASSKEYS.md",
    whyHref: `${REPO_BLOB}/mil/auth/MIL67_PASSKEYS.md`,
  },
  {
    text: "Prompts moved to file with versioned eval sets. Today: synthesis prompts are inline strings in commentary / briefing-email / chat. After: file-based, hash-versioned, per-prompt eval.",
    why: "MIL-126",
  },
  {
    text: "Frozen enrichment validation corpus. A 100-record held-out set with locked labels, replayed on every enrichment-route change. Today: model swaps validated by manual spot-check.",
    why: "MIL-123",
  },
  {
    text: "Day-60 CAC sensitivity analysis. Weight grid across α/β/δ. Re-rerun against the larger corpus accumulated post-Day-30.",
    why: "mil/data/calibration_notes.md",
    whyHref: `${REPO_BLOB}/mil/data/calibration_notes.md`,
  },
  {
    text: "Drift Monitor Phase 2 detectors. Silent Wall ships today (MIL-48). Fetch-volume, enrichment-failure, severity-distribution detectors queue against operational signals.",
    why: "mil/monitoring/drift_monitor.py",
    whyHref: `${REPO_BLOB}/mil/monitoring/drift_monitor.py`,
  },
  {
    text: "PULSE-11 dictionary completion. 17 of 23 tables confirmed; 6 pending field population.",
    why: "PULSE-11",
  },
];

const CONSIDERED: Bullet[] = [
  {
    text: "SOC 2 Type 1 attestation. Today: readiness assessment underway (AICPA-verifiable phrasing, deliberately). Unblock: budget + auditor selection.",
    why: "MIL-100",
  },
  {
    text: "Formal pen test on the alpha surface. Today: in-house defence-in-depth + Cloudflare WAF. Unblock: alpha cohort scale + scoping.",
    why: "no ticket — radar",
  },
  {
    text: "DPIA REG-001..004. Pulse-side; gates live-customer-data work. MIL is public-only and does not trigger them. Unblock: Phase 2 commitment + ICO coordination.",
    why: "manifests/governance_principles.yaml",
    whyHref: `${REPO_BLOB}/manifests/governance_principles.yaml`,
  },
  {
    text: "QLoRA specialist re-attempt. Today: shelved on evidence (4B trained model loses to qwen3:14b baseline). Unblock: bitsandbytes stability on RTX 5070 Ti Blackwell, or larger training hardware.",
    why: "mil/specialist/heldout_eval_report.md",
    whyHref: `${REPO_BLOB}/mil/specialist/heldout_eval_report.md`,
  },
  {
    text: "Designed-Ceiling escalation automation. Today: a human reads the click log on Fridays. Unblock: alpha cohort volume that justifies SLA tracking.",
    why: "mil/data/click_log.jsonl",
    whyHref: `${REPO_BLOB}/mil/data/click_log.jsonl`,
  },
  {
    text: "Phase 2 internal-data integration. The whole CJI Pulse 90-day plan; surfaces internal telemetry under DPIA. Unblock: Day-90 evidence pack + buyer commitment.",
    why: "PULSE-83",
  },
];

// At-a-glance table — synthesised from the four panel-seat reactions
// (table_react_*.md). Each cell ≤12 words, falsifiable. Strengths point
// to shipped code; Pipeline points to a real Jira ticket; Ideal world
// names a specific control gated by a named blocker — never aspirational
// or confused with a current attestation. The legend immediately under
// the table is load-bearing: it stops "Ideal world" being read as today.
const TABLE_ROWS: TableRow[] = [
  {
    discipline: "AI",
    strengths: "Article Zero, four-tier routing, verifier-cleared synthesis",
    pipeline: "Prompts-to-file + eval sets (MIL-126); frozen validation corpus (MIL-123)",
    idealWorld: "Specialist beats baseline on P0; CHRONICLE auto-updates from observable signal",
  },
  {
    discipline: "Software",
    strengths: "Adapter swappability, 56-test deny-list, ~300 Worker tests (MIL-110)",
    pipeline: "V1 retirement (MIL-125); tenant strings extracted (MIL-119)",
    idealWorld: "Single tenant-config swap; clone-deploy under one day; zero hardcoded strings",
  },
  {
    discipline: "Data",
    strengths: "Provenance Chain live, 90-day benchmarks, manifest-as-truth (MIL-39)",
    pipeline: "Day-60 CAC sensitivity; PULSE-11 dictionary (6 of 23 pending)",
    idealWorld: "Findings verified against observable signal in 24h; signal_ids non-empty",
  },
  {
    discipline: "Security",
    strengths: "Hash-chained audit + daily salts; cookie-as-code (MIL-65, MIL-64)",
    pipeline: "Refresh-token rotation (MIL-74); per-org SCIM mapping (MIL-71)",
    idealWorld: "Pen-tested alpha; SOC 2 Type 1 attestation; passkey enrolment over 50% of partners",
  },
];

const CALLOUTS: Callout[] = [
  {
    eyebrow: "§AI",
    text: "Evidence-based model switching is audited in YAML. Haiku → qwen3:14b → Sonnet 4.6, with date and reason on each switch. Most AI shops cannot produce this audit trail.",
    why: "mil/config/model_routing.yaml",
    whyHref: `${REPO_BLOB}/mil/config/model_routing.yaml`,
  },
  {
    eyebrow: "§Software",
    text: "Secrets are rejected by name pattern at the publish-adapter API boundary, not at the filesystem or CI gate. A caller bug fails before disk write.",
    why: "MIL-110",
  },
  {
    eyebrow: "§Data",
    text: "Provenance fields signal_ids and teacher_model_version are structurally present but empty on most findings. We surface the empty fields by design — calibration debt is visible, not hidden.",
    why: "MIL-39",
  },
  {
    eyebrow: "§Security",
    text: "firm_slug is admin-set only. A compromised partner IdP + malicious user cannot self-assign rival firm context. Most SaaS vendors delegate firm assignment to the partner's IdP.",
    why: "MIL-152",
  },
];

// ── Render helpers ───────────────────────────────────────────────────

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function jiraLinkFor(why: string): string | null {
  // "MIL-123" or "PULSE-83" — Jira ticket form. Anything else is a path
  // or a freeform label and needs an explicit whyHref.
  const m = /^(MIL|PULSE)-\d+$/.exec(why);
  return m ? `${JIRA_BROWSE}/${why}` : null;
}

function whyAnchor(b: Bullet | Callout): string {
  const href = b.whyHref ?? jiraLinkFor(b.why);
  const label = `[why: ${escapeHtml(b.why)}]`;
  if (!href) return `<span class="why-label">${label}</span>`;
  return `<a class="why-link" href="${escapeHtml(href)}" target="_blank" rel="noopener">${label}</a>`;
}

function codeAnchor(b: Bullet): string {
  if (!b.codePath) return "";
  const href = `${REPO_BLOB}/${b.codePath}`;
  const label = `[code: ${escapeHtml(b.codeLabel ?? b.codePath)}]`;
  return `<a class="code-link" href="${escapeHtml(href)}" target="_blank" rel="noopener">${label}</a>`;
}

function renderBulletList(bullets: Bullet[]): string {
  return bullets
    .map(
      (b) => `<li>
      <span class="bullet-text">${escapeHtml(b.text)}</span>
      <span class="bullet-links">${codeAnchor(b)} ${whyAnchor(b)}</span>
    </li>`,
    )
    .join("\n");
}

function renderSection(s: Section): string {
  return `<section class="addressed-section voice-${s.voice}">
    <p class="section-eyebrow">${escapeHtml(s.eyebrow)} · ${escapeHtml(s.title)}</p>
    <ul class="bullets">
      ${renderBulletList(s.bullets)}
    </ul>
  </section>`;
}

function renderCallout(c: Callout): string {
  return `<div class="callout">
    <p class="callout-eyebrow">${escapeHtml(c.eyebrow)}</p>
    <p class="callout-text">${escapeHtml(c.text)}</p>
    <p class="callout-why">${whyAnchor(c)}</p>
  </div>`;
}

function renderTableRow(r: TableRow): string {
  // data-label drives the mobile-stacked layout (CSS-only, no JS).
  // Labels mirror the thead; on desktop they're hidden via thead {} rules.
  return `<tr>
    <th scope="row">${escapeHtml(r.discipline)}</th>
    <td data-label="Strengths">${escapeHtml(r.strengths)}</td>
    <td data-label="Pipeline">${escapeHtml(r.pipeline)}</td>
    <td data-label="Ideal world">${escapeHtml(r.idealWorld)}</td>
  </tr>`;
}

function renderAtAGlanceTable(): string {
  const rows = TABLE_ROWS.map(renderTableRow).join("\n");
  return `<section class="at-a-glance" aria-labelledby="at-a-glance-heading">
    <h2 id="at-a-glance-heading" class="bucket-h2">At a glance</h2>
    <p class="bucket-lede">Fast scan across the four lenses. Bullets below carry the falsifiable claims.</p>
    <table class="ag-table">
      <thead>
        <tr>
          <th scope="col">Discipline</th>
          <th scope="col">Strengths</th>
          <th scope="col">Pipeline</th>
          <th scope="col">Ideal world</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
    <p class="ag-legend">
      <span class="ag-legend-key">How to read this</span>
      <span class="ag-legend-item"><strong>Strengths</strong> — production today; every claim resolves to shipped code.</span>
      <span class="ag-legend-item"><strong>Pipeline</strong> — committed, ticket-tracked work in flight.</span>
      <span class="ag-legend-item"><strong>Ideal world</strong> — a specific control gated by a named blocker. <em>Not</em> a current attestation, not on the roadmap.</span>
    </p>
  </section>`;
}

const CSS = `
  :root {
    --ink:        #0A1E2A;
    --ink-soft:   #2C3E4D;
    --muted:      #6B7A85;
    --hairline:   #D8DFE5;
    --paper:      #FFFFFF;
    --cream:      #FAFAF7;
    --navy:       #00273D;
    --accent:     #003A5C;
    --accent-soft:#E8F0F5;
    --serif:      "Source Serif 4", Georgia, "Times New Roman", "DejaVu Serif", serif;
    --sans:       Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    --mono:       "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--paper); color: var(--ink);
    font-family: var(--sans); font-size: 16px; line-height: 1.55; }
  a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
  a:hover { border-bottom-color: var(--accent); }
  main { max-width: 50rem; margin: 3rem auto 6rem; padding: 0 1.75rem; }

  .topbar { border-bottom: 1px solid var(--hairline); padding: 18px 0; background: var(--paper); }
  .topbar-inner { display: flex; align-items: baseline; justify-content: space-between;
    max-width: 50rem; margin: 0 auto; padding: 0 1.75rem; }
  .brand { font-family: var(--serif); font-size: 20px; font-weight: 700; color: var(--ink); }
  .signout { font-size: 13px; color: var(--muted); }
  .signout:hover { color: var(--ink); border-bottom-color: var(--ink); }

  .header-strip { padding-top: 1.5rem; }
  .page-eyebrow { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.12em; margin: 0 0 0.6rem 0; }
  .opener { font-family: var(--serif); font-size: 1.55rem; line-height: 1.35;
    font-weight: 500; color: var(--ink); margin: 0 0 1.1rem 0; font-style: italic; }
  .meta-line { font-family: var(--mono); font-size: 0.78rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em; margin: 0; }

  .bucket-divider { border: 0; border-top: 1px solid var(--hairline);
    margin: 3rem 0 2rem 0; }
  .bucket-h2 { font-family: var(--serif); font-size: 1.3rem; font-weight: 600;
    color: var(--ink); margin: 0 0 0.45rem 0; }
  .bucket-lede { font-family: var(--sans); font-size: 0.9rem; color: var(--muted);
    margin: 0 0 1.6rem 0; font-style: italic; }

  .addressed-section { margin: 0 0 2rem 0; padding: 0; }
  .addressed-section.voice-clinical { padding-left: 0; }
  .section-eyebrow { font-family: var(--mono); font-size: 0.72rem; color: var(--ink-soft);
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0 0 0.85rem 0;
    padding-bottom: 0.35rem; border-bottom: 1px solid var(--hairline); }

  ul.bullets { list-style: none; padding: 0; margin: 0; }
  ul.bullets li { padding: 0.6rem 0; border-bottom: 1px dotted var(--hairline); }
  ul.bullets li:last-child { border-bottom: 0; }
  .bullet-text { display: block; color: var(--ink); font-size: 0.95rem; }
  .bullet-links { display: block; margin-top: 0.4rem; font-family: var(--mono);
    font-size: 0.72rem; color: var(--muted); }
  .code-link, .why-link { font-family: var(--mono); font-size: 0.72rem;
    color: var(--accent); margin-right: 0.85rem; word-break: break-all; }
  .why-label { font-family: var(--mono); font-size: 0.72rem; color: var(--muted); }

  .callouts { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
    margin-top: 2rem; }
  .callout { padding: 1rem 1.1rem; border: 1px solid var(--hairline);
    background: var(--cream); border-radius: 3px; }
  .callout-eyebrow { font-family: var(--mono); font-size: 0.7rem;
    color: var(--accent); text-transform: uppercase; letter-spacing: 0.1em;
    margin: 0 0 0.4rem 0; }
  .callout-text { font-family: var(--sans); font-size: 0.88rem; color: var(--ink);
    margin: 0 0 0.5rem 0; line-height: 1.5; }
  .callout-why { margin: 0; }

  .footer-meta { margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--hairline);
    font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em; }

  .at-a-glance { margin-top: 2rem; }
  .ag-table { width: 100%; border-collapse: collapse; font-family: var(--sans);
    font-size: 0.85rem; margin: 0 0 0.85rem 0; }
  .ag-table thead th { font-family: var(--mono); font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted);
    text-align: left; font-weight: 600; padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--ink); }
  .ag-table thead th:first-child { width: 7rem; }
  .ag-table tbody th { font-family: var(--serif); font-weight: 600;
    color: var(--ink); padding: 0.65rem 0.75rem; text-align: left;
    border-bottom: 1px dotted var(--hairline); white-space: nowrap;
    vertical-align: top; }
  .ag-table tbody td { color: var(--ink-soft); padding: 0.65rem 0.75rem;
    border-bottom: 1px dotted var(--hairline); vertical-align: top; line-height: 1.45; }
  .ag-table tbody tr:last-child th,
  .ag-table tbody tr:last-child td { border-bottom: 1px solid var(--hairline); }

  .ag-legend { margin: 0 0 0 0; padding: 0.75rem 0.85rem;
    background: var(--cream); border: 1px solid var(--hairline); border-radius: 3px;
    font-family: var(--sans); font-size: 0.78rem; color: var(--muted); line-height: 1.55; }
  .ag-legend-key { display: block; font-family: var(--mono); font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.1em; color: var(--ink-soft);
    margin-bottom: 0.35rem; }
  .ag-legend-item { display: block; margin: 0.15rem 0; }
  .ag-legend-item strong { color: var(--ink); font-weight: 600; }

  @media (max-width: 640px) {
    .callouts { grid-template-columns: 1fr; }
    .opener { font-size: 1.3rem; }
    /* On narrow screens, the 4-column table would force microscopic
       cells; collapse to label-stacked rows instead. CSS-only — no JS. */
    .ag-table thead { display: none; }
    .ag-table, .ag-table tbody, .ag-table tr,
    .ag-table th, .ag-table td { display: block; width: auto; }
    .ag-table tbody tr { padding: 0.85rem 0; border-bottom: 1px solid var(--hairline); }
    .ag-table tbody tr:last-child { border-bottom: 0; }
    .ag-table tbody th { padding: 0 0 0.4rem 0; white-space: normal;
      border-bottom: 0; font-size: 1rem; }
    .ag-table tbody td { padding: 0.2rem 0; border-bottom: 0; }
    .ag-table tbody td::before { content: attr(data-label); display: block;
      font-family: var(--mono); font-size: 0.65rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.1rem; }
  }
`;

export function renderEngineering(): string {
  const addressed = ADDRESSED_SECTIONS.map(renderSection).join("\n");
  const planned = renderBulletList(PLANNED);
  const considered = renderBulletList(CONSIDERED);
  const callouts = CALLOUTS.map(renderCallout).join("\n");

  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Engineering posture · CJI</title>
${FONTS_BLOCK}
<style>${CSS}</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="/portal" style="border-bottom:0">CJI</a>
    <a class="signout" href="https://login.cjipro.com/logout">Sign out</a>
  </div>
</header>
<main>

  <section class="header-strip">
    <p class="page-eyebrow">Engineering posture</p>
    <p class="opener">This system prefers honest ignorance to unverified certainty — every claim ships with an evidence id, every gap ships with a ticket number.</p>
    <p class="meta-line">Last reviewed: 2026-04-27 · Scope: public-signal market intelligence; air-gapped from internal banking systems by design.</p>
  </section>

  <hr class="bucket-divider">
  ${renderAtAGlanceTable()}

  <hr class="bucket-divider">
  <h2 class="bucket-h2">Addressed — in production today</h2>
  <p class="bucket-lede">Confessional voice in §AI and §Data; clinical voice in §Security and §Software. Every bullet resolves to evidence.</p>
  ${addressed}

  <hr class="bucket-divider">
  <h2 class="bucket-h2">Planned — committed work, ticket-tracked</h2>
  <p class="bucket-lede">In flight or imminent. Confessional in AI/Data, clinical in Security/Software.</p>
  <ul class="bullets">
    ${planned}
  </ul>

  <hr class="bucket-divider">
  <h2 class="bucket-h2">Considered — post-MVP, signal-driven, not committed</h2>
  <p class="bucket-lede">Each line names what would unblock it. Nothing here is on the roadmap; everything here is on the radar.</p>
  <ul class="bullets">
    ${considered}
  </ul>

  <hr class="bucket-divider">
  <h2 class="bucket-h2">One non-obvious claim per discipline</h2>
  <p class="bucket-lede">Four cards. The panel's strongest distinguishing claims, one per lens.</p>
  <div class="callouts">
    ${callouts}
  </div>

  <p class="footer-meta">Source: panel synthesis (MIL-159) · Build: MIL-160 · Page renders without inline JS</p>

</main>
</body>
</html>`;
}
