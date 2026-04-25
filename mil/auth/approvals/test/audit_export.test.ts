import { describe, expect, test } from "vitest";
import { exportAuditForOrg } from "../src/audit_export";
import { sha256Hex } from "../../audit/src/hash";
import { utcDateString } from "../../audit/src/salt";

// The export query is harder to fake than other modules — it uses
// dynamic placeholder counts in IN-lists, calls sha256, etc. So we
// test against a richer fake than the shared FakeD1.

class ExportFakeD1 {
  sessions: { sub: string; organization_id: string | null }[] = [];
  salts: Map<string, string> = new Map();
  events: {
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
    user_hash: string | null;
  }[] = [];

  prepare(sql: string) {
    return new ExportStmt(this, sql, []);
  }
  async batch<T>(stmts: ExportStmt[]) {
    const out: { results?: T[] }[] = [];
    for (const s of stmts) out.push(await s._run<T>());
    return out;
  }
}

class ExportStmt {
  constructor(
    private db: ExportFakeD1,
    private sql: string,
    private args: unknown[],
  ) {}
  bind(...args: unknown[]) {
    return new ExportStmt(this.db, this.sql, args);
  }
  async first<T = unknown>() {
    const r = await this._run<T>();
    return r.results?.[0] ?? null;
  }
  async all<T = unknown>() {
    return this._run<T>();
  }
  async run() {
    return this._run();
  }
  async _run<T = unknown>(): Promise<{ results?: T[] }> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("SELECT sub FROM sessions WHERE organization_id")) {
      const orgId = this.args[0] as string;
      return {
        results: this.db.sessions
          .filter((r) => r.organization_id === orgId)
          .map((r) => ({ sub: r.sub })) as T[],
      };
    }
    if (s.startsWith("INSERT OR IGNORE INTO audit_salts")) {
      const [date, salt] = this.args as [string, string];
      if (!this.db.salts.has(date)) this.db.salts.set(date, salt);
      return { results: [] };
    }
    if (s.startsWith("SELECT salt FROM audit_salts")) {
      const [date] = this.args as [string];
      const salt = this.db.salts.get(date);
      return { results: salt ? ([{ salt }] as T[]) : [] };
    }
    if (s.startsWith("SELECT id, ts, worker, event_type")) {
      const [since, until, ...hashes] = this.args as [string, string, ...string[]];
      const hashSet = new Set(hashes);
      const matched = this.db.events.filter(
        (e) =>
          e.ts >= since &&
          e.ts <= until &&
          e.user_hash !== null &&
          hashSet.has(e.user_hash),
      );
      return {
        results: matched.map((e) => {
          const { user_hash: _h, ...rest } = e;
          return rest as T;
        }),
      };
    }
    throw new Error(`ExportFakeD1: unhandled SQL: ${this.sql}`);
  }
}

const asD1 = (db: ExportFakeD1) => db as unknown as D1Database;

async function seedEventsForSub(
  db: ExportFakeD1,
  sub: string,
  date: string,
  events: { id: number; ts: string; event_type: string; path?: string }[],
): Promise<void> {
  // Generate the salt for this date if absent (mirrors d1SaltStore
  // behavior of writing-on-demand).
  let salt = db.salts.get(date);
  if (!salt) {
    salt = "salt_" + date.replace(/-/g, "");
    db.salts.set(date, salt);
  }
  const userHash = await sha256Hex(sub + salt);
  for (const e of events) {
    db.events.push({
      id: e.id,
      ts: e.ts,
      worker: "edge-bouncer",
      event_type: e.event_type,
      method: "GET",
      host: "cjipro.com",
      path: e.path ?? "/briefing-v4/",
      enforce: 1,
      country: "GB",
      reason: null,
      detail: null,
      user_hash: userHash,
    });
  }
}

