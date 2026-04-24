// MIL-66b — GET + POST handlers for /request-access.
//
// GET renders a minimal HTML form. POST validates the email,
// rate-limits per IP, writes to pending_signups, and renders a
// thank-you page. No JSON API for this route — it's a one-shot
// form-driven flow for end users.

import { sha256Hex } from "../../audit/src/hash";
import { submitRequest, type SubmitOutcome } from "../../approvals/src/signups";
import {
  checkAndIncrement,
  DEFAULT_RATE_LIMIT,
} from "../../approvals/src/rate_limit";

const PAGE_STYLES = `
  :root { --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7; --accent:#003A5C; }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font:16px/1.55 ui-serif,Georgia,serif; }
  main { max-width:32rem; margin:6rem auto; padding:2rem; }
  h1 { font-weight:600; font-size:1.4rem; margin:0 0 0.75rem; }
  p { margin:0.5rem 0; color:var(--muted); }
  label { display:block; margin:1rem 0 0.25rem; color:var(--ink); font-size:0.92rem; }
  input, textarea { width:100%; padding:0.5rem 0.65rem; font:inherit;
    border:1px solid #ccd5dc; border-radius:3px; background:#fff; box-sizing:border-box; }
  textarea { min-height:5rem; resize:vertical; }
  button { margin-top:1.25rem; padding:0.6rem 1.2rem; font:inherit; cursor:pointer;
    background:var(--accent); color:#fff; border:0; border-radius:3px; }
  button:hover { background:#002a44; }
  a { color:var(--accent); }
  .err { color:#b00020; font-size:0.88rem; margin:0.35rem 0 0; }
  .ok { color:#1d6e3a; font-size:0.95rem; }
`;

export function renderRequestForm(opts: { error?: string; email?: string } = {}): Response {
  const errHtml = opts.error
    ? `<p class="err">${escapeHtml(opts.error)}</p>`
    : "";
  const emailVal = opts.email ? escapeHtml(opts.email) : "";
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Request access · CJI Pro</title>
<style>${PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Request access</h1>
<p>CJI Pro is in private alpha. Enter your work email and a short note
about why you'd like access — we'll review and get back to you.</p>
<form method="post" action="/request-access">
  <label for="email">Work email</label>
  <input id="email" name="email" type="email" required autocomplete="email"
         value="${emailVal}">
  <label for="note">Note (optional)</label>
  <textarea id="note" name="note" maxlength="500"
            placeholder="Team, what you'd like to see, etc."></textarea>
  ${errHtml}
  <button type="submit">Request access</button>
</form>
<p style="margin-top:2rem;"><a href="/">← Back to sign in</a></p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: opts.error ? 400 : 200,
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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Request received · CJI Pro</title>
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
<html><head><meta charset="utf-8"><title>Slow down · CJI Pro</title>
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
