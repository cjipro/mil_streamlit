// MIL-151 + MIL-144 — /portal post-auth landing.
//
// Merged scope:
//   - MIL-151: identity strip, 90-day re-affirmation prompt, sign-out
//   - MIL-144: welcome line, briefing hero (Share / Forward), recent
//             dates strip, full product family with entitlement CTAs
//
// Single surface at /portal. Root `/` still 302s here (router.ts). The
// portal stays the default landing; magic-link callbacks may still
// deep-link to /sonar/{slug}/ via return_to. Refusal to confirm details
// does NOT block — Consumer Duty 2.0 touchpoint, not an auth gate.
//
// Entitlements are hardcoded for the alpha cohort: Reckoner + Sonar are
// always available; Pulse + Lever render as prospect CTAs. When an
// entitlements column lands on partner_profiles, swap `entitlements()`
// to read from the row.

import {
  confirmDetails,
  getProfile,
  needsReaffirmation,
  type PartnerProfile,
} from "../../approvals/src/partner_profiles";
import { lookupSessionEmail } from "../../approvals/src/sessions";
import { isAdmin } from "../../approvals/src/admin";
import { resolveFirm, type ResolvedFirm } from "./firm_resolution";
import { SUBJECTS } from "./subjects.generated";
import { FONTS_BLOCK } from "../../fonts_block/src/fonts_block.generated";

export interface PortalIdentity {
  sub: string;
  email: string;
}

export interface RecentDate {
  iso: string;   // YYYY-MM-DD
  label: string; // "Apr 27" / "Yesterday" / "Today"
}

export interface PortalRenderOptions {
  identity: PortalIdentity;
  profile: PartnerProfile | null;
  firm: ResolvedFirm;
  lastActiveAt: string | null;
  lastActiveCountry: string | null;
  promptReaffirmation: boolean;
  recentDates: RecentDate[]; // empty when firm not provisioned
  // MIL-156 — admin-internal users only. Currently-selected subject slug
  // (from the `__Host-cji_admin_subject` cookie via firm_resolution).
  // Used to highlight the right radio when the picker renders.
  // Partners ignore this; passing it has no effect on their render.
  adminSubjectChoice?: string;
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
  main { max-width: 50rem; margin: 3.5rem auto 5rem; padding: 0 1.75rem; }

  .topbar { border-bottom: 1px solid var(--hairline); padding: 18px 0; background: var(--paper); }
  .topbar-inner { display: flex; align-items: baseline; justify-content: space-between;
    max-width: 50rem; margin: 0 auto; padding: 0 1.75rem; }
  .brand { font-family: var(--serif); font-size: 20px; font-weight: 700; color: var(--ink); }
  .signout { font-size: 13px; color: var(--muted); }
  .signout:hover { color: var(--ink); border-bottom-color: var(--ink); }

  .welcome { font-family: var(--serif); font-size: 1.85rem; font-weight: 600;
    color: var(--ink); margin: 0 0 0.4rem 0; line-height: 1.25; }
  .welcome-firm { color: var(--accent); }
  .role-badge { display: inline-block; margin-left: 0.6rem; padding: 0.15rem 0.55rem;
    font-family: var(--mono); font-size: 0.65rem; text-transform: uppercase;
    letter-spacing: 0.1em; border: 1px solid var(--accent); color: var(--accent);
    background: var(--paper); border-radius: 2px; vertical-align: middle; }

  .identity { margin-top: 0.25rem; padding: 1.1rem 1.4rem;
    border: 1px solid var(--hairline); background: var(--cream); }
  .identity-line { font-family: var(--sans); font-size: 0.92rem; color: var(--ink-soft); margin: 0; }
  .identity-firm { font-family: var(--sans); font-size: 0.88rem; color: var(--muted);
    margin: 0.3rem 0 0 0; }
  .identity-meta { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.08em; margin: 0.7rem 0 0 0; }
  .identity-mismatch { font-size: 0.78rem; color: var(--muted); margin-top: 0.45rem; }

