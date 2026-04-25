// MIL-72 — per-tenant audit log export.
//
// Joins auth_events to sessions to filter the timeline to events
// whose actor (session_sub_hash) belongs to a user in the requested
// WorkOS organization. Two output formats: JSONL (one event per line,
// best for SIEM ingestion) and CSV (best for spreadsheets).
//
// What's INCLUDED in a tenant export:
//   - bouncer.* events for users in the org
//   - magic_link.* events for users in the org
//   - dsync.* events scoped to the org
//   - workos.webhook events tied to a user in the org
//
// What's EXCLUDED (global, not per-tenant):
//   - admin.* events (your governance, not the partner's)
//   - signup.request events (no org assigned at request time)
//   - bouncer.pass.public events (no user attached)
//
// The actor join is via session_sub_hash → sessions.sub. Note: the
// audit log stores HASHED sub (sha256(sub || daily_salt)), so we
// must match by hash too. Same daily-salt store; the export query
// recomputes hashes per day in the requested window.

import { sha256Hex } from "../../audit/src/hash";
import { d1SaltStore, utcDateString } from "../../audit/src/salt";

export type ExportFormat = "jsonl" | "csv";

export interface ExportInput {
  organizationId: string;
  since: string; // ISO-8601
  until: string; // ISO-8601
  format: ExportFormat;
}

export interface ExportRow {
  id: number;
  ts: string;
  worker: string;
  event_type: string;
  method: string | null;
  host: string | null;
  path: string | null;
  enforce: number | null;
  country: string | null;
  reason: string | null;
  detail: string | null;
}

// The exported event row — public fields only. Internal hash columns
// (user_hash, ip_hash, ua_hash, prev_hash, row_hash) are NOT included
// in the partner-facing export. The partner shouldn't need to reverse
// our salts; if they want to correlate sessions they have their own
// IdP logs.

export async function exportAuditForOrg(
  db: D1Database,
  input: ExportInput,
): Promise<{ contentType: string; body: string; rowCount: number }> {
  // Step 1: collect every sub in this org from sessions.
  const sessRes = await db
    .prepare("SELECT sub FROM sessions WHERE organization_id = ?")
    .bind(input.organizationId)
    .all<{ sub: string }>();
  const subs = (sessRes.results ?? []).map((r) => r.sub);

  if (subs.length === 0) {
    return formatRows([], input.format);
  }

  // Step 2: collect every (date, salt) we need to compute hashes.
  // Daily salts are written when the first event of each UTC day is
  // logged. We need salts for every day in the [since, until] window.
  const sinceDate = new Date(input.since);
  const untilDate = new Date(input.until);
  const days = enumerateUtcDays(sinceDate, untilDate);
  const saltStore = d1SaltStore(db);
  const saltByDate = new Map<string, string>();
  for (const day of days) {
    try {
      const salt = await saltStore.getOrCreate(day);
      saltByDate.set(day, salt);
    } catch {
      // No salt = no events that day — skip.
    }
  }

  // Step 3: compute the set of user_hash values we want to match.
  // Each (sub, day) pair produces one hash because the salt rotates.
  const wantedHashes = new Set<string>();
  for (const sub of subs) {
    for (const [, salt] of saltByDate) {
      wantedHashes.add(await sha256Hex(sub + salt));
    }
  }

  if (wantedHashes.size === 0) {
    return formatRows([], input.format);
  }

  // Step 4: pull events in the window and filter by user_hash. SQLite
  // doesn't have a great way to bind a large IN-list; chunk if needed.
  const placeholders = Array.from(wantedHashes).map(() => "?").join(",");
  const sql = `
    SELECT id, ts, worker, event_type, method, host, path, enforce,
           country, reason, detail
    FROM auth_events
    WHERE ts >= ? AND ts <= ?
      AND user_hash IN (${placeholders})
    ORDER BY id ASC
  `;
  const allRes = await db
    .prepare(sql)
    .bind(input.since, input.until, ...Array.from(wantedHashes))
    .all<ExportRow>();
  const rows = allRes.results ?? [];

  return formatRows(rows, input.format);
}

function formatRows(
  rows: ExportRow[],
  format: ExportFormat,
): { contentType: string; body: string; rowCount: number } {
  if (format === "csv") {
    const header =
      "id,ts,worker,event_type,method,host,path,enforce,country,reason,detail";
    const lines = rows.map(csvLine);
    return {
      contentType: "text/csv; charset=utf-8",
      body: [header, ...lines].join("\n"),
      rowCount: rows.length,
    };
  }
  // default: jsonl
  return {
    contentType: "application/x-ndjson",
    body: rows.map((r) => JSON.stringify(r)).join("\n"),
    rowCount: rows.length,
  };
}

function csvLine(r: ExportRow): string {
  return [
    r.id,
    csvEscape(r.ts),
    csvEscape(r.worker),
    csvEscape(r.event_type),
    csvEscape(r.method),
    csvEscape(r.host),
    csvEscape(r.path),
    r.enforce ?? "",
    csvEscape(r.country),
    csvEscape(r.reason),
    csvEscape(r.detail),
  ].join(",");
}

function csvEscape(v: string | number | null): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function enumerateUtcDays(since: Date, until: Date): string[] {
  const out: string[] = [];
  const cursor = new Date(
    Date.UTC(
      since.getUTCFullYear(),
      since.getUTCMonth(),
      since.getUTCDate(),
    ),
  );
  const end = new Date(
    Date.UTC(until.getUTCFullYear(), until.getUTCMonth(), until.getUTCDate()),
  );
  while (cursor.getTime() <= end.getTime()) {
    out.push(utcDateString(cursor));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}
