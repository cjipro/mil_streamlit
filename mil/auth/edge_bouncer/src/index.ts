// MIL-61 — Edge Bouncer entrypoint
//
// Three responsibilities, in order:
//   1. Public allowlist — landing, privacy, security.txt, robots,
//      sitemap, .nojekyll → always pass through.
//   2. Session check — extract + verify __Secure-cjipro-session
//      JWT against WorkOS JWKS.
//   3. On miss — 302 to login.cjipro.com with return_to.
//
// ENFORCE=false: decide, log, always pass through. Default until
// MIL-63 ships the magic-link flow that actually sets the cookie.
//
// The Worker does NOT itself serve any content — it either passes
// the request to origin via `fetch(request)` or returns a 302.

import { isPublic, parsePatterns, type Matcher } from "./whitelist";
import {
  extractCookie,
  verifySession,
  type SessionCheck,
  type SessionConfig,
} from "./session";
import { logAuthEvent } from "../../audit/src/audit";
import type { AuthEventInput, AuthEventType } from "../../audit/src/types";
import { isApproved } from "../../approvals/src/approvals";
import { lookupSessionEmail, recordActivity } from "../../approvals/src/sessions";
import { isPending } from "../../approvals/src/signups";
import {
  FONTS_BLOCK,
  FONT_STACK_SANS,
  FONT_STACK_SERIF,
} from "../../fonts_block/src/fonts_block.generated";

export interface Env {
  ENFORCE: string;
  SESSION_COOKIE_NAME: string;
  JWKS_URL: string;
  EXPECTED_AUD: string;
  EXPECTED_ISS: string;
  LOGIN_URL: string;
  RETURN_TO_PARAM: string;
  JWKS_CACHE_TTL_SECONDS: string;
  PUBLIC_PATHS: string;
  // MIL-65 — audit log binding. Optional: the Worker runs without it
  // (degraded to console.log only) so a missing D1 doesn't take the
  // auth path down. Populate via wrangler.toml [[d1_databases]].
  AUDIT_DB?: D1Database;
}

type Decision =
  | { action: "pass"; reason: "public" | "valid-session"; sub?: string }
  | { action: "redirect"; reason: "missing" | "invalid"; detail?: string }
  | {
      action: "deny";
      // MIL-153 — three deny variants:
      //   "not-approved"  : legacy fallback when D1 unavailable or no sub
      //   "in-queue"      : pending_signups row exists
      //   "not-on-allowlist": authenticated but no row anywhere
      reason: "not-approved" | "in-queue" | "not-on-allowlist";
      sub?: string;
      email?: string;
      requestedAt?: string;
    };

// Pattern list is parsed per-request rather than cached in module
// scope because wrangler vars can hot-reload.
function publicMatchers(env: Env): Matcher[] {
  return parsePatterns(env.PUBLIC_PATHS);
}

function sessionConfig(env: Env): SessionConfig {
  return {
    jwksUrl: env.JWKS_URL,
    expectedIss: env.EXPECTED_ISS,
    expectedAud: env.EXPECTED_AUD,
    jwksCacheTtlSeconds: parseInt(env.JWKS_CACHE_TTL_SECONDS, 10) || 3600,
  };
}

function buildRedirect(request: Request, env: Env): Response {
  const url = new URL(request.url);
  // Encode the FULL origin + path so the magic-link callback can
  // redirect cross-host. Path-only return_to was a bug pre-2026-04-26
  // ENFORCE flip — sign-in completed on login.cjipro.com would resolve
  // /briefing/ against the login host (404) instead of cjipro.com.
  const returnTo = url.origin + url.pathname + url.search;
  const login = new URL(env.LOGIN_URL);
  login.searchParams.set(env.RETURN_TO_PARAM, returnTo);
  return Response.redirect(login.toString(), 302);
}

