// MIL-161 (initial) + MIL-162 (back-affordance + AuthKit endpoint fix)
// — sign-out page renders.
//
// Two pages:
//   1. GET /logout (signed-in)  → confirm form, POSTs back to /logout
//      with CSRF token + Sign-out button. "← Back" returns to /portal.
//   2. POST /logout result      → "You're signed out" confirmation,
//      with Sign-in-again CTA + "← Back to cjipro.com" escape. The
//      outcome of the lifecycle is shown as a compact status line so a
//      partner who has just demoed on a shared machine can SEE that
//      revocation happened, not infer it.
//
// CSP-clean: server-rendered, no inline JS, no event handlers.
// Back affordances are real anchor links (not history.back()) because
// the strict CSP forbids inline JS, and because /logout/* is reached
// via 302 chains where browser-history "back" would re-fire the flow.

import { FONTS_BLOCK } from "../../fonts_block/src/fonts_block.generated";
import type { LogoutOutcome } from "./logout";

const CSS = `
  :root {
    --ink: #0A1E2A; --ink-soft: #2C3E4D; --muted: #6B7A85;
    --hairline: #D8DFE5; --paper: #FFFFFF; --cream: #FAFAF7;
    --navy: #00273D; --accent: #003A5C;
    --serif: "Source Serif 4", Georgia, serif;
    --sans: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, sans-serif;
    --mono: "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--paper); color: var(--ink);
    font-family: var(--sans); font-size: 16px; line-height: 1.55; }
  main { max-width: 28rem; margin: 5rem auto; padding: 0 1.5rem; }
  h1 { font-family: var(--serif); font-weight: 600; font-size: 1.5rem;
    margin: 0 0 0.7rem 0; line-height: 1.3; }
  p { margin: 0.6rem 0; color: var(--ink-soft); }
  a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
  a:hover { border-bottom-color: var(--accent); }

  .actions { margin-top: 1.5rem; display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .btn-primary, .btn-secondary {
    display: inline-block; padding: 0.6rem 1.1rem; font: inherit;
    font-family: var(--sans); font-size: 0.9rem; border-radius: 3px;
    border: 1px solid var(--accent); cursor: pointer; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { background: var(--navy); border-color: var(--navy); }
  .btn-secondary { background: var(--paper); color: var(--accent); text-decoration: none; }
  .btn-secondary:hover { background: var(--accent); color: #fff; border-bottom: 1px solid var(--accent); }

  .status { margin-top: 1.5rem; padding: 0.85rem 1rem;
    background: var(--cream); border: 1px solid var(--hairline); border-radius: 3px;
    font-family: var(--mono); font-size: 0.78rem; color: var(--ink-soft); line-height: 1.6; }
  .status-key { display: block; font-size: 0.68rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.4rem; }
  .status-row { display: block; }
  .status-row strong { color: var(--ink); font-weight: 600; }
  .status-ok { color: #1d6f3f; }
  .status-skip { color: var(--muted); }
  .status-error { color: #a3320b; }

  footer.foot { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--hairline);
    font-family: var(--mono); font-size: 0.7rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.1em; }

  /* MIL-162 — page-level back affordance. Anchored top-left of <main>,
     above the heading, so it reads as "escape this flow" rather than
     "primary action". Underline-on-hover for affordance, never the
     default state. */
  .back-link { display: inline-block; margin-bottom: 1.4rem;
    font-family: var(--sans); font-size: 0.85rem; color: var(--muted);
    text-decoration: none; border-bottom: 1px solid transparent; }
  .back-link:hover, .back-link:focus-visible {
    color: var(--accent); border-bottom-color: var(--accent); }
  .back-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
`;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// GET /logout (cookie present) — shows a confirm form. The form POSTs
// back to /logout with the CSRF token. A "Cancel" link returns to
// /portal so a misclick doesn't strand the user on the sign-out page.
export function renderLogoutConfirm(
  csrfToken: string,
  cancelHref: string,
): string {
  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Sign out · CJI</title>
${FONTS_BLOCK}
<style>${CSS}</style>
</head>
<body>
<main>
<a class="back-link" href="${escapeHtml(cancelHref)}">&larr; Back</a>
<h1>Sign out of CJI?</h1>
<p>This will end your current session, revoke the access token at WorkOS, and clear your sign-in cookie across <code>cjipro.com</code>.</p>
<p>If you're on a shared machine, sign out before you walk away.</p>
<form method="POST" action="/logout">
  <input type="hidden" name="csrf" value="${escapeHtml(csrfToken)}">
  <div class="actions">
    <button class="btn-primary" type="submit">Sign out</button>
    <a class="btn-secondary" href="${escapeHtml(cancelHref)}">Cancel</a>
  </div>
</form>
<footer class="foot">Single-page action · No third-party trackers</footer>
</main>
</body>
</html>`;
}

// GET /logout when there's no cookie (already signed out) OR after a
// successful POST. The outcome block is omitted in the no-cookie case.
export function renderLogoutDone(outcome: LogoutOutcome | null): string {
  const status = outcome ? renderStatus(outcome) : "";
  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Signed out · CJI</title>
${FONTS_BLOCK}
<style>${CSS}</style>
</head>
<body>
<main>
<a class="back-link" href="https://cjipro.com/">&larr; Back to cjipro.com</a>
<h1>You're signed out.</h1>
<p>Your session has been ended. Sign in again whenever you need to.</p>
${status}
<div class="actions">
  <a class="btn-primary" href="https://login.cjipro.com/">Sign in again</a>
  <a class="btn-secondary" href="https://cjipro.com/">Back to cjipro.com</a>
</div>
<footer class="foot">If you signed out on a shared machine, you can close the tab safely.</footer>
</main>
</body>
</html>`;
}

// CSRF mismatch / replayed-POST / missing-cookie-on-POST. Renders a
// 400 with a "try again" link rather than 302-ing to /logout, so the
// user gets a clear failure mode rather than a silent loop.
export function renderLogoutCsrfFailed(): string {
  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Sign-out failed · CJI</title>
${FONTS_BLOCK}
<style>${CSS}</style>
</head>
<body>
<main>
<a class="back-link" href="https://app.cjipro.com/portal">&larr; Back to portal</a>
<h1>Couldn't complete sign out.</h1>
<p>Your session may have changed in another tab, or this page expired before you confirmed.</p>
<div class="actions">
  <a class="btn-primary" href="/logout">Try again</a>
  <a class="btn-secondary" href="https://app.cjipro.com/portal">Back to portal</a>
</div>
</main>
</body>
</html>`;
}

function renderStatus(o: LogoutOutcome): string {
  return `<div class="status" aria-label="Sign-out details">
    <span class="status-key">Sign-out details</span>
    <span class="status-row"><strong>Cookie cleared:</strong> <span class="status-ok">yes</span></span>
    <span class="status-row"><strong>Sessions row:</strong> ${renderStatusValue(o.sessions_row_deleted)}</span>
    <span class="status-row"><strong>WorkOS session revoked:</strong> ${renderStatusValue(o.workos_session_revoked)}</span>
  </div>`;
}

function renderStatusValue(v: string): string {
  if (v === "deleted" || v === "revoked") {
    return `<span class="status-ok">${escapeHtml(v)}</span>`;
  }
  if (v === "error") {
    return `<span class="status-error">error (logged)</span>`;
  }
  return `<span class="status-skip">${escapeHtml(v)}</span>`;
}
