// MIL-66b — GET + POST handlers for /request-access.
//
// GET renders a minimal HTML form. POST validates the email,
// rate-limits per IP, writes to pending_signups, and renders a
// thank-you page. No JSON API for this route — it's a one-shot
// form-driven flow for end users.

import { sha256Hex } from "../../audit/src/hash";
import {
  isPlausibleEmail,
  submitRequest,
  type SubmitOutcome,
} from "../../approvals/src/signups";
import {
  checkAndIncrement,
  DEFAULT_RATE_LIMIT,
} from "../../approvals/src/rate_limit";
import {
  FONTS_BLOCK,
  FONT_STACK_SANS,
  FONT_STACK_SERIF,
} from "../../fonts_block/src/fonts_block.generated";

// MIL-147 — accept ?email=foo@bar.com URL param to pre-fill the email
// field. This closes the forwarded-recipient loop (a partner shares a
// link, the recipient lands here with their email already in the form).
// Validation guards against XSS via the existing escapeHtml call AND
// against arbitrary text — invalid values fall through to a blank field.
//
// Hua Li enumeration guard: do NOT pre-fill ANY firm-related field
// from URL. The submit-time domain inference (admin dashboard) is
// fine — leaking a corporate-email-implies-firm hint at form-render
// time is not.
export function readEmailParam(url: URL): string | undefined {
  const raw = url.searchParams.get("email");
  if (!raw) return undefined;
  const trimmed = raw.trim();
  if (trimmed.length === 0 || trimmed.length > 254) return undefined;
  if (!isPlausibleEmail(trimmed)) return undefined;
  return trimmed;
}

// MIL-139 — visible focus rings (WCAG 2.2 AA SC 2.4.7) and explicit
// :focus-visible style on inputs/buttons/links. No outline:none reset
// anywhere; keyboard traversal must always show where the focus is.
// MIL-158 — body/h1 stacks switched to Inter / Source Serif 4. Same
// stacks Workers' other surfaces use; loaded via FONTS_BLOCK.
const PAGE_STYLES = `
  :root {
    --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7; --accent:#003A5C; --error:#b00020;
    --serif: ${FONT_STACK_SERIF};
    --sans: ${FONT_STACK_SANS};
  }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font: 16px/1.55 var(--sans); }
  main { max-width:32rem; margin:6rem auto; padding:2rem; }
  h1 { font-family: var(--serif); font-weight:600; font-size:1.4rem; margin:0 0 0.75rem; }
  p { margin:0.5rem 0; color:var(--muted); }
  label { display:block; margin:1rem 0 0.25rem; color:var(--ink); font-size:0.92rem; }
  input, textarea { width:100%; padding:0.5rem 0.65rem; font:inherit;
    border:1px solid #ccd5dc; border-radius:3px; background:#fff; box-sizing:border-box; }
  input:focus-visible, textarea:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 0; border-color: var(--accent);
  }
  input[aria-invalid="true"] { border-color: var(--error); }
  textarea { min-height:5rem; resize:vertical; }
  button { margin-top:1.25rem; padding:0.6rem 1.2rem; font:inherit; cursor:pointer;
    background:var(--accent); color:#fff; border:0; border-radius:3px; }
  button:hover { background:#002a44; }
  button:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
  a { color:var(--accent); }
  a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }
  .err { color:var(--error); font-size:0.88rem; margin:0.35rem 0 0; }
  .help { color:var(--muted); font-size:0.82rem; margin:0.3rem 0 0; }
  .ok { color:#1d6e3a; font-size:0.95rem; }
  .meta { font-size:0.86rem; color:var(--muted); border-left:3px solid var(--accent);
    padding:0.35rem 0 0.35rem 0.75rem; margin:1.25rem 0 0; }
  /* WCAG 2.2 AA — utility .visually-hidden for sr-only text without display:none */
  .visually-hidden {
    position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden;
    clip:rect(0,0,0,0); white-space:nowrap; border:0;
  }
`;

