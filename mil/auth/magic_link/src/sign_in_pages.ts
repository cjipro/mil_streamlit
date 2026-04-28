// MIL-149 — HTML renderers for /sign-in/ flow
//
// Two pages: email entry, then code entry. Both use the same
// chrome as request_access.ts so the visual language stays
// consistent (Source Serif 4 + Inter via FONTS_BLOCK, focus rings,
// error live regions).

import {
  FONTS_BLOCK,
  FONT_STACK_SANS,
  FONT_STACK_SERIF,
} from "../../fonts_block/src/fonts_block.generated";

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
  input { width:100%; padding:0.5rem 0.65rem; font:inherit;
    border:1px solid #ccd5dc; border-radius:3px; background:#fff; box-sizing:border-box; }
  input:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 0; border-color: var(--accent);
  }
  input[aria-invalid="true"] { border-color: var(--error); }
  input.code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 1.25rem; letter-spacing: 0.4em; text-align: center; padding: 0.7rem; }
  button { margin-top:1.25rem; padding:0.6rem 1.2rem; font:inherit; cursor:pointer;
    background:var(--accent); color:#fff; border:0; border-radius:3px; }
  button:hover { background:#002a44; }
  button:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
  a { color:var(--accent); }
  a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }
  .err { color:var(--error); font-size:0.88rem; margin:0.35rem 0 0; }
  .help { color:var(--muted); font-size:0.82rem; margin:0.3rem 0 0; }
  .meta { font-size:0.86rem; color:var(--muted); border-left:3px solid var(--accent);
    padding:0.35rem 0 0.35rem 0.75rem; margin:1.25rem 0 0; }
  .row-actions { display:flex; gap:0.75rem; align-items:center; margin-top:1.5rem; }
  .visually-hidden {
    position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden;
    clip:rect(0,0,0,0); white-space:nowrap; border:0;
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

export interface EmailFormOpts {
  email?: string;
  error?: string;
  returnTo?: string;
}

export function renderSignInEmailForm(opts: EmailFormOpts = {}): Response {
  const hasError = Boolean(opts.error);
  const errHtml = hasError
    ? `<p class="err" id="email-err" role="alert">${escapeHtml(opts.error!)}</p>`
    : "";
  const emailDescribedBy = hasError ? "email-help email-err" : "email-help";
  const emailAriaInvalid = hasError ? ' aria-invalid="true"' : "";
  const emailVal = opts.email ? escapeHtml(opts.email) : "";
  const returnToHidden = opts.returnTo
    ? `<input type="hidden" name="return_to" value="${escapeHtml(opts.returnTo)}">`
    : "";
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Sign in · CJI</title>
${FONTS_BLOCK}
<style>${PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Sign in</h1>
<p>Enter your work email. We'll send you a one-time code.</p>
<form method="post" action="/sign-in/email" novalidate>
  <label for="email">Work email</label>
  <input id="email" name="email" type="email" required autocomplete="email"
         inputmode="email" spellcheck="false" autofocus
         aria-describedby="${emailDescribedBy}"${emailAriaInvalid}
         value="${emailVal}">
  <p class="help" id="email-help">Use the address your access was approved on.</p>
  ${errHtml}
  ${returnToHidden}
  <button type="submit">Send code</button>
</form>
<p style="margin-top:2rem;font-size:0.9rem;">No account yet? <a href="/request-access">Request access</a>.</p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: hasError ? 400 : 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export interface CodeFormOpts {
  email: string;
  state: string;
  error?: string;
}

export function renderSignInCodeForm(opts: CodeFormOpts): Response {
  const hasError = Boolean(opts.error);
  const errHtml = hasError
    ? `<p class="err" id="code-err" role="alert">${escapeHtml(opts.error!)}</p>`
    : "";
  const codeDescribedBy = hasError ? "code-help code-err" : "code-help";
  const codeAriaInvalid = hasError ? ' aria-invalid="true"' : "";
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Enter code · CJI</title>
${FONTS_BLOCK}
<style>${PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Check your email</h1>
<p>We sent a 6-digit code to <strong>${escapeHtml(opts.email)}</strong>.
   Codes expire after 10 minutes.</p>
<form method="post" action="/sign-in/code" novalidate>
  <label for="code">One-time code</label>
  <input id="code" name="code" type="text" required autofocus
         inputmode="numeric" autocomplete="one-time-code"
         pattern="[0-9]*" spellcheck="false" maxlength="10"
         class="code"
         aria-describedby="${codeDescribedBy}"${codeAriaInvalid}>
  <p class="help" id="code-help">Numbers only. Six digits.</p>
  ${errHtml}
  <input type="hidden" name="state" value="${escapeHtml(opts.state)}">
  <div class="row-actions">
    <button type="submit">Sign in</button>
    <a href="/sign-in/">Use a different email</a>
  </div>
</form>
</main>
</body>
</html>`;
  return new Response(html, {
    status: hasError ? 400 : 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

// Generic error page for state-token failures (expired, tampered).
// Different shape from the code-form error because the user has
// nothing to retry — the only path forward is to start over.
export function renderSignInExpired(): Response {
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Sign-in expired · CJI</title>
${FONTS_BLOCK}
<style>${PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Sign-in expired</h1>
<p>This sign-in attempt has expired. Codes are valid for 10 minutes.</p>
<p><a href="/sign-in/">Start again</a></p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: 400,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