// MIL-87 + MIL-143 — legacy /briefing-v4 paths permanently moved.
// Authenticated home for the real briefing migrated to
// app.cjipro.com/sonar/{slug}/ (see MIL-86); the public-facing
// replacement is the sanitised sample at /insights/sample-briefing/.
//
// MIL-143 reframe (2026-04-26): warm partners with a session cookie
// route to app.cjipro.com/sonar/barclays/ (the real briefing); only
// cold visitors with no cookie route to the public sample. This
// matches the panel verdict that warm partners with a magic-link
// shouldn't be bait-and-switched to a sample. Cookie presence — not
// validity — is the trigger; the destination bouncer handles auth.
// An expired cookie is treated as warm: those users were partners
// before and still know what they're looking for; the destination
// will silently re-auth them.
//
// 302 (not 301) because the destination is per-request (cookie state
// can change). 301 caches per-URL, which would lock a browser into
// whichever destination it saw first regardless of later auth state.
// Cache-Control: no-store reinforces this for proxies and Cloudflare
// edge caches that might otherwise honour 302 with a default TTL.
//
// Fires before decide() so ENFORCE state is irrelevant to routing.
const _LEGACY_BRIEFING_TARGET_COLD = "https://cjipro.com/insights/sample-briefing/";
const _LEGACY_BRIEFING_TARGET_WARM = "https://app.cjipro.com/sonar/barclays/";

function legacyPathRedirect(request: Request, env: Env): Response | null {
  const url = new URL(request.url);
  if (url.pathname !== "/briefing-v4" && !url.pathname.startsWith("/briefing-v4/")) {
    return null;
  }
  const sessionCookie = extractCookie(
    request.headers.get("cookie"),
    env.SESSION_COOKIE_NAME,
  );
  const target = sessionCookie
    ? _LEGACY_BRIEFING_TARGET_WARM
    : _LEGACY_BRIEFING_TARGET_COLD;
  return new Response(null, {
    status: 302,
    headers: {
      location: target,
      "cache-control": "no-store",
    },
  });
}

async function decide(request: Request, env: Env): Promise<Decision> {
  const url = new URL(request.url);
  if (isPublic(url.pathname, publicMatchers(env))) {
    return { action: "pass", reason: "public" };
  }
  const cookie = extractCookie(
    request.headers.get("cookie"),
    env.SESSION_COOKIE_NAME,
  );
  const result: SessionCheck = await verifySession(cookie, sessionConfig(env));
  if (result.kind === "missing") {
    return { action: "redirect", reason: "missing" };
  }
  if (result.kind === "invalid") {
    return { action: "redirect", reason: "invalid", detail: result.reason };
  }

  // Valid JWT. MIL-66a/c — check the user's email against the
  // approved_users allowlist. WorkOS access tokens carry sub but no
  // email; MIL-66c writes a sub→email row at /callback time so we
  // can look it up here. No AUDIT_DB or no session row → fail CLOSED.
  const sub = typeof result.payload.sub === "string" ? result.payload.sub : undefined;
  if (!env.AUDIT_DB || !sub) {
    return { action: "deny", reason: "not-approved", sub };
  }
  const email = await lookupSessionEmail(env.AUDIT_DB, sub);
  const approved = await isApproved(env.AUDIT_DB, email);
  if (approved) {
    return { action: "pass", reason: "valid-session", sub };
  }
  // MIL-153 — differentiate the deny: in-queue (has a pending row)
  // gets a "your request is being reviewed" page; not-on-allowlist
  // (no row anywhere) gets a "request access" CTA. Same audit
  // sub/email plumbing as before; lookupRequestedAt scopes the
  // requested_at lookup to a single column so we don't re-query
  // half the table.
  const pending = email ? await lookupPendingRow(env.AUDIT_DB, email) : null;
  if (pending) {
    return {
      action: "deny",
      reason: "in-queue",
      sub,
      email,
      requestedAt: pending.requested_at,
    };
  }
  return { action: "deny", reason: "not-on-allowlist", sub, email };
}

// MIL-153 — pending-row lookup with the requested_at column. Used
// by the in-queue render to show "Submitted: <date>". Returns null
// if no pending row exists.
async function lookupPendingRow(
  db: D1Database,
  email: string,
): Promise<{ requested_at: string } | null> {
  const canonical = email.trim().toLowerCase();
  if (!canonical) return null;
  const row = await db
    .prepare(
      "SELECT requested_at FROM pending_signups WHERE email = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
    )
    .bind(canonical)
    .first<{ requested_at: string }>();
  return row ?? null;
}

function auditEventType(decision: Decision): AuthEventType {
  if (decision.action === "pass" && decision.reason === "public") {
    return "bouncer.pass.public";
  }
  if (decision.action === "pass" && decision.reason === "valid-session") {
    return "bouncer.pass.session";
  }
  if (decision.action === "redirect" && decision.reason === "missing") {
    return "bouncer.redirect.missing";
  }
  if (decision.action === "deny") {
    // MIL-153 — differentiated states. Legacy not_approved kept as
    // the D1-unavailable / no-sub fallback, so historical audit
    // analysis stays linkable across the rename boundary.
    if (decision.reason === "in-queue") return "bouncer.deny.in_queue";
    if (decision.reason === "not-on-allowlist") return "bouncer.deny.not_on_allowlist";
    return "bouncer.deny.not_approved";
  }
  return "bouncer.redirect.invalid";
}