describe("exportAuditForOrg", () => {
  const SINCE = "2026-04-25T00:00:00Z";
  const UNTIL = "2026-04-25T23:59:59Z";
  const DAY = utcDateString(new Date(SINCE));

  test("empty result when no sessions for org", async () => {
    const db = new ExportFakeD1();
    const out = await exportAuditForOrg(asD1(db), {
      organizationId: "org_empty",
      since: SINCE,
      until: UNTIL,
      format: "jsonl",
    });
    expect(out.rowCount).toBe(0);
    expect(out.body).toBe("");
  });

  test("filters to only org members' events", async () => {
    const db = new ExportFakeD1();
    db.sessions.push({ sub: "u_alpha", organization_id: "org_partner" });
    db.sessions.push({ sub: "u_other", organization_id: "org_other" });

    await seedEventsForSub(db, "u_alpha", DAY, [
      { id: 1, ts: "2026-04-25T08:00:00Z", event_type: "bouncer.pass.session" },
      { id: 2, ts: "2026-04-25T09:00:00Z", event_type: "magic_link.callback.success" },
    ]);
    await seedEventsForSub(db, "u_other", DAY, [
      { id: 3, ts: "2026-04-25T08:30:00Z", event_type: "bouncer.pass.session" },
    ]);

    const out = await exportAuditForOrg(asD1(db), {
      organizationId: "org_partner",
      since: SINCE,
      until: UNTIL,
      format: "jsonl",
    });
    expect(out.rowCount).toBe(2);
    const lines = out.body.split("\n");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain('"id":1');
    expect(lines[1]).toContain('"id":2');
  });

  test("respects time window", async () => {
    const db = new ExportFakeD1();
    db.sessions.push({ sub: "u_alpha", organization_id: "org_partner" });
    await seedEventsForSub(db, "u_alpha", DAY, [
      { id: 10, ts: "2026-04-25T08:00:00Z", event_type: "bouncer.pass.session" },
    ]);
    // Day before — should NOT be included
    await seedEventsForSub(db, "u_alpha", "2026-04-24", [
      { id: 9, ts: "2026-04-24T08:00:00Z", event_type: "bouncer.pass.session" },
    ]);

    const out = await exportAuditForOrg(asD1(db), {
      organizationId: "org_partner",
      since: SINCE,
      until: UNTIL,
      format: "jsonl",
    });
    expect(out.rowCount).toBe(1);
    expect(out.body).toContain('"id":10');
  });

  test("CSV format has header + escaped fields", async () => {
    const db = new ExportFakeD1();
    db.sessions.push({ sub: "u_alpha", organization_id: "org_partner" });
    await seedEventsForSub(db, "u_alpha", DAY, [
      { id: 1, ts: "2026-04-25T08:00:00Z", event_type: "bouncer.pass.session" },
    ]);
    const out = await exportAuditForOrg(asD1(db), {
      organizationId: "org_partner",
      since: SINCE,
      until: UNTIL,
      format: "csv",
    });
    expect(out.contentType).toBe("text/csv; charset=utf-8");
    const lines = out.body.split("\n");
    expect(lines[0]).toBe(
      "id,ts,worker,event_type,method,host,path,enforce,country,reason,detail",
    );
    expect(lines[1]).toContain("1,2026-04-25T08:00:00Z,edge-bouncer");
  });

  test("internal hash columns are NOT in export output", async () => {
    const db = new ExportFakeD1();
    db.sessions.push({ sub: "u_alpha", organization_id: "org_partner" });
    await seedEventsForSub(db, "u_alpha", DAY, [
      { id: 1, ts: "2026-04-25T08:00:00Z", event_type: "bouncer.pass.session" },
    ]);
    const out = await exportAuditForOrg(asD1(db), {
      organizationId: "org_partner",
      since: SINCE,
      until: UNTIL,
      format: "jsonl",
    });
    expect(out.body).not.toContain("user_hash");
    expect(out.body).not.toContain("ip_hash");
    expect(out.body).not.toContain("ua_hash");
    expect(out.body).not.toContain("prev_hash");
    expect(out.body).not.toContain("row_hash");
  });

  test("multi-day window: events across days correlated via per-day salts", async () => {
    const db = new ExportFakeD1();
    db.sessions.push({ sub: "u_alpha", organization_id: "org_partner" });
    await seedEventsForSub(db, "u_alpha", "2026-04-25", [
      { id: 1, ts: "2026-04-25T08:00:00Z", event_type: "bouncer.pass.session" },
    ]);
    await seedEventsForSub(db, "u_alpha", "2026-04-26", [
      { id: 2, ts: "2026-04-26T08:00:00Z", event_type: "bouncer.pass.session" },
    ]);
    const out = await exportAuditForOrg(asD1(db), {
      organizationId: "org_partner",
      since: "2026-04-25T00:00:00Z",
      until: "2026-04-26T23:59:59Z",
      format: "jsonl",
    });
    expect(out.rowCount).toBe(2);
  });
});