  .briefing-hero { margin-top: 2rem; padding: 1.75rem;
    border: 1px solid var(--accent); background: var(--accent-soft); }
  .briefing-eyebrow { font-family: var(--mono); font-size: 0.72rem; color: var(--accent);
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0 0 0.5rem 0; }
  .briefing-title { font-family: var(--serif); font-size: 1.3rem; font-weight: 600;
    color: var(--ink); margin: 0 0 1.25rem 0; line-height: 1.3; }
  .briefing-actions { display: flex; flex-wrap: wrap; gap: 0.6rem; }
  .briefing-actions .btn-primary,
  .briefing-actions .btn-secondary {
    padding: 0.6rem 1.1rem; font-family: var(--sans); font-size: 0.9rem;
    border-radius: 3px; border: 1px solid var(--accent); cursor: pointer; }
  .briefing-actions .btn-primary { background: var(--accent); color: #fff; }
  .briefing-actions .btn-primary:hover { background: var(--navy); border-color: var(--navy); }
  .briefing-actions .btn-secondary { background: var(--paper); color: var(--accent); }
  .briefing-actions .btn-secondary:hover { background: var(--accent); color: #fff; }
  .briefing-actions .btn-disabled {
    padding: 0.6rem 1.1rem; font-family: var(--sans); font-size: 0.9rem;
    border-radius: 3px; border: 1px solid var(--hairline); background: var(--paper);
    color: var(--muted); cursor: not-allowed; }

  .recent { margin-top: 1rem; font-family: var(--sans); font-size: 0.85rem; color: var(--muted); }
  .recent-label { text-transform: uppercase; font-family: var(--mono); font-size: 0.7rem;
    letter-spacing: 0.1em; color: var(--muted); margin-right: 0.6rem; }
  .recent a { color: var(--accent); margin-right: 0.5rem; }
  .recent a:not(:last-of-type)::after { content: "·"; color: var(--hairline);
    margin-left: 0.5rem; pointer-events: none; }
  .recent-all { margin-left: 0.4rem; }

  .confirm-block { margin-top: 2rem; padding: 1.75rem;
    border: 1px solid var(--hairline); background: var(--paper); }
  .confirm-eyebrow { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0 0 0.5rem 0; }
  .confirm-h2 { font-family: var(--serif); font-size: 1.1rem; font-weight: 600;
    color: var(--ink); margin: 0 0 0.5rem 0; }
  .confirm-lede { color: var(--ink-soft); font-size: 0.92rem; margin: 0 0 1.25rem 0; }
  label { display: block; font-size: 0.85rem; color: var(--ink-soft); margin: 0.75rem 0 0.25rem 0; }
  input[type="text"] { width: 100%; padding: 0.55rem 0.65rem; font: inherit;
    border: 1px solid #b7c2ca; border-radius: 3px; background: var(--paper); }
  .confirm-row { display: flex; gap: 0.6rem; align-items: center; margin-top: 1rem; }
  .confirm-btn { padding: 0.55rem 1.1rem; font: inherit; font-size: 0.9rem;
    background: var(--accent); color: #fff; border: 0; border-radius: 3px; cursor: pointer; }
  .confirm-btn:hover { background: var(--navy); }
  .confirm-skip { color: var(--muted); font-size: 0.85rem; }

  .last-confirmed { margin-top: 2rem; font-size: 0.82rem; color: var(--muted); }

  .products { margin-top: 3rem; }
  .products-eyebrow { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0 0 1rem 0; }
  .product-row { display: grid; grid-template-columns: minmax(11rem, 1fr) 1.7fr auto;
    gap: 1rem; align-items: center; padding: 1rem 0; border-top: 1px solid var(--hairline); }
  .product-row:last-child { border-bottom: 1px solid var(--hairline); }
  .product-name { font-family: var(--serif); font-size: 1rem; font-weight: 600; color: var(--ink); }
  .product-tagline { font-family: var(--sans); font-size: 0.88rem; color: var(--muted); }
  .product-cta { font-family: var(--sans); font-size: 0.85rem; padding: 0.45rem 0.9rem;
    border: 1px solid var(--accent); border-radius: 3px; color: var(--accent);
    background: var(--paper); white-space: nowrap; }
  .product-cta:hover { background: var(--accent); color: #fff; }
  .product-cta.muted { border-color: var(--hairline); color: var(--muted); }
  .product-cta.muted:hover { border-color: var(--ink); color: var(--ink); background: var(--paper); }
  .product-cta.here { border-color: var(--hairline); color: var(--muted); cursor: default; }
  .product-cta.here:hover { background: var(--paper); color: var(--muted); }

  @media (max-width: 640px) {
    .product-row { grid-template-columns: 1fr; gap: 0.4rem; }
    .product-row .product-cta { justify-self: start; margin-top: 0.4rem; }
    .briefing-actions { flex-direction: column; align-items: stretch; }
  }

  /* MIL-156 — admin subject picker. Hidden by default (no rule needed —
     renderAdminPicker emits empty string when SUBJECTS.length < 2). */
  .admin-picker { margin: 0 0 1.25rem 0; padding: 0.85rem 1rem;
    border: 1px solid var(--hairline); background: var(--cream); border-radius: 4px; }
  .picker-eyebrow { font-family: var(--mono); font-size: 0.7rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0 0 0.5rem 0; }
  .picker-row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .subject-pick { font-family: var(--sans); font-size: 0.88rem;
    padding: 0.35rem 0.7rem; border: 1px solid var(--hairline); border-radius: 3px;
    color: var(--ink-soft); background: var(--paper); text-decoration: none;
    border-bottom: 1px solid var(--hairline); }
  .subject-pick:hover { border-color: var(--accent); color: var(--accent); }
  .subject-pick-on { background: var(--accent); color: #fff; border-color: var(--accent); }
  .subject-pick-on:hover { background: var(--navy); border-color: var(--navy); color: #fff; }
`;

export function renderPortal(opts: PortalRenderOptions): string {
  const { identity, profile, firm, lastActiveAt, lastActiveCountry, promptReaffirmation, recentDates } = opts;
  const first = firstName(profile, identity.email);

  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Portal · CJI</title>
${FONTS_BLOCK}
<style>${CSS}</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <span class="brand">CJI</span>
    <a class="signout" href="https://login.cjipro.com/logout">Sign out</a>
  </div>
</header>
<main>

  ${renderWelcome(first, firm)}

  <section class="identity">
    <p class="identity-line">Signed in as <strong>${escapeHtml(identity.email)}</strong></p>
    <p class="identity-firm">${escapeHtml(firm.display_name)}</p>
    ${renderLastSignIn(lastActiveAt, lastActiveCountry)}
    <p class="identity-mismatch">
      Not you? <a href="https://login.cjipro.com/logout">Sign out</a> and sign back in.
    </p>
  </section>

  ${renderAdminPicker(firm, opts.adminSubjectChoice)}

  ${renderBriefingHero(firm)}

  ${renderRecentStrip(recentDates, firm)}

  ${promptReaffirmation
    ? renderConfirmBlock(profile)
    : renderLastConfirmedLine(profile?.last_confirmed_at ?? null)}

  ${renderProductFamily(firm)}

</main>
</body>
</html>`;
}

function renderWelcome(first: string, firm: ResolvedFirm): string {
  // For partners with a real firm context: "Welcome back, Alpha. Barclays workspace."
  // For admin/internal: "Welcome back, Hussain. CJI [INTERNAL]"
  // For unprovisioned: "Welcome back, Alpha." (no firm clause — there's nothing
  // honest to say until the admin sets one)
  const firstSafe = escapeHtml(first);
  if (firm.kind === "unprovisioned") {
    return `<h1 class="welcome">Welcome back, ${firstSafe}.</h1>`;
  }
  const firmSafe = escapeHtml(firm.display_name);
  const badge = firm.is_internal
    ? `<span class="role-badge">Internal</span>`
    : "";
  const firmClause = firm.is_internal
    ? `<span class="welcome-firm">${firmSafe}</span>${badge}`
    : `<span class="welcome-firm">${firmSafe}</span> workspace`;
  return `<h1 class="welcome">Welcome back, ${firstSafe}. ${firmClause}.</h1>`;
}

// ── Sections ─────────────────────────────────────────────────────────

function renderBriefingHero(firm: ResolvedFirm): string {
  if (!firm.has_briefing || !firm.slug) {
    return `<section class="briefing-hero" aria-disabled="true">
      <p class="briefing-eyebrow">Today's briefing</p>
      <h2 class="briefing-title">Your briefing will appear here once your firm is provisioned.</h2>
      <div class="briefing-actions">
        <span class="btn-disabled">Open</span>
        <span class="btn-disabled">Share with team</span>
        <span class="btn-disabled">Forward by email</span>
      </div>
    </section>`;
  }
  // MIL-145 sibling will replace mailto: with token-based share links and
  // forward-detection audit-tagging. Until then, mailto: is the affordance —
  // partner copies the link into Outlook / Gmail and forwards manually.
  // Internal admins get the same hero pointed at the default subject — the
  // briefing-title names the subject explicitly so it doesn't read as
  // "your" briefing for the CJI team.
  const subjectLabel = firm.is_internal
    ? `${firm.display_name === "CJI" ? "Today's Sonar briefing" : firm.display_name}`
    : `Today's Sonar briefing for ${firm.display_name}`;
  const heroTitle = firm.is_internal
    ? `Today's Sonar briefing — ${escapeHtml(slugDisplayFor(firm))}`
    : `Today's Sonar briefing for ${escapeHtml(firm.display_name)}`;
  const briefingUrl = `https://app.cjipro.com/sonar/${escapeAttr(firm.slug)}/`;
  const shareSubject = encodeURIComponent(`Today's CJI Sonar briefing — ${subjectLabel}`);
  const shareBody = encodeURIComponent(`Today's briefing:\n${briefingUrl}\n\n— shared via CJI Sonar`);
  const mailto = `mailto:?subject=${shareSubject}&body=${shareBody}`;
  return `<section class="briefing-hero">
    <p class="briefing-eyebrow">Today's briefing</p>
    <h2 class="briefing-title">${heroTitle}</h2>
    <div class="briefing-actions">
      <a class="btn-primary" href="/sonar/${escapeAttr(firm.slug)}/">Open</a>
      <a class="btn-secondary" href="${mailto}">Share with team</a>
      <a class="btn-secondary" href="${mailto}">Forward by email</a>
    </div>
  </section>`;
}

// For admin-internal: surface the actual subject's display name in the
// hero title, since "CJI workspace" is the partner-context label but the
// briefing itself is FOR a specific subject. MIL-156 — refactored from
// a hardcoded if-chain to a SUBJECTS-driven lookup so the picker and the
// hero title always agree on display names.
function slugDisplayFor(firm: ResolvedFirm): string {
  if (!firm.slug) return "";
  const hit = SUBJECTS.find((s) => s.slug === firm.slug);
  return hit?.display ?? firm.slug;
}

// MIL-156 — multi-subject admin picker.
//
// Hidden when SUBJECTS.length === 1 (the default-and-only-subject case
// today, barclays). Visible only on the admin-internal branch — partners
// have a fixed firm and never see this strip even when multiple subjects
// exist. Each option is a plain GET link to /portal?subject=<slug>; the
// handler in index.ts validates, sets the `__Host-cji_admin_subject`
// cookie, and 303s back to /portal so the URL stays clean.
function renderAdminPicker(firm: ResolvedFirm, currentSubject?: string): string {
  if (firm.kind !== "admin-internal") return "";
  if (SUBJECTS.length < 2) return "";
  const selected = currentSubject ?? firm.slug ?? SUBJECTS[0]!.slug;
  const options = SUBJECTS.map((s) => {
    const isOn = s.slug === selected;
    const cls = isOn ? "subject-pick subject-pick-on" : "subject-pick";
    const ariaCurrent = isOn ? ' aria-current="true"' : "";
    return `<a class="${cls}" href="/portal?subject=${escapeAttr(s.slug)}"${ariaCurrent}>${escapeHtml(s.display)}</a>`;
  }).join("");
  return `<section class="admin-picker" aria-label="Subject picker (admin)">
    <p class="picker-eyebrow">Viewing as CJI Internal — subject:</p>
    <div class="picker-row" role="group">${options}</div>
  </section>`;
}

function renderRecentStrip(dates: RecentDate[], firm: ResolvedFirm): string {
  if (!firm.slug || !firm.has_briefing || dates.length === 0) return "";
  const links = dates
    .map(
      (d) =>
        `<a href="/sonar/${escapeAttr(firm.slug!)}/${escapeAttr(d.iso)}/">${escapeHtml(d.label)}</a>`,
    )
    .join("");
  return `<p class="recent">
    <span class="recent-label">Recent</span>
    ${links}
    <a class="recent-all" href="/sonar/${escapeAttr(firm.slug)}/">All briefings →</a>
  </p>`;
}

function renderProductFamily(firm: ResolvedFirm): string {
  // Alpha entitlements: Reckoner + Sonar always; Pulse + Lever as prospects.
  // Sonar shows "(you are here)" since the briefing hero is the dominant
  // motion above. Reckoner is "Open" not "Start free trial" — alpha cohort
  // is already inside the trial perimeter.
  return `<section class="products">
    <p class="products-eyebrow">All CJI products</p>
    <div class="product-row">
      <div class="product-name">CJI Reckoner</div>
      <div class="product-tagline">Industry intelligence</div>
      <a class="product-cta" href="/reckoner">Open →</a>
    </div>
    <div class="product-row">
      <div class="product-name">CJI Sonar</div>
      <div class="product-tagline">Daily firm briefing</div>
      ${
        firm.slug && firm.has_briefing
          ? `<a class="product-cta here" href="/sonar/${escapeAttr(firm.slug)}/">You're here</a>`
          : `<span class="product-cta here">You're here</span>`
      }
    </div>
    <div class="product-row">
      <div class="product-name">CJI Pulse</div>
      <div class="product-tagline">Live insight — coming 2026</div>
      <a class="product-cta muted" href="mailto:hello@cjipro.com?subject=CJI%20Pulse%20design%20partner">Join design partners</a>
    </div>
    <div class="product-row">
      <div class="product-name">CJI Lever</div>
      <div class="product-tagline">Tailored decision framework — design partners only</div>
      <a class="product-cta muted" href="mailto:hello@cjipro.com?subject=CJI%20Lever%20enquiry">Talk to us</a>
    </div>
  </section>`;
}

function renderLastSignIn(ts: string | null, country: string | null): string {
  if (!ts) {
    return `<p class="identity-meta">First sign-in</p>`;
  }
  const human = humanTime(ts);
  const where = country ? ` from ${escapeHtml(country)}` : "";
  return `<p class="identity-meta">Last seen ${escapeHtml(human)}${where}</p>`;
}

function renderConfirmBlock(profile: PartnerProfile | null): string {
  const dn = profile?.display_name ?? "";
  const role = profile?.role ?? "";
  return `<form class="confirm-block" method="post" action="/portal/confirm">
    <p class="confirm-eyebrow">Confirm your details</p>
    <h2 class="confirm-h2">Quick check — still you?</h2>
    <p class="confirm-lede">We periodically ask partners to reaffirm their details. Optional fields are blank.</p>
    <label for="display_name">Name (optional)</label>
    <input id="display_name" name="display_name" type="text" value="${escapeAttr(dn)}" autocomplete="name">
    <label for="role">Role (optional)</label>
    <input id="role" name="role" type="text" value="${escapeAttr(role)}" autocomplete="organization-title">
    <div class="confirm-row">
      <button class="confirm-btn" type="submit">Confirm</button>
      <a class="confirm-skip" href="/portal?skip=1">Not now</a>
    </div>
  </form>`;
}

function renderLastConfirmedLine(ts: string | null): string {
  if (!ts) return "";
  return `<p class="last-confirmed">Details last confirmed: ${escapeHtml(humanTime(ts))}</p>`;
}

// ── Helpers ──────────────────────────────────────────────────────────

// First-name extraction: prefer the first whitespace-separated token of
// display_name; fall back to the email local-part with first letter
// capitalised. Empty/unset display_name OR malformed email both land on
// the email-prefix path; if that's also empty (shouldn't happen) we
// return "there" as a last-ditch friendly fallback.
export function firstName(profile: PartnerProfile | null, email: string): string {
  const dn = profile?.display_name?.trim();
  if (dn) {
    const first = dn.split(/\s+/)[0];
    if (first) return first;
  }
  const local = email.split("@")[0] ?? "";
  if (local) return local.charAt(0).toUpperCase() + local.slice(1);
  return "there";
}

// Recent date strip: today + previous (count-1) days, formatted as
// "Today" / "Yesterday" / "Apr 25" etc. Server-side computation only
// (the page has no JS); UTC is used for ISO slugs since /sonar/{slug}/
// historical paths are UTC-day-keyed by run_daily.py.
export function buildRecentDates(now: Date, count = 3): RecentDate[] {
  const out: RecentDate[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i));
    out.push({ iso: isoDate(d), label: relativeDayLabel(d, i) });
  }
  return out;
}

function isoDate(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function relativeDayLabel(d: Date, i: number): string {
  if (i === 0) return "Today";
  if (i === 1) return "Yesterday";
  return `${MONTHS_SHORT[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

// Lightweight relative-time formatter — server-side, no JS needed.
// Falls back to ISO date for >30 days.
function humanTime(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const ageMs = Date.now() - t;
  const min = Math.floor(ageMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hr ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} day${day === 1 ? "" : "s"} ago`;
  return iso.slice(0, 10);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(s: string): string {
  return escapeHtml(s);
}

// ── Handler façade ───────────────────────────────────────────────────

export interface PortalEnv {
  AUDIT_DB: D1Database;
}

// MIL-156 — picker-switch handler.
//
// Called from index.ts when the request URL is `/portal?subject=<slug>`.
// Validates the slug against SUBJECTS, sets the `__Host-cji_admin_subject`
// cookie if valid (or clears it if the slug is unknown), and 303s back to
// /portal so the URL stays clean. Caller is responsible for emitting the
// `portal.admin_subject_switched` audit event with the old + new slugs —
// this function returns the (oldSlug, newSlug) tuple so the audit step
// can be done outside, where the env binding is available.
export interface AdminSubjectSwitchResult {
  response: Response;
  oldSlug: string | null;
  newSlug: string;
}

export const ADMIN_SUBJECT_COOKIE_NAME = "__Host-cji_admin_subject";

export function handleAdminSubjectSwitch(
  requestedSlug: string | null,
  currentCookie: string | null,
): AdminSubjectSwitchResult {
  const valid = requestedSlug
    ? SUBJECTS.find((s) => s.slug === requestedSlug)
    : undefined;
  // Default fallback (unknown slug) → clear cookie + redirect anyway.
  const newSlug = valid?.slug ?? SUBJECTS[0]!.slug;
  const setCookie = valid
    ? buildAdminSubjectCookie(valid.slug)
    : clearAdminSubjectCookie();
  return {
    response: new Response(null, {
      status: 303,
      headers: {
        location: "/portal",
        "set-cookie": setCookie,
        "cache-control": "no-store",
      },
    }),
    oldSlug: currentCookie ?? null,
    newSlug,
  };
}

function buildAdminSubjectCookie(slug: string): string {
  // __Host- prefix invariants: Path=/, Secure, no Domain. SameSite=Lax
  // because the picker click is a top-level GET navigation. Max-Age 30d.
  return [
    `${ADMIN_SUBJECT_COOKIE_NAME}=${slug}`,
    "Path=/",
    "Secure",
    "HttpOnly",
    "SameSite=Lax",
    "Max-Age=2592000",
  ].join("; ");
}

function clearAdminSubjectCookie(): string {
  return [
    `${ADMIN_SUBJECT_COOKIE_NAME}=`,
    "Path=/",
    "Secure",
    "HttpOnly",
    "SameSite=Lax",
    "Max-Age=0",
  ].join("; ");
}

export async function handleGetPortal(
  identity: PortalIdentity,
  env: PortalEnv,
  lastActiveAt: string | null,
  now: Date = new Date(),
  // MIL-156 — value of the `__Host-cji_admin_subject` cookie if present.
  // Only consulted on the admin-internal branch; other firm kinds ignore.
  adminSubjectCookie: string | null = null,
): Promise<Response> {
  const profile = await getProfile(env.AUDIT_DB, identity.sub);
  const adminFlag = await isAdmin(env.AUDIT_DB, identity.email);
  const firm = resolveFirm(profile, identity.email, adminFlag, adminSubjectCookie);
  const promptReaffirmation = needsReaffirmation(profile, now);
  const recentDates = firm.has_briefing ? buildRecentDates(now, 3) : [];
  const html = renderPortal({
    identity,
    profile,
    firm,
    lastActiveAt,
    lastActiveCountry: null,
    promptReaffirmation,
    recentDates,
    adminSubjectChoice: firm.kind === "admin-internal" ? firm.slug ?? undefined : undefined,
  });
  return new Response(html, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "strict-origin-when-cross-origin",
    },
  });
}

export interface ConfirmHandlerOutcome {
  status: number;
  redirectTo?: string;
  body?: string;
  fields_changed: string[];
  prev_hash: string | null;
  new_hash: string | null;
}

export async function handlePostConfirm(
  identity: PortalIdentity,
  env: PortalEnv,
  formData: FormData,
  now: Date = new Date(),
): Promise<{ response: Response; outcome: ConfirmHandlerOutcome }> {
  const display = (formData.get("display_name") ?? "").toString().trim() || null;
  const role = (formData.get("role") ?? "").toString().trim() || null;

  const result = await confirmDetails(
    env.AUDIT_DB,
    identity.sub,
    { display_name: display, role },
    now,
  );

  if ("kind" in result) {
    return {
      response: redirectToPortal(),
      outcome: {
        status: 302,
        redirectTo: "/portal",
        fields_changed: [],
        prev_hash: null,
        new_hash: null,
      },
    };
  }
  return {
    response: redirectToPortal(),
    outcome: {
      status: 302,
      redirectTo: "/portal",
      fields_changed: result.fields_changed,
      prev_hash: result.prev_hash,
      new_hash: result.new_hash,
    },
  };
}

export { lookupSessionEmail };

// Workers' Response.redirect requires an absolute URL. handlePostConfirm
// has no request context, so a relative Location header is used (legal
// per RFC 7231 §7.1.2 — modern Workers runtime accepts it).
function redirectToPortal(): Response {
  return new Response(null, {
    status: 302,
    headers: { location: "/portal" },
  });
}
