// MIL-92 — Reckoner default surface
//
// The cohort-agnostic landing view of CJI Reckoner. Three sections:
//
//   1. INDUSTRY PULSE — top patterns surfaced this week, ranked by
//      severity-weighted volume across the regulated-consumer cohort.
//   2. ANOMALIES — patterns that diverged from baseline on this run,
//      anchored to the CJI Chronicle entry they rhyme with.
//   3. DECISIONS SURFACED — patterns escalated to a Clark tier and
//      ready to be addressed (CLARK-2 ESCALATE, CLARK-3 ACT NOW).
//
// MVP behaviour: the page renders from a typed ReckonerSnapshot
// argument. The Worker passes a baked-in MVP snapshot today; a
// follow-up ticket wires the snapshot from mil/outputs/mil_findings
// and benchmark_history via a daily build step or D1 sync.
//
// Not yet implemented (deliberate — Reckoner has three interface
// modes per the brand spine; this is "default surfacing" only):
//   - Conversational drill-in (MIL-93)
//   - Drag-drop canvas (post-MIL-93)
// Tabs render but the non-default modes are disabled in MVP.

export type ClarkTier = "CLARK-0" | "CLARK-1" | "CLARK-2" | "CLARK-3";
export type Trend = "WORSENING" | "STABLE" | "IMPROVING";

export interface IndustryPulseRow {
  pattern: string;          // human-readable issue label
  cohort_share: number;     // 0..1, fraction of cohort with the signal
  severity: "P0" | "P1" | "P2";
  trend: Trend;
}

export interface AnomalyRow {
  pattern: string;
  competitor: string;       // anonymised "Peer A" allowed in alpha
  chronicle_id: string;     // "CHR-007" etc.
  confidence: "evidenced" | "directional" | "early";
  baseline_delta_pp: number; // percentage points vs 90d baseline
}

export interface DecisionRow {
  pattern: string;
  competitor: string;
  clark: ClarkTier;
  audience: string;         // "product leadership", "ExCo", etc.
  cadence: string;          // "this week", "next 24h"
  artefact: string;         // "formal brief", "live runbook"
}

