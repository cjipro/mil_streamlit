// MIL-145 — share + forward affordances on Sonar briefings.
//
// Injected into the Sonar briefing HTML by sonarHandler in router.ts
// before </body>. Two affordances:
//
//   1. "Share with team" — a <details><summary> expand-to-reveal block
//      containing a copyable link + an "Add colleague by email" form.
//      Form posts to /api/share-invite (POST) which creates a
//      pending_signups row tagged with this briefing's firm context.
//      Standard form submission (no inline JS) → CSP-friendly.
//
//   2. "Forward by email" — plain mailto: link with a sensible subject
//      and body. Recipient is filled manually in the user's mail client.
//      Body includes the briefing URL + a /request-access link so the
//      forwarded colleague has a clear next step.
//
// CSS is scoped via .cji-share-* prefixes so it can't collide with the
// briefing's own classes. Visible-but-unobtrusive (top divider rule,
// muted background, tucks below the briefing chrome).

const REQUEST_ACCESS_URL = "https://login.cjipro.com/request-access";

interface ShareAffordanceOpts {
  firmSlug: string;
  firmDisplay: string;     // e.g. "Barclays" — already-escaped or untrusted: caller decides
  briefingUrl: string;     // absolute URL the recipient lands on
  briefingDateLabel: string; // human-readable, e.g. "27 Apr 2026" or "today"
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

function buildMailto(opts: ShareAffordanceOpts): string {
  // Subject is locked-form per MIL-49 PDB pattern — predictable bytes for
  // any future inbox-rule routing on the partner side.
  const subject = `CJI Sonar briefing — ${opts.firmDisplay} — ${opts.briefingDateLabel}`;
  const lede =
    `Today's CJI Sonar briefing on ${opts.firmDisplay}. ` +
    `Open-source signal: app-store reviews, DownDetector, public commentary.`;
  const lines = [
    `${lede}`,
    "",
    `Briefing: ${opts.briefingUrl}`,
    "",
    `Don't have access yet? Request at ${REQUEST_ACCESS_URL}`,
    "",
    "— shared via CJI Sonar",
  ];
  const body = lines.join("\n");
  return (
    "mailto:?subject=" +
    encodeURIComponent(subject) +
    "&body=" +
    encodeURIComponent(body)
  );
}

export function renderShareAffordance(opts: ShareAffordanceOpts): string {
  const safeFirm = escapeHtml(opts.firmDisplay);
  const safeUrl = escapeAttr(opts.briefingUrl);
  const safeSlug = escapeAttr(opts.firmSlug);
  const mailto = escapeAttr(buildMailto(opts));

  return `
<style>
  .cji-share { max-width: 60rem; margin: 2.5rem auto 3.5rem; padding: 1.5rem 1.75rem;
    border-top: 1px solid rgba(255,255,255,0.12); color: #E8F4FA;
    font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 14px; line-height: 1.55; }
  .cji-share-header { font-family: "DM Mono", monospace; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.1em; color: #7AACBF;
    margin: 0 0 1rem 0; }
  .cji-share-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: stretch; }
  .cji-share details, .cji-share .cji-mailto-card { flex: 1 1 24rem;
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 4px; padding: 0; }
  .cji-share summary, .cji-share .cji-mailto-summary {
    list-style: none; cursor: pointer;
    padding: 0.85rem 1.1rem; font-weight: 600; font-size: 14px;
    color: #E8F4FA; border-radius: 4px; user-select: none;
    display: flex; align-items: center; gap: 0.6rem; }
  .cji-share summary::-webkit-details-marker { display: none; }
  .cji-share summary:hover, .cji-share .cji-mailto-summary:hover {
    background: rgba(255,255,255,0.06); }
  .cji-share details[open] summary { border-bottom: 1px solid rgba(255,255,255,0.12); }
  .cji-share-icon {
    width: 16px; height: 16px; flex-shrink: 0; opacity: 0.85; }
  .cji-share-body { padding: 1rem 1.1rem 1.25rem; }
  .cji-share-label { font-family: "DM Mono", monospace; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.1em; color: #7AACBF;
    margin: 0 0 0.4rem 0; }
  .cji-share-link { width: 100%; padding: 0.55rem 0.75rem; font: inherit;
    font-size: 13px; color: #E8F4FA; background: rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.18); border-radius: 3px;
    box-sizing: border-box; user-select: all; }
  .cji-share-link:focus-visible { outline: 2px solid #00AEEF; outline-offset: 0;
    border-color: #00AEEF; }
  .cji-share-form { margin-top: 1.1rem; padding-top: 1rem;
    border-top: 1px dashed rgba(255,255,255,0.12); }
  .cji-share-form input[type="email"] { width: 100%; padding: 0.55rem 0.75rem;
    font: inherit; font-size: 13px; color: #E8F4FA; background: rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.18); border-radius: 3px;
    box-sizing: border-box; }
  .cji-share-form input[type="email"]:focus-visible { outline: 2px solid #00AEEF;
    outline-offset: 0; border-color: #00AEEF; }
  .cji-share-form button { margin-top: 0.65rem; padding: 0.55rem 1rem; font: inherit;
    font-size: 13px; font-weight: 600; cursor: pointer;
    background: #003A5C; color: #fff; border: 1px solid #00AEEF; border-radius: 3px; }
  .cji-share-form button:hover { background: #00273D; }
  .cji-share-form button:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
  .cji-share-help { margin: 0.5rem 0 0 0; color: #7AACBF; font-size: 12px; }
  .cji-mailto-summary { color: #E8F4FA; text-decoration: none; }
  .cji-mailto-summary:hover { color: #fff; }
  /* Confirmation banner — sonarHandler injects this above the briefing
     when ?invite_sent=<email> is in the URL. Same colour palette. */
  .cji-share-confirm {
    max-width: 60rem; margin: 1rem auto 0;
    padding: 0.85rem 1.25rem;
    background: rgba(0,175,160,0.10); color: #B8E0DA;
    border: 1px solid rgba(0,175,160,0.5); border-radius: 4px;
    font-family: "Plus Jakarta Sans", -apple-system, sans-serif; font-size: 14px; }
</style>

<section class="cji-share" aria-label="Share this briefing">
  <p class="cji-share-header">Share this ${safeFirm} briefing</p>
  <div class="cji-share-row">

    <details>
      <summary>
        <svg class="cji-share-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="18" cy="5" r="3"></circle>
          <circle cx="6" cy="12" r="3"></circle>
          <circle cx="18" cy="19" r="3"></circle>
          <line x1="8.6" y1="13.5" x2="15.4" y2="17.5"></line>
          <line x1="15.4" y1="6.5" x2="8.6" y2="10.5"></line>
        </svg>
        Share with team
      </summary>
      <div class="cji-share-body">
        <p class="cji-share-label">Briefing link (auth-gated)</p>
        <input type="text" class="cji-share-link" readonly value="${safeUrl}" onfocus="this.select()" aria-label="Briefing URL — select all to copy">
        <p class="cji-share-help">Recipients without access will land on the request-access form. Firm context is inferred from their email domain.</p>

        <form class="cji-share-form" method="post" action="/api/share-invite">
          <input type="hidden" name="source_firm_slug" value="${safeSlug}">
          <p class="cji-share-label">Or add a colleague by email</p>
          <input type="email" name="recipient_email" required placeholder="colleague@${safeSlug}.com" autocomplete="email" inputmode="email" spellcheck="false">
          <button type="submit">Send invite to admin queue</button>
          <p class="cji-share-help">Goes to the CJI access queue, not directly to your colleague. We review every request.</p>
        </form>
      </div>
    </details>

    <a class="cji-mailto-card cji-mailto-summary" href="${mailto}">
      <svg class="cji-share-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 4h16c1.1 0 2 0.9 2 2v12c0 1.1-0.9 2-2 2H4c-1.1 0-2-0.9-2-2V6c0-1.1 0.9-2 2-2z"></path>
        <polyline points="22,6 12,13 2,6"></polyline>
      </svg>
      Forward by email
    </a>

  </div>
</section>
`.trim();
}

// Tiny banner the sonarHandler can show when ?invite_sent=<email> is in
// the URL after a successful POST to /api/share-invite redirects back.
export function renderInviteSentBanner(recipientEmail: string): string {
  const safe = escapeHtml(recipientEmail);
  return `<div class="cji-share-confirm" role="status">Invite for <strong>${safe}</strong> added to the CJI access queue. We'll review it shortly.</div>`;
}