function buildAuditInput(
  request: Request,
  decision: Decision,
  enforce: boolean,
): AuthEventInput {
  const url = new URL(request.url);
  const cf = (request as Request & { cf?: IncomingRequestCfProperties }).cf;
  return {
    worker: "edge-bouncer",
    event_type: auditEventType(decision),
    method: request.method,
    host: url.host,
    path: url.pathname,
    enforce,
    session_sub: decision.action === "pass" || decision.action === "deny"
      ? decision.sub
      : undefined,
    ip: request.headers.get("cf-connecting-ip") ?? undefined,
    user_agent: request.headers.get("user-agent") ?? undefined,
    country: cf?.country ?? undefined,
    reason: decision.reason,
    detail: decision.action === "redirect" ? decision.detail : undefined,
  };
}

// Shared chrome — both deny variants + the legacy fallback render
// over the same minimal page shell. Inlined to avoid a build step.
// MIL-158 — body uses Inter, h1 uses Source Serif 4. FONTS_BLOCK is
// injected separately into each page's <head>.
const DENY_PAGE_STYLES = `
  :root { --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7; --accent:#003A5C;
    --serif: ${FONT_STACK_SERIF};
    --sans: ${FONT_STACK_SANS}; }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font: 16px/1.55 var(--sans); }
  main { max-width:32rem; margin:6rem auto; padding:2rem; }
  h1 { font-family: var(--serif); font-weight:600; font-size:1.4rem; margin:0 0 0.75rem; }
  p { margin:0.5rem 0; color:var(--muted); }
  a { color:var(--accent); }
  .cta { display:inline-block; margin-top:1rem; padding:0.6rem 1.1rem;
    background:var(--accent); color:#fff; border-radius:3px;
    text-decoration:none; }
  .cta:hover { filter:brightness(0.9); }
  .submitted { font-family:"SF Mono",Menlo,Consolas,monospace;
    font-size:0.78rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:0.08em; margin-top:1rem; }
`;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// MIL-153 — pending request acknowledged. 200 (not 403): the user
// is in a known queue state, this is a positive acknowledgment, not
// an error. Keeps the auth-pending page out of browser-error UX.
function renderInQueue(email: string | undefined, requestedAt: string | undefined): Response {
  const submitted = requestedAt
    ? `<p class="submitted">Submitted: ${escapeHtml(requestedAt.slice(0, 10))}</p>`
    : "";
  const who = email ? escapeHtml(email) : "your account";
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Request being reviewed · CJI</title>
${FONTS_BLOCK}
<style>${DENY_PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Your request is being reviewed</h1>
<p>We've received your access request from <strong>${who}</strong>.</p>
<p>We'll email you once it's approved.</p>
${submitted}
</main>
</body>
</html>`;
  return new Response(html, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

// MIL-153 — authenticated but never requested access. 403 with a
// real CTA to /request-access (carrying email pre-fill via MIL-147).
function renderNotOnAllowlist(email: string | undefined): Response {
  const who = email ? escapeHtml(email) : "your account";
  const cta = email
    ? `https://login.cjipro.com/request-access?email=${encodeURIComponent(email)}`
    : "https://login.cjipro.com/request-access";
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Access not yet provisioned · CJI</title>
${FONTS_BLOCK}
<style>${DENY_PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Access not yet provisioned</h1>
<p>You're signed in as <strong>${who}</strong>, but you don't have access to CJI yet.</p>
<a class="cta" href="${escapeHtml(cta)}">Request access →</a>
<p style="margin-top:1.5rem;">Or email
<a href="mailto:hello@cjipro.com">hello@cjipro.com</a>.</p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: 403,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

// Legacy fallback — fires only when D1 is unavailable, no sub, or
// (transitionally) any caller still passing reason="not-approved".
// MIL-154 (BACKLOG) removes this once MIL-153 has soaked clean.
function buildDenyResponse(): Response {
  const html = `<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Access pending · CJI</title>
${FONTS_BLOCK}
<style>${DENY_PAGE_STYLES}</style>
</head>
<body>
<main>
<h1>Access pending</h1>
<p>You're signed in, but this account isn't on the alpha access list yet.</p>
<p>Request access at
<a href="https://login.cjipro.com/request-access">login.cjipro.com/request-access</a>,
or email <a href="mailto:hello@cjipro.com">hello@cjipro.com</a>.</p>
</main>
</body>
</html>`;
  return new Response(html, {
    status: 403,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function logDecision(
  request: Request,
  decision: Decision,
  enforce: boolean,
): void {
  const url = new URL(request.url);
  const entry = {
    ts: new Date().toISOString(),
    enforce,
    method: request.method,
    host: url.host,
    path: url.pathname,
    action: decision.action,
    reason: decision.reason,
    detail: "detail" in decision ? decision.detail : undefined,
  };
  // Cloudflare Workers logs are picked up by observability=enabled
  // in wrangler.toml and surfaced via `wrangler tail` / Logpush.
  console.log(JSON.stringify(entry));
}

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<Response> {
    // MIL-87 + MIL-143 — legacy /briefing-v4 cutover, cookie-aware.
    // Returned BEFORE decide() so the redirect fires regardless of
    // ENFORCE state. Warm partners (cookie present) route to the real
    // briefing on app.cjipro.com; cold visitors get the public sample.
    const legacy = legacyPathRedirect(request, env);
    if (legacy) return legacy;

    const enforce = env.ENFORCE === "true";
    const decision = await decide(request, env);
    logDecision(request, decision, enforce);

    // MIL-65 — fire the audit write into the waitUntil pool so it
    // never gates the user response. A D1 failure is swallowed by
    // the .catch here and logged; auth still flows.
    if (env.AUDIT_DB) {
      const db = env.AUDIT_DB;
      ctx.waitUntil(
        logAuthEvent(db, buildAuditInput(request, decision, enforce)).catch(
          (err) => {
            console.log(
              JSON.stringify({
                ts: new Date().toISOString(),
                audit_error: err instanceof Error ? err.message : String(err),
              }),
            );
          },
        ),
      );
      // MIL-68 — bump last_active_at on session pass-throughs so the
      // admin dashboard can show "Last seen Xmin ago" per user. Only
      // on the pass.session branch — public-allowlist hits aren't
      // tied to a specific user.
      if (
        decision.action === "pass" &&
        decision.reason === "valid-session" &&
        decision.sub
      ) {
        const sub = decision.sub;
        ctx.waitUntil(
          recordActivity(db, sub).catch((err) => {
            console.log(
              JSON.stringify({
                ts: new Date().toISOString(),
                activity_write_error:
                  err instanceof Error ? err.message : String(err),
              }),
            );
          }),
        );
      }
    }

    // MIL-69 — log when Cloudflare WAF passed through a request
    // that had to solve a challenge (rate-limited but recovered).
    // Pre-challenge blocks never reach the Worker; this captures the
    // post-solve case for unified-timeline visibility.
    if (env.AUDIT_DB) {
      const challenged = request.headers.get("cf-challenge-status");
      if (challenged) {
        const db = env.AUDIT_DB;
        const url = new URL(request.url);
        const cf = (request as Request & { cf?: IncomingRequestCfProperties }).cf;
        ctx.waitUntil(
          logAuthEvent(db, {
            worker: "edge-bouncer",
            event_type: "bouncer.rate_limited",
            method: request.method,
            host: url.host,
            path: url.pathname,
            ip: request.headers.get("cf-connecting-ip") ?? undefined,
            user_agent: request.headers.get("user-agent") ?? undefined,
            country: cf?.country ?? undefined,
            reason: challenged,
          }).catch(() => {}),
        );
      }
    }

    if (decision.action === "redirect" && enforce) {
      return buildRedirect(request, env);
    }
    if (decision.action === "deny" && enforce) {
      // MIL-153 — route to the differentiated page based on reason.
      // not-approved (legacy) is the D1-unavailable / no-sub fallback.
      if (decision.reason === "in-queue") {
        return renderInQueue(decision.email, decision.requestedAt);
      }
      if (decision.reason === "not-on-allowlist") {
        return renderNotOnAllowlist(decision.email);
      }
      return buildDenyResponse();
    }
    // Pass through to origin for all other cases:
    //   - public allowlist match
    //   - valid session
    //   - enforce=false (shadow / monitor mode) — including deny cases:
    //     we log what we WOULD have done, but never block in shadow mode
    return fetch(request);
  },
};
