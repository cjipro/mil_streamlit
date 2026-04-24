// MIL-66b — /admin + /admin/api/* route handlers.
//
// All routes are gated by checkAdmin(). On a non-admin session we
// return 403 with an HTML or JSON body depending on the Accept
// header. The dashboard HTML is self-contained vanilla JS that
// fetches the JSON endpoints.

import type { AdminGateConfig, AdminCheck } from "./admin_gate";
import {
  approvePending,
  denyPending,
  listApproved,
  listByStatus,
  revokeApproval,
} from "../../approvals/src/signups";

const STYLES = `
  :root { --ink:#0A1E2A; --muted:#6B7A85; --paper:#FAFAF7; --accent:#003A5C; --line:#e0e4e7; }
  html,body { margin:0; padding:0; background:var(--paper); color:var(--ink);
    font:15px/1.5 ui-sans-serif,-apple-system,Segoe UI,system-ui,sans-serif; }
  main { max-width:64rem; margin:2.5rem auto; padding:0 1.5rem; }
  h1 { font:600 1.45rem/1.2 ui-serif,Georgia,serif; margin:0 0 1.25rem; }
  h2 { font:600 1.05rem/1.2 ui-sans-serif,-apple-system,Segoe UI,system-ui,sans-serif;
    margin:2rem 0 0.5rem; color:var(--ink); }
  p.sub { color:var(--muted); margin:0 0 1.5rem; font-size:0.88rem; }
  table { width:100%; border-collapse:collapse; font-size:0.89rem; }
  th, td { text-align:left; padding:0.55rem 0.6rem; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-weight:500; text-transform:uppercase; font-size:0.72rem; letter-spacing:0.04em; }
  td.actions { white-space:nowrap; }
  button { padding:0.28rem 0.65rem; font:inherit; font-size:0.82rem; cursor:pointer;
    background:#fff; color:var(--ink); border:1px solid #b7c2ca; border-radius:3px;
    margin-right:0.35rem; }
  button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  button.danger  { color:#b00020; border-color:#f0b4be; }
  button:hover { filter:brightness(0.96); }
  .empty { color:var(--muted); font-style:italic; padding:0.75rem 0; }
  .err   { color:#b00020; margin:0.5rem 0; }
  code { background:#fff; padding:0.08em 0.3em; border-radius:3px; font-size:0.86em; }
`;

export function renderDashboard(adminEmail: string): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Access admin · CJI Pro</title>
<style>${STYLES}</style>
</head>
<body>
<main>
<h1>Access admin</h1>
<p class="sub">Signed in as <code>${escapeHtml(adminEmail)}</code>.
 Review pending signup requests and manage the approved-user allowlist.</p>

<h2>Pending requests</h2>
<div id="pending"><p class="empty">Loading…</p></div>

<h2>Approved users</h2>
<div id="approved"><p class="empty">Loading…</p></div>

<script>
const $ = (id) => document.getElementById(id);

function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function load() {
  try {
    const r = await fetch("/admin/api/signups");
    if (!r.ok) throw new Error("fetch failed: " + r.status);
    const j = await r.json();
    renderPending(j.pending || []);
    renderApproved(j.approved || []);
  } catch (e) {
    $("pending").innerHTML = '<p class="err">' + esc(e.message) + '</p>';
    $("approved").innerHTML = "";
  }
}

function renderPending(rows) {
  if (rows.length === 0) {
    $("pending").innerHTML = '<p class="empty">No pending requests.</p>';
    return;
  }
  let html = '<table><thead><tr><th>Email</th><th>Requested</th><th>Note</th><th>Country</th><th></th></tr></thead><tbody>';
  for (const r of rows) {
    html += '<tr>'
      + '<td>' + esc(r.email) + '</td>'
      + '<td>' + esc(r.requested_at).slice(0,16).replace("T"," ") + '</td>'
      + '<td>' + esc(r.note || "") + '</td>'
      + '<td>' + esc(r.country || "") + '</td>'
      + '<td class="actions">'
      +   '<button class="primary" onclick="act(\\'approve\\',' + r.id + ')">Approve</button>'
      +   '<button class="danger"  onclick="act(\\'deny\\','    + r.id + ')">Deny</button>'
      + '</td></tr>';
  }
  html += '</tbody></table>';
  $("pending").innerHTML = html;
}

