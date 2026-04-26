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
  listByStatus,
  revokeApproval,
} from "../../approvals/src/signups";
import {
  forceSignout,
  listApprovedWithSessions,
} from "../../approvals/src/sessions";
import {
  generatePortalLink,
  type PortalIntent,
} from "../../approvals/src/admin_portal";
import {
  exportAuditForOrg,
  type ExportFormat,
} from "../../approvals/src/audit_export";

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

<h2>Per-tenant audit export</h2>
<p class="sub">Download the audit timeline scoped to a single partner
 organization. Format: JSONL for SIEM ingest, CSV for spreadsheets.
 Default window: last 7 days.</p>
<div style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center; margin-bottom:0.5rem;">
  <input id="export_org" type="text" placeholder="org_01HXYZ..." style="flex:1; min-width:14rem; padding:0.4rem 0.55rem; font:inherit; border:1px solid #b7c2ca; border-radius:3px;">
  <input id="export_since" type="datetime-local" style="padding:0.4rem 0.55rem; font:inherit; border:1px solid #b7c2ca; border-radius:3px;">
  <input id="export_until" type="datetime-local" style="padding:0.4rem 0.55rem; font:inherit; border:1px solid #b7c2ca; border-radius:3px;">
  <select id="export_format" style="padding:0.4rem 0.55rem; font:inherit; border:1px solid #b7c2ca; border-radius:3px;">
    <option value="jsonl">jsonl</option>
    <option value="csv">csv</option>
  </select>
  <button class="primary" onclick="exportAudit()">Download</button>
</div>

<h2>Partner SSO setup link</h2>
<p class="sub">Generate a one-shot WorkOS Admin Portal link for a partner
 organization. Share with their IT — they configure SAML / SCIM /
 domain verification inside WorkOS's hosted UI. Link expires in 5 min.</p>
<div style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center; margin-bottom:0.5rem;">
  <input id="org_id" type="text" placeholder="org_01HXYZ..." style="flex:1; min-width:18rem; padding:0.4rem 0.55rem; font:inherit; border:1px solid #b7c2ca; border-radius:3px;">
  <select id="intent" style="padding:0.4rem 0.55rem; font:inherit; border:1px solid #b7c2ca; border-radius:3px;">
    <option value="sso">sso</option>
    <option value="domain_verification">domain_verification</option>
    <option value="dsync">dsync</option>
    <option value="audit_logs">audit_logs</option>
    <option value="log_streams">log_streams</option>
  </select>
  <button class="primary" onclick="generateLink()">Generate</button>
</div>
<div id="portal_link_out"></div>

<script>
const $ = (id) => document.getElementById(id);

// MIL-83 — API base is host-aware. On admin.cjipro.com the
// dashboard is mounted at root and APIs live at /api/*; on
// login.cjipro.com (legacy) they live at /admin/api/*. The
// Worker accepts both shapes.
const A = location.host === "admin.cjipro.com" ? "" : "/admin";

function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function load() {
  try {
    const r = await fetch(A + "/api/signups");
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

function relTime(iso) {
  if (!iso) return '<span style="color:var(--muted)">never</span>';
  const then = new Date(iso).getTime();
  if (isNaN(then)) return '<span style="color:var(--muted)">—</span>';
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  const d = Math.floor(h / 24);
  return d + 'd ago';
}

function renderApproved(rows) {
  if (rows.length === 0) {
    $("approved").innerHTML = '<p class="empty">No approved users yet.</p>';
    return;
  }
  let html = '<table><thead><tr><th>Email</th><th>Approved</th><th>By</th><th>Last seen</th><th>Note</th><th></th></tr></thead><tbody>';
  for (const r of rows) {
    html += '<tr>'
      + '<td>' + esc(r.email) + '</td>'
      + '<td>' + esc(r.approved_at).slice(0,16).replace("T"," ") + '</td>'
      + '<td>' + esc(r.approved_by) + '</td>'
      + '<td>' + relTime(r.last_active_at) + '</td>'
      + '<td>' + esc(r.note || "") + '</td>'
      + '<td class="actions">'
      +   '<button onclick="signout(\\'' + esc(r.email) + '\\')">Sign out</button>'
      +   '<button class="danger" onclick="revoke(\\'' + esc(r.email) + '\\')">Revoke</button>'
      + '</td></tr>';
  }
  html += '</tbody></table>';
  $("approved").innerHTML = html;
}

async function act(kind, id) {
  const verb = kind === "approve" ? "Approve" : "Deny";
  if (!confirm(verb + " request #" + id + "?")) return;
  const r = await fetch(A + "/api/" + kind, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ id })
  });
  if (!r.ok) alert("Failed: " + r.status);
  await load();
}

