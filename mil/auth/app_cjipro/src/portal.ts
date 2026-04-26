// MIL-151 — /portal post-auth landing.
//
// Thin shim over the partner_profiles row. Three blocks:
//   1. Identity strip — who you are, where you signed in last, sign-out
//   2. Confirm details — soft prompt, only when stale (>90d / null)
//   3. Two CTAs — Today's briefing (firm-scoped) + Open Reckoner
//
// The portal is the default landing; magic-link callbacks may still
// deep-link to /sonar/{slug}/ via return_to. Refusal to confirm
// details does NOT block — it's a Consumer Duty 2.0 touchpoint, not
// an auth gate.

import {
  confirmDetails,
  getProfile,
  needsReaffirmation,
  type PartnerProfile,
} from "../../approvals/src/partner_profiles";
import { lookupSessionEmail } from "../../approvals/src/sessions";

export interface PortalIdentity {
  sub: string;
  email: string;
}

export interface PortalRenderOptions {
  identity: PortalIdentity;
  profile: PartnerProfile | null;
  lastActiveAt: string | null; // sessions.last_active_at (previous request)
  lastActiveCountry: string | null; // null for MVP — column doesn't exist yet
  promptReaffirmation: boolean;
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
    --serif:      Georgia, "Times New Roman", "DejaVu Serif", serif;
    --sans:       -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    --mono:       "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--paper); color: var(--ink);
    font-family: var(--sans); font-size: 16px; line-height: 1.55; }
  a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
  a:hover { border-bottom-color: var(--accent); }
  main { max-width: 44rem; margin: 4rem auto; padding: 0 1.75rem; }

  .topbar {
    border-bottom: 1px solid var(--hairline);
    padding: 18px 0;
    background: var(--paper);
  }
  .topbar-inner { display: flex; align-items: baseline; justify-content: space-between;
    max-width: 44rem; margin: 0 auto; padding: 0 1.75rem; }
  .brand { font-family: var(--serif); font-size: 20px; font-weight: 700; color: var(--ink); }
  .signout {
    font-size: 13px;
    color: var(--muted);
  }
  .signout:hover { color: var(--ink); border-bottom-color: var(--ink); }

  .identity {
    margin-top: 2rem;
    padding: 1.5rem 1.75rem;
    border: 1px solid var(--hairline);
    background: var(--cream);
  }
  .identity-line { font-family: var(--serif); font-size: 1.1rem; color: var(--ink); margin: 0; }
  .identity-firm { font-family: var(--sans); font-size: 0.95rem; color: var(--ink-soft);
    margin: 0.4rem 0 0 0; }
  .identity-meta { font-family: var(--mono); font-size: 0.78rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.08em; margin: 1rem 0 0 0; }
  .identity-mismatch { font-size: 0.82rem; color: var(--muted); margin-top: 0.5rem; }

  .confirm-block {
    margin-top: 2rem;
    padding: 1.75rem;
    border: 1px solid var(--hairline);
    background: var(--paper);
  }
  .confirm-eyebrow { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0 0 0.5rem 0; }
  .confirm-h2 { font-family: var(--serif); font-size: 1.1rem; font-weight: 600;
    color: var(--ink); margin: 0 0 0.5rem 0; }
  .confirm-lede { color: var(--ink-soft); font-size: 0.92rem; margin: 0 0 1.25rem 0; }
  label { display: block; font-size: 0.85rem; color: var(--ink-soft); margin: 0.75rem 0 0.25rem 0; }
  input[type="text"] {
    width: 100%;
    padding: 0.55rem 0.65rem;
    font: inherit;
    border: 1px solid #b7c2ca;
    border-radius: 3px;
    background: var(--paper);
  }
  .confirm-row { display: flex; gap: 0.6rem; align-items: center; margin-top: 1rem; }
  .confirm-btn {
    padding: 0.55rem 1.1rem;
    font: inherit;
    font-size: 0.9rem;
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 3px;
    cursor: pointer;
  }
  .confirm-btn:hover { background: var(--navy); }
  .confirm-skip { color: var(--muted); font-size: 0.85rem; }

  .last-confirmed {
    margin-top: 2rem;
    font-size: 0.82rem;
    color: var(--muted);
  }

  .ctas {
    margin-top: 2.5rem;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }
  .cta {
    padding: 1.1rem 1.25rem;
    border: 1px solid var(--hairline);
    background: var(--paper);
    text-align: left;
    font-family: var(--serif);
  }
  .cta:hover { border-color: var(--accent); }
  .cta.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  .cta.primary:hover { background: var(--navy); border-color: var(--navy); }
  .cta-name { font-size: 1.05rem; font-weight: 600; display: block; }
  .cta-sub { font-family: var(--sans); font-size: 0.82rem; color: var(--muted); margin-top: 0.25rem; display: block; }
  .cta.primary .cta-sub { color: #d8e3ec; }
  .cta.disabled { opacity: 0.55; cursor: not-allowed; }

  @media (max-width: 560px) {
    .ctas { grid-template-columns: 1fr; }
  }
`;

export function renderPortal(opts: PortalRenderOptions): string {
  const { identity, profile, lastActiveAt, lastActiveCountry, promptReaffirmation } = opts;
  const firmSlug = profile?.firm_slug ?? null;
  const firmName = profile?.firm_name ?? "Setting up your account";

  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Portal · CJI</title>
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

  <section class="identity">
    <p class="identity-line">Signed in as <strong>${escapeHtml(identity.email)}</strong></p>
    <p class="identity-firm">${escapeHtml(firmName)}</p>
    ${renderLastSignIn(lastActiveAt, lastActiveCountry)}
    <p class="identity-mismatch">
      Not you? <a href="https://login.cjipro.com/logout">Sign out</a> and sign back in.
    </p>
  </section>

  ${promptReaffirmation
    ? renderConfirmBlock(profile)
    : renderLastConfirmedLine(profile?.last_confirmed_at ?? null)}

  <div class="ctas">
    ${firmSlug
      ? `<a class="cta primary" href="/sonar/${escapeAttr(firmSlug)}/">
           <span class="cta-name">Today's briefing</span>
           <span class="cta-sub">CJI Sonar — ${escapeHtml(firmName)}</span>
         </a>`
      : `<span class="cta primary disabled" title="Briefing available once your firm is provisioned">
           <span class="cta-name">Today's briefing</span>
           <span class="cta-sub">Available once your account is set up</span>
         </span>`}
    <a class="cta" href="/reckoner">
      <span class="cta-name">Open Reckoner</span>
      <span class="cta-sub">Industry intelligence — cohort patterns</span>
    </a>
  </div>

</main>
</body>
</html>`;
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

// ── Handler façade ───────────────────────────────────────────────
//
// The route handlers below are pure-data — they take a session
// identity (sub + email already extracted by index.ts auth gate) and
// the D1 binding, and return either a Response or an opaque "not-
// authed" sentinel that index.ts handles by redirecting to login.

export interface PortalEnv {
  AUDIT_DB: D1Database;
}

export async function handleGetPortal(
  identity: PortalIdentity,
  env: PortalEnv,
  lastActiveAt: string | null,
  now: Date = new Date(),
): Promise<Response> {
  const profile = await getProfile(env.AUDIT_DB, identity.sub);
  const promptReaffirmation = needsReaffirmation(profile, now);
  const html = renderPortal({
    identity,
    profile,
    lastActiveAt,
    lastActiveCountry: null,
    promptReaffirmation,
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
    // Profile row missing — shouldn't happen in production (ensureProfile
    // fires at /callback), but be defensive: redirect back to portal so
    // the user isn't stuck.
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

// Re-exported for the index.ts wiring path: it needs to look up
// session email from sub (already in app_cjipro for the auth gate)
// and read sessions.last_active_at to display on the portal.
export { lookupSessionEmail };

// Workers' Response.redirect requires an absolute URL. We don't have
// the request URL available in handlePostConfirm without threading it,
// so build a 302 with a relative Location header — which IS legal.
function redirectToPortal(): Response {
  return new Response(null, {
    status: 302,
    headers: { location: "/portal" },
  });
}