function renderApproved(rows) {
  if (rows.length === 0) {
    $("approved").innerHTML = '<p class="empty">No approved users yet.</p>';
    return;
  }
  let html = '<table><thead><tr><th>Email</th><th>Approved</th><th>By</th><th>Note</th><th></th></tr></thead><tbody>';
  for (const r of rows) {
    html += '<tr>'
      + '<td>' + esc(r.email) + '</td>'
      + '<td>' + esc(r.approved_at).slice(0,16).replace("T"," ") + '</td>'
      + '<td>' + esc(r.approved_by) + '</td>'
      + '<td>' + esc(r.note || "") + '</td>'
      + '<td class="actions">'
      +   '<button class="danger" onclick="revoke(\\'' + esc(r.email) + '\\')">Revoke</button>'
      + '</td></tr>';
  }
  html += '</tbody></table>';
  $("approved").innerHTML = html;
}

async function act(kind, id) {
  const verb = kind === "approve" ? "Approve" : "Deny";
  if (!confirm(verb + " request #" + id + "?")) return;
  const r = await fetch("/admin/api/" + kind, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ id })
  });
  if (!r.ok) alert("Failed: " + r.status);
  await load();
}

async function revoke(email) {
  if (!confirm("Revoke access for " + email + "? They will get a 403 on next request.")) return;
  const r = await fetch("/admin/api/revoke", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email })
  });
  if (!r.ok) alert("Failed: " + r.status);
  await load();
}

load();
</script>
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

export function renderDenied(check: AdminCheck): Response {
  // For no-session: bounce to /. For invalid/not-admin/misconfigured:
  // a static 403 page. We avoid looping to login for invalid-session
  // because the user might loop forever if their cookie is stuck bad.
  if (check.kind === "no-session") {
    return new Response(null, {
      status: 302,
      headers: { location: "/?return_to=/admin" },
    });
  }
  const detail =
    check.kind === "not-admin"
      ? `You're signed in, but this account isn't on the admin list.`
      : check.kind === "misconfigured"
        ? `Admin features aren't configured on this deployment.`
        : `We couldn't verify your session.`;
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Not authorised · CJI Pro</title>
<style>${STYLES}</style></head><body><main>
<h1>Not authorised</h1>
<p class="sub">${escapeHtml(detail)}</p>
<p><a href="/">Back to sign in</a></p>
</main></body></html>`;
  return new Response(html, {
    status: 403,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

// --- JSON API ---

export async function handleApiSignups(
  db: D1Database,
): Promise<Response> {
  const [pending, approved] = await Promise.all([
    listByStatus(db, "pending"),
    listApproved(db),
  ]);
  return json({ pending, approved });
}

async function readJson<T>(request: Request): Promise<T | null> {
  try {
    return (await request.json()) as T;
  } catch {
    return null;
  }
}

export async function handleApiApprove(
  request: Request,
  db: D1Database,
  adminEmail: string,
): Promise<Response> {
  const body = await readJson<{ id?: number }>(request);
  if (!body || typeof body.id !== "number") {
    return json({ ok: false, error: "missing id" }, 400);
  }
  const out = await approvePending(db, body.id, adminEmail);
  if (out.kind !== "ok") return json({ ok: false, error: out.kind }, 400);
  return json({ ok: true });
}

export async function handleApiDeny(
  request: Request,
  db: D1Database,
  adminEmail: string,
): Promise<Response> {
  const body = await readJson<{ id?: number }>(request);
  if (!body || typeof body.id !== "number") {
    return json({ ok: false, error: "missing id" }, 400);
  }
  const out = await denyPending(db, body.id, adminEmail);
  if (out.kind !== "ok") return json({ ok: false, error: out.kind }, 400);
  return json({ ok: true });
}

export async function handleApiRevoke(
  request: Request,
  db: D1Database,
): Promise<Response> {
  const body = await readJson<{ email?: string }>(request);
  if (!body || typeof body.email !== "string") {
    return json({ ok: false, error: "missing email" }, 400);
  }
  const out = await revokeApproval(db, body.email);
  if (out.kind !== "ok") return json({ ok: false, error: out.kind }, 400);
  return json({ ok: true });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
    },
  });
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Used by adminRoutesCfgFromEnv in index.ts — kept here alongside
// the type that consumes it so a config change is one place.
export type { AdminGateConfig };