async function revoke(email) {
  if (!confirm("Revoke access for " + email + "? They will get a 403 on next request.")) return;
  const r = await fetch(A + "/api/revoke", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email })
  });
  if (!r.ok) alert("Failed: " + r.status);
  await load();
}

async function signout(email) {
  if (!confirm("Force sign-out for " + email + "? Their cached session is killed; they remain on the approved list and can sign back in.")) return;
  const r = await fetch(A + "/api/force_signout", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email })
  });
  if (!r.ok) alert("Failed: " + r.status);
  await load();
}

function isoOrEmpty(local) {
  if (!local) return "";
  const d = new Date(local);
  if (isNaN(d.getTime())) return "";
  return d.toISOString();
}

function exportAudit() {
  const org = $("export_org").value.trim();
  const since = isoOrEmpty($("export_since").value);
  const until = isoOrEmpty($("export_until").value);
  const format = $("export_format").value;
  if (!org) { alert("Enter an organization id (e.g. org_01HXYZ…)"); return; }
  const params = new URLSearchParams({ org, format });
  if (since) params.set("since", since);
  if (until) params.set("until", until);
  // Trigger a real download by navigating to the URL — Content-Disposition
  // headers on the response make the browser save it.
  window.location.href = A + "/api/audit_export?" + params.toString();
}

async function generateLink() {
  const org_id = $("org_id").value.trim();
  const intent = $("intent").value;
  if (!org_id) { alert("Enter an organization id (e.g. org_01HXYZ…)"); return; }
  const out = $("portal_link_out");
  out.innerHTML = '<p class="sub">Requesting…</p>';
  const r = await fetch(A + "/api/portal_link", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ organization_id: org_id, intent })
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.ok) {
    out.innerHTML = '<p class="err">Failed: ' + esc(j.error || ("HTTP " + r.status)) + (j.detail ? ' — ' + esc(j.detail) : '') + '</p>';
    return;
  }
  out.innerHTML =
    '<p class="sub">Link valid for 5 min. Share with the partner\\'s IT contact:</p>'
    + '<div style="display:flex; gap:0.5rem; align-items:center;">'
    +   '<input readonly value="' + esc(j.link) + '" style="flex:1; padding:0.4rem 0.55rem; font:ui-monospace,monospace; font-size:0.82rem; border:1px solid #b7c2ca; border-radius:3px; background:#fff;">'
    +   '<button onclick="navigator.clipboard.writeText(\\'' + esc(j.link) + '\\').then(() => alert(\\'Copied\\'))">Copy</button>'
    + '</div>';
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