export function renderRequestForm(opts: { error?: string; email?: string } = {}): Response {
  // MIL-139 — error message is in a role="alert" live region so screen
  // readers announce it on render; aria-describedby threads it to the
  // input it concerns. aria-invalid lights up only when an error is
  // actually present so unfilled forms aren't styled as broken on load.
  const hasError = Boolean(opts.error);
  const errHtml = hasError
    ? `<p class="err" id="email-err" role="alert">${escapeHtml(opts.error!)}</p>`
    : "";
  const emailDescribedBy = hasError ? "email-help email-err" : "email-help";
  const emailAriaInvalid = hasError ? ' aria-invalid="true"' : "";
  const emailVal = opts.email ? escapeHtml(opts.email) : "";
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Request access · CJI</title>
${FONTS_BLOCK}
<style>${PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Request access</h1>
<p>CJI is in private alpha. Enter your work email and a short note
about why you'd like access — we'll review and get back to you.</p>
<p class="meta">We review every request personally. Corporate email preferred but not required.</p>
<form method="post" action="/request-access" novalidate>
  <label for="email">Work email</label>
  <input id="email" name="email" type="email" required autocomplete="email"
         inputmode="email" spellcheck="false"
         aria-describedby="${emailDescribedBy}"${emailAriaInvalid}
         value="${emailVal}">
  <p class="help" id="email-help">We'll only use this to confirm your access request.</p>
  <label for="note">Note <span class="help" style="display:inline">(optional)</span></label>
  <textarea id="note" name="note" maxlength="500"
            aria-describedby="note-help"
            placeholder="Team, what you'd like to see, etc."></textarea>
  <p class="help" id="note-help">Up to 500 characters. Plain text — no formatting.</p>
  ${errHtml}
  <button type="submit">Request access</button>
</form>
<p style="margin-top:2rem;"><a href="/">← Back to sign in</a></p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: hasError ? 400 : 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function renderThanks(outcome: SubmitOutcome): Response {
  let body: string;
  if (outcome.kind === "created") {
    body = `<h1>Thanks — we'll be in touch</h1>
<p>Your request is in the queue. We'll email you once it's reviewed.</p>`;
  } else if (outcome.kind === "already-pending") {
    body = `<h1>Already in the queue</h1>
<p>Your earlier request is still pending review. No action needed.</p>`;
  } else {
    body = `<h1>You're already approved</h1>
<p>Head to <a href="/">sign in</a>.</p>`;
  }
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Request received · CJI</title>
${FONTS_BLOCK}
<style>${PAGE_STYLES}</style>
</head>
<body>
<main>
${body}
<p style="margin-top:2rem;"><a href="/">← Back to sign in</a></p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function rateLimited(): Response {
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Slow down · CJI</title>
${FONTS_BLOCK}
<style>${PAGE_STYLES}</style></head>
<body><main>
<h1>Slow down</h1>
<p>You've submitted a few requests recently. Wait an hour and try again,
or email <a href="mailto:hello@cjipro.com">hello@cjipro.com</a> directly.</p>
</main></body></html>`;
  return new Response(html, {
    status: 429,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "retry-after": "3600",
    },
  });
}

export async function handleRequestAccessPost(
  request: Request,
  db: D1Database | undefined,
  dailySalt: string | null,
): Promise<Response> {
  if (!db) {
    return renderRequestForm({
      error: "Request intake is not configured. Email hello@cjipro.com instead.",
    });
  }

  const formData = await request.formData();
  const rawEmail = (formData.get("email") ?? "").toString();
  const note = (formData.get("note") ?? "").toString();

  const ip = request.headers.get("cf-connecting-ip");
  const ua = request.headers.get("user-agent");
  const ipHash = ip && dailySalt ? await sha256Hex(ip + dailySalt) : undefined;
  const uaHash = ua ? await sha256Hex(ua) : undefined;

  // Rate-limit BEFORE the D1 insert to avoid a flood of garbage rows.
  const allowed = await checkAndIncrement(
    db,
    ipHash,
    new Date(),
    DEFAULT_RATE_LIMIT,
  );
  if (!allowed) return rateLimited();

  const outcome = await submitRequest(db, {
    email: rawEmail,
    note: note.slice(0, 500) || undefined,
    ipHash,
    uaHash,
  });

  if (outcome.kind === "invalid-email") {
    return renderRequestForm({
      error: "That doesn't look like a valid email.",
      email: rawEmail,
    });
  }
  return renderThanks(outcome);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