export interface ReckonerSnapshot {
  generated_at: string;     // ISO 8601
  run_number: number;
  corpus_size: number;      // total enriched records
  cohort_label: string;     // "UK retail banking · 6 firms · 6 sources"
  industry_pulse: IndustryPulseRow[];
  anomalies: AnomalyRow[];
  decisions: DecisionRow[];
  is_alpha_preview: boolean; // banner gate
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
    --p0:         #B0341A;
    --p1:         #B07A1F;
    --p2:         #6B7A85;
    --worsening:  #B0341A;
    --improving:  #1F7A4C;
    --stable:     #6B7A85;
    --serif:      Georgia, "Times New Roman", "DejaVu Serif", serif;
    --sans:       -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    --mono:       "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: var(--paper); color: var(--ink);
    font-family: var(--sans); font-size: 15px; line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
  a:hover { border-bottom-color: var(--accent); }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 0 28px; }

  /* ── Topbar ───────────────────────────────────────────── */
  .topbar { border-bottom: 1px solid var(--hairline); padding: 14px 0; background: var(--paper); }
  .topbar-inner { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
  .brand-mark { display: flex; align-items: baseline; gap: 14px; }
  .brand { font-family: var(--serif); font-size: 19px; font-weight: 700; color: var(--ink); }
  .product-name { font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 1.6px; color: var(--muted); }
  .meta-strip { font-family: var(--mono); font-size: 11px; color: var(--muted); letter-spacing: 0.4px; }
  .meta-strip span + span::before { content: " · "; padding: 0 4px; color: var(--hairline); }

  /* ── Alpha banner ─────────────────────────────────────── */
  .alpha-banner {
    background: var(--cream); border-bottom: 1px solid var(--hairline);
    padding: 10px 0; font-family: var(--mono); font-size: 11px;
    text-transform: uppercase; letter-spacing: 1.4px; color: var(--accent);
  }

  /* ── Tab strip ────────────────────────────────────────── */
  .tabs { border-bottom: 1px solid var(--hairline); padding: 14px 0 0 0; background: var(--paper); }
  .tabs-inner { display: flex; gap: 6px; align-items: flex-end; }
  .tab {
    font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 1.4px;
    padding: 10px 14px 12px; border: 0; border-bottom: 2px solid transparent;
    background: transparent; color: var(--muted); cursor: pointer;
  }
  .tab.active { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
  .tab.disabled { color: var(--hairline); cursor: not-allowed; }
  .tab-coming { display: inline-block; margin-left: 6px; font-size: 9px; color: var(--coming, #B07A1F); letter-spacing: 1.2px; }

  /* ── Section heading + scaffolding ────────────────────── */
  section { padding: 36px 0; }
  section + section { border-top: 1px solid var(--hairline); }
  .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
  .section-eyebrow { font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 1.6px; color: var(--muted); }
  h2 { font-family: var(--serif); font-size: 24px; font-weight: 700; line-height: 1.2; margin: 4px 0 0 0; color: var(--ink); letter-spacing: -0.2px; }
  .section-lede { font-family: var(--serif); font-size: 16px; line-height: 1.55; color: var(--ink-soft); max-width: 680px; margin: 0 0 18px 0; }

  /* ── KPI strip (Industry Pulse) ───────────────────────── */
  .kpi-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 16px 0 24px 0; }
  .kpi {
    border: 1px solid var(--hairline); padding: 16px 18px; background: var(--paper);
  }
  .kpi-label { font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--muted); margin-bottom: 6px; }
  .kpi-value { font-family: var(--mono); font-size: 22px; font-weight: 600; color: var(--ink); }
  .kpi-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }

  /* ── Pattern table (shared) ───────────────────────────── */
  table.patterns {
    width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 8px;
  }
  table.patterns th {
    font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--muted); font-weight: 600; text-align: left;
    padding: 10px 12px; border-bottom: 1px solid var(--hairline);
  }
  table.patterns td {
    padding: 14px 12px; border-bottom: 1px solid var(--hairline); vertical-align: top;
  }
  table.patterns td.pattern { font-family: var(--serif); font-size: 16px; color: var(--ink); }
  table.patterns td.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
  table.patterns td.muted { color: var(--muted); }

  .badge {
    display: inline-block; font-family: var(--mono); font-size: 10px;
    text-transform: uppercase; letter-spacing: 1.2px; padding: 2px 8px; font-weight: 600;
  }
  .badge.p0 { color: var(--p0); background: #F8E5DF; }
  .badge.p1 { color: var(--p1); background: #FAF1E2; }
  .badge.p2 { color: var(--p2); background: #ECEEF0; }

  .arrow.worsening { color: var(--worsening); }
  .arrow.stable    { color: var(--stable); }
  .arrow.improving { color: var(--improving); }

  .conf {
    font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px;
    padding: 2px 8px; font-weight: 600;
  }
  .conf.evidenced   { color: #1F4D7A; background: #E6EEF4; }
  .conf.directional { color: var(--p1);  background: #FAF1E2; }
  .conf.early       { color: var(--muted); background: #ECEEF0; }

  .clark {
    font-family: var(--mono); font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.4px; padding: 2px 8px;
  }
  .clark.t0 { color: var(--muted); background: #ECEEF0; }
  .clark.t1 { color: var(--p2);    background: #ECEEF0; }
  .clark.t2 { color: var(--p1);    background: #FAF1E2; }
  .clark.t3 { color: var(--p0);    background: #F8E5DF; }

  /* ── Footer ───────────────────────────────────────────── */
  footer {
    border-top: 1px solid var(--hairline); padding: 28px 0 24px 0; margin-top: 36px;
    font-size: 12px; color: var(--muted);
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 16px;
  }
  footer a { color: var(--muted); margin-left: 14px; }
  footer a:first-child { margin-left: 0; }
  footer a:hover { color: var(--ink); border-bottom-color: var(--ink); }

  @media (max-width: 720px) {
    .kpi-strip { grid-template-columns: 1fr; }
    table.patterns { font-size: 13px; }
    table.patterns td.pattern { font-size: 15px; }
    .topbar-inner { flex-direction: column; align-items: flex-start; gap: 8px; }
    .tabs-inner { overflow-x: auto; }
    h2 { font-size: 21px; }
  }
`;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderIndustryPulse(rows: IndustryPulseRow[]): string {
  if (!rows.length) {
    return `<p class="section-lede">No patterns surfaced this run.</p>`;
  }
  const body = rows
    .map((r) => {
      const sevCls = r.severity.toLowerCase();
      const arrow =
        r.trend === "WORSENING" ? "↑" : r.trend === "IMPROVING" ? "↓" : "→";
      const arrowCls = r.trend.toLowerCase();
      return `
        <tr>
          <td class="pattern">${escapeHtml(r.pattern)}</td>
          <td class="num">${(r.cohort_share * 100).toFixed(0)}%</td>
          <td><span class="badge ${sevCls}">${escapeHtml(r.severity)}</span></td>
          <td><span class="arrow ${arrowCls}">${arrow}</span> <span class="muted">${escapeHtml(r.trend)}</span></td>
        </tr>`;
    })
    .join("");
  return `
    <table class="patterns">
      <thead>
        <tr>
          <th>Pattern</th>
          <th>Cohort share</th>
          <th>Severity</th>
          <th>Trend</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderAnomalies(rows: AnomalyRow[]): string {
  if (!rows.length) {
    return `<p class="section-lede">No anomalies surfaced this run. Cohort tracking baseline.</p>`;
  }
  const body = rows
    .map((r) => {
      const sign = r.baseline_delta_pp >= 0 ? "+" : "";
      return `
        <tr>
          <td class="pattern">${escapeHtml(r.pattern)}</td>
          <td class="muted">${escapeHtml(r.competitor)}</td>
          <td class="num">${escapeHtml(r.chronicle_id)}</td>
          <td class="num">${sign}${r.baseline_delta_pp.toFixed(1)} pp</td>
          <td><span class="conf ${r.confidence}">${escapeHtml(r.confidence)}</span></td>
        </tr>`;
    })
    .join("");
  return `
    <table class="patterns">
      <thead>
        <tr>
          <th>Pattern</th>
          <th>Subject</th>
          <th>Anchor</th>
          <th>Δ vs 90d</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderDecisions(rows: DecisionRow[]): string {
  if (!rows.length) {
    return `<p class="section-lede">No patterns escalated to a Clark tier this run. The cohort is quiet.</p>`;
  }
  const body = rows
    .map((r) => {
      const tier = r.clark.split("-")[1] ?? "0";
      return `
        <tr>
          <td class="pattern">${escapeHtml(r.pattern)}</td>
          <td class="muted">${escapeHtml(r.competitor)}</td>
          <td><span class="clark t${tier}">${escapeHtml(r.clark)}</span></td>
          <td class="muted">${escapeHtml(r.audience)} · ${escapeHtml(r.cadence)}</td>
          <td class="muted">${escapeHtml(r.artefact)}</td>
        </tr>`;
    })
    .join("");
  return `
    <table class="patterns">
      <thead>
        <tr>
          <th>Pattern</th>
          <th>Subject</th>
          <th>Tier</th>
          <th>Audience &amp; cadence</th>
          <th>Artefact</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
}

export function renderReckonerHtml(snap: ReckonerSnapshot): string {
  const totalP0 = snap.industry_pulse.filter((r) => r.severity === "P0").length;
  const worsening = snap.industry_pulse.filter((r) => r.trend === "WORSENING").length;
  const anchored = snap.anomalies.length;
  const banner = snap.is_alpha_preview
    ? `<div class="alpha-banner"><div class="wrap">Alpha preview · illustrative content · live data wiring follow-up</div></div>`
    : "";
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CJI Reckoner — Industry intelligence</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'none'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'">
<meta http-equiv="X-Content-Type-Options" content="nosniff">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta http-equiv="Permissions-Policy" content="camera=(), microphone=(), geolocation=(), payment=(), usb=()">
<meta name="robots" content="noindex,nofollow">
<style>${CSS}</style>
</head>
<body>

<header class="topbar">
  <div class="wrap topbar-inner">
    <div class="brand-mark">
      <span class="brand">CJI</span>
      <span class="product-name">Reckoner</span>
    </div>
    <div class="meta-strip">
      <span>${escapeHtml(snap.cohort_label)}</span>
      <span>Run #${snap.run_number}</span>
      <span>${escapeHtml(snap.generated_at)}</span>
      <span>${snap.corpus_size.toLocaleString("en-GB")} signals</span>
    </div>
  </div>
</header>

${banner}

<nav class="tabs">
  <div class="wrap tabs-inner">
    <button class="tab active" type="button" aria-current="page">Default surface</button>
    <button class="tab disabled" type="button" disabled aria-disabled="true">Conversational drill-in <span class="tab-coming">Coming</span></button>
    <button class="tab disabled" type="button" disabled aria-disabled="true">Drag-drop canvas <span class="tab-coming">Coming</span></button>
  </div>
</nav>

<main>

  <section>
    <div class="wrap">
      <div class="section-head">
        <div>
          <div class="section-eyebrow">Section 01 · Aggregate</div>
          <h2>Industry Pulse</h2>
        </div>
      </div>
      <p class="section-lede">
        Top patterns surfaced across the cohort in the last 7 days, ranked
        by severity-weighted volume. Reckoner anchors each to the CJI
        Chronicle precedent it rhymes with.
      </p>

      <div class="kpi-strip">
        <div class="kpi">
          <div class="kpi-label">Cohort signal volume</div>
          <div class="kpi-value">${snap.corpus_size.toLocaleString("en-GB")}</div>
          <div class="kpi-sub">enriched signals · 90d rolling</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">P0 patterns active</div>
          <div class="kpi-value">${totalP0}</div>
          <div class="kpi-sub">blocking-class issues across cohort</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Worsening trend</div>
          <div class="kpi-value">${worsening}</div>
          <div class="kpi-sub">patterns with negative slope vs baseline</div>
        </div>
      </div>

      ${renderIndustryPulse(snap.industry_pulse)}
    </div>
  </section>

  <section>
    <div class="wrap">
      <div class="section-head">
        <div>
          <div class="section-eyebrow">Section 02 · Awareness</div>
          <h2>Anomalies</h2>
        </div>
      </div>
      <p class="section-lede">
        Patterns that diverged from the 90-day cohort baseline on this run.
        Each is anchored to a CJI Chronicle entry — the closest sector
        precedent — with a confidence flag.
      </p>
      <p class="section-lede" style="font-size: 14px; color: var(--muted);">
        ${anchored} anomal${anchored === 1 ? "y" : "ies"} surfaced this run.
      </p>
      ${renderAnomalies(snap.anomalies)}
    </div>
  </section>

  <section>
    <div class="wrap">
      <div class="section-head">
        <div>
          <div class="section-eyebrow">Section 03 · Action</div>
          <h2>Decisions Surfaced</h2>
        </div>
      </div>
      <p class="section-lede">
        Patterns that have crossed a Clark tier and are ready to be put in
        front of an accountable audience. The decision lives with the firm;
        Reckoner names the artefact and the cadence.
      </p>
      ${renderDecisions(snap.decisions)}
    </div>
  </section>

</main>

<footer>
  <div class="wrap" style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 16px; width: 100%;">
    <div>&copy; 2026 CJI · Reckoner default surface (alpha)</div>
    <div>
      <a href="https://cjipro.com/insights/methodology/">Methodology</a>
      <a href="https://cjipro.com/security/">Security</a>
      <a href="https://cjipro.com/privacy/">Privacy</a>
      <a href="mailto:hello@cjipro.com">Contact</a>
    </div>
  </div>
</footer>

</body>
</html>`;
}

// MVP snapshot — illustrative content for the alpha preview banner.
// Numbers are realistic (drawn from the live Run #59 corpus shape:
// ~7,418 records, 138 findings, 7 Designed Ceiling, churn 50.8
// WORSENING) but specific patterns + competitor pseudonyms here are
// illustrative until the data wiring lands. Replacing this constant
// with a snapshot read from D1 / mil_findings is the next ticket.
export function mvpSnapshot(): ReckonerSnapshot {
  return {
    generated_at: new Date().toISOString(),
    run_number: 59,
    corpus_size: 7418,
    cohort_label: "UK retail banking · 6 firms · 6 sources",
    industry_pulse: [
      {
        pattern: "Login failure on biometric retry",
        cohort_share: 0.42,
        severity: "P0",
        trend: "WORSENING",
      },
      {
        pattern: "Account locked after card replacement",
        cohort_share: 0.31,
        severity: "P0",
        trend: "WORSENING",
      },
      {
        pattern: "App crashing on launch (older Android)",
        cohort_share: 0.27,
        severity: "P1",
        trend: "STABLE",
      },
      {
        pattern: "Transfer delays on faster-payments cut-off",
        cohort_share: 0.19,
        severity: "P1",
        trend: "WORSENING",
      },
      {
        pattern: "Statement download formatting drift",
        cohort_share: 0.12,
        severity: "P2",
        trend: "STABLE",
      },
    ],
    anomalies: [
      {
        pattern: "Biometric retry loop",
        competitor: "Peer A",
        chronicle_id: "CHR-007",
        confidence: "evidenced",
        baseline_delta_pp: 11.4,
      },
      {
        pattern: "Account-locked → branch resolution required",
        competitor: "Peer C",
        chronicle_id: "CHR-018",
        confidence: "evidenced",
        baseline_delta_pp: 8.2,
      },
      {
        pattern: "Push-notification silence on transfer fail",
        competitor: "Peer B",
        chronicle_id: "CHR-005",
        confidence: "directional",
        baseline_delta_pp: 4.7,
      },
      {
        pattern: "App-Store version regression chatter",
        competitor: "Peer D",
        chronicle_id: "CHR-002",
        confidence: "early",
        baseline_delta_pp: 2.3,
      },
    ],
    decisions: [
      {
        pattern: "Biometric retry loop",
        competitor: "Peer A",
        clark: "CLARK-3",
        audience: "ExCo",
        cadence: "next 24h",
        artefact: "live runbook + customer comms",
      },
      {
        pattern: "Account-locked → branch resolution",
        competitor: "Peer C",
        clark: "CLARK-2",
        audience: "product leadership",
        cadence: "this week",
        artefact: "formal brief",
      },
    ],
    is_alpha_preview: true,
  };
}