export function renderDenied(check: AdminCheck, request?: Request): Response {
  // For no-session: bounce to /. For invalid/not-admin/misconfigured:
  // a static 403 page. We avoid looping to login for invalid-session
  // because the user might loop forever if their cookie is stuck bad.
  if (check.kind === "no-session") {
    // MIL-83 — on admin.cjipro.com a relative location loops:
    //   /  → path rewrite to /admin → no-session → 302 / → / rewrites
    //   to /admin again. Send absolute Location to login.cjipro.com.
    //   Cross-origin return_to back to admin host would require widening
    //   isValidReturnTo to allow cjipro.com origins; deferred. After auth
    //   the user lands on login.cjipro.com/admin via backwards-compat.
    let location = "/?return_to=/admin";
    if (request) {
      const url = new URL(request.url);
      if (url.host === "admin.cjipro.com") {
        location = "https://login.cjipro.com/?return_to=/admin";
      }
    }
    return new Response(null, {
      status: 302,
      headers: { location },
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
    listApprovedWithSessions(db),
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

// MIL-70 — generate a short-lived (5min) WorkOS Admin Portal setup
// link for a partner organization. Caller (admin) shares the link
// with the partner's IT team; they configure SAML/SCIM/etc. inside
// WorkOS's hosted UI; activation events flow back via webhooks.
export async function handleApiPortalLink(
  request: Request,
  workosApiKey: string,
): Promise<Response> {
  const body = await readJson<{
    organization_id?: string;
    intent?: string;
    return_url?: string;
  }>(request);
  if (!body || typeof body.organization_id !== "string") {
    return json({ ok: false, error: "missing organization_id" }, 400);
  }
  const validIntents: PortalIntent[] = [
    "sso",
    "domain_verification",
    "dsync",
    "audit_logs",
    "log_streams",
  ];
  const intent = (body.intent ?? "sso") as PortalIntent;
  if (!validIntents.includes(intent)) {
    return json({ ok: false, error: `invalid intent: ${body.intent}` }, 400);
  }
  const out = await generatePortalLink(workosApiKey, {
    organizationId: body.organization_id,
    intent,
    returnUrl: body.return_url,
  });
  if (!out.ok) {
    return json(
      { ok: false, error: out.reason, detail: out.detail },
      out.status,
    );
  }
  return json({ ok: true, link: out.link });
}

// MIL-72 — per-tenant audit log export. GET so partners can hit
// it from a SIEM cron with a curl/wget. Body is plaintext (JSONL or
// CSV); content-type set per format.
export async function handleApiAuditExport(
  url: URL,
  db: D1Database,
): Promise<Response> {
  const orgId = url.searchParams.get("org") ?? "";
  if (!orgId) {
    return json({ ok: false, error: "missing org param" }, 400);
  }
  const since = url.searchParams.get("since") ?? defaultSince();
  const until = url.searchParams.get("until") ?? new Date().toISOString();
  const formatRaw = (url.searchParams.get("format") ?? "jsonl").toLowerCase();
  if (formatRaw !== "jsonl" && formatRaw !== "csv") {
    return json(
      { ok: false, error: "format must be jsonl or csv" },
      400,
    );
  }
  const format = formatRaw as ExportFormat;
  const out = await exportAuditForOrg(db, {
    organizationId: orgId,
    since,
    until,
    format,
  });
  const ext = format === "csv" ? "csv" : "jsonl";
  return new Response(out.body, {
    status: 200,
    headers: {
      "content-type": out.contentType,
      "cache-control": "no-store",
      "content-disposition": `attachment; filename="audit_${orgId}_${since.slice(0, 10)}_${until.slice(0, 10)}.${ext}"`,
      "x-row-count": String(out.rowCount),
    },
  });
}

function defaultSince(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 7);
  return d.toISOString();
}

// MIL-68 — boot any active session for this user without removing
// them from approved_users. They can sign back in but the cached
// JWT they currently hold is dead on next request.
export async function handleApiForceSignout(
  request: Request,
  db: D1Database,
): Promise<Response> {
  const body = await readJson<{ email?: string }>(request);
  if (!body || typeof body.email !== "string") {
    return json({ ok: false, error: "missing email" }, 400);
  }
  const out = await forceSignout(db, body.email);
  if (out.kind !== "ok") return json({ ok: false, error: out.kind }, 400);
  return json({ ok: true, affected: out.affected });
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
