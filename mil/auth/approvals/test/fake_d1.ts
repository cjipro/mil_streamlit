// Minimal D1 fake — enough for the approvals lib surface area:
// SELECT/INSERT on approved_users, pending_signups, admin_users,
// signup_rate_limit.

interface ApprovedUserRow {
  email: string;
  approved_at: string;
  approved_by: string;
  note: string | null;
}

interface PendingSignupRow {
  id: number;
  email: string;
  requested_at: string;
  ip_hash: string | null;
  ua_hash: string | null;
  note: string | null;
  status: "pending" | "approved" | "denied";
  reviewed_at: string | null;
  reviewed_by: string | null;
}

interface AdminUserRow {
  email: string;
  added_at: string;
  added_by: string;
}

interface RateLimitRow {
  ip_hash: string;
  window: string;
  count: number;
}

interface AutoApproveRow {
  organization_id: string;
  added_at: string;
  added_by: string;
  note: string | null;
}

interface SessionRow {
  sub: string;
  email: string;
  created_at: string;
  last_active_at: string | null;
}

export class FakeD1 {
  public users: ApprovedUserRow[] = [];
  public signups: PendingSignupRow[] = [];
  public admins: AdminUserRow[] = [];
  public rateLimits: RateLimitRow[] = [];
  public sessions: SessionRow[] = [];
  public autoApproveOrgs: AutoApproveRow[] = [];
  public nextSignupId = 1;

  prepare(sql: string): FakeStatement {
    return new FakeStatement(this, sql, []);
  }
}

export class FakeStatement {
  constructor(
    private db: FakeD1,
    private sql: string,
    private args: unknown[],
  ) {}

  bind(...args: unknown[]): FakeStatement {
    return new FakeStatement(this.db, this.sql, args);
  }

  async first<T = unknown>(): Promise<T | null> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    // approvals
    if (s.startsWith("SELECT 1 AS present FROM approved_users")) {
      const email = this.args[0] as string;
      return this.db.users.find((u) => u.email === email)
        ? ({ present: 1 } as T)
        : null;
    }
    // admin
    if (s.startsWith("SELECT 1 AS present FROM admin_users")) {
      const email = this.args[0] as string;
      return this.db.admins.find((a) => a.email === email)
        ? ({ present: 1 } as T)
        : null;
    }
    // pending lookup
    if (s.startsWith("SELECT id FROM pending_signups WHERE email")) {
      const email = this.args[0] as string;
      const hit = [...this.db.signups]
        .reverse()
        .find((r) => r.email === email && r.status === "pending");
      return hit ? ({ id: hit.id } as T) : null;
    }
    if (s.startsWith("SELECT email, status FROM pending_signups WHERE id =")) {
      const id = this.args[0] as number;
      const hit = this.db.signups.find((r) => r.id === id);
      return hit ? ({ email: hit.email, status: hit.status } as T) : null;
    }
    if (s.startsWith("SELECT status FROM pending_signups WHERE id =")) {
      const id = this.args[0] as number;
      const hit = this.db.signups.find((r) => r.id === id);
      return hit ? ({ status: hit.status } as T) : null;
    }
    // sessions
    if (s.startsWith("SELECT 1 AS present FROM auto_approve_orgs")) {
      const orgId = this.args[0] as string;
      return this.db.autoApproveOrgs.find((o) => o.organization_id === orgId)
        ? ({ present: 1 } as T)
        : null;
    }
    if (s.startsWith("SELECT email FROM sessions WHERE sub")) {
      const sub = this.args[0] as string;
      const hit = this.db.sessions.find((r) => r.sub === sub);
      return hit ? ({ email: hit.email } as T) : null;
    }
    // rate limit
    if (s.startsWith("SELECT count FROM signup_rate_limit")) {
      const [ipHash, window] = this.args as [string, string];
      const hit = this.db.rateLimits.find(
        (r) => r.ip_hash === ipHash && r.window === window,
      );
      return hit ? ({ count: hit.count } as T) : null;
    }
    throw new Error(`FakeD1.first: unhandled SQL: ${this.sql}`);
  }

  async all<T = unknown>(): Promise<{ results?: T[] }> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("SELECT * FROM pending_signups WHERE status")) {
      const [status, limit] = this.args as [string, number];
      const rows = this.db.signups
        .filter((r) => r.status === status)
        .sort((a, b) => b.requested_at.localeCompare(a.requested_at))
        .slice(0, limit);
      return { results: rows as T[] };
    }
    if (s.startsWith("SELECT email, approved_at, approved_by, note FROM approved_users")) {
      const [limit] = this.args as [number];
      const rows = [...this.db.users]
        .sort((a, b) => b.approved_at.localeCompare(a.approved_at))
        .slice(0, limit)
        .map((r) => ({
          email: r.email,
          approved_at: r.approved_at,
          approved_by: r.approved_by,
          note: r.note,
        }));
      return { results: rows as T[] };
    }
    if (s.includes("approved_users au") && s.includes("LEFT JOIN sessions s")) {
      const [limit] = this.args as [number];
      const rows = [...this.db.users]
        .sort((a, b) => b.approved_at.localeCompare(a.approved_at))
        .slice(0, limit)
        .map((u) => {
          const sess = this.db.sessions.find((s) => s.email === u.email);
          return {
            email: u.email,
            approved_at: u.approved_at,
            approved_by: u.approved_by,
            note: u.note,
            last_active_at: sess?.last_active_at ?? null,
          };
        });
      return { results: rows as T[] };
    }
    throw new Error(`FakeD1.all: unhandled SQL: ${this.sql}`);
  }

  async run(): Promise<{ meta?: { last_row_id?: number; changes?: number } }> {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("INSERT INTO pending_signups")) {
      const id = this.db.nextSignupId++;
      this.db.signups.push({
        id,
        email: this.args[0] as string,
        requested_at: this.args[1] as string,
        ip_hash: (this.args[2] as string | null) ?? null,
        ua_hash: (this.args[3] as string | null) ?? null,
        note: (this.args[4] as string | null) ?? null,
        status: "pending",
        reviewed_at: null,
        reviewed_by: null,
      });
      return { meta: { last_row_id: id } };
    }
    if (s.startsWith("INSERT OR IGNORE INTO approved_users")) {
      const [email, approved_at, approved_by] = this.args as [string, string, string];
      if (!this.db.users.find((u) => u.email === email)) {
        this.db.users.push({ email, approved_at, approved_by, note: "via signup request" });
      }
      return {};
    }
    if (s.startsWith("UPDATE pending_signups SET status =")) {
      // status is embedded in the SQL between single-quotes —
      // extract it to keep the fake honest.
      const m = s.match(/SET status = '(\w+)'/);
      const status = (m?.[1] ?? "pending") as "approved" | "denied";
      const [reviewedAt, reviewedBy, id] = this.args as [string, string, number];
      const row = this.db.signups.find((r) => r.id === id);
      if (row) {
        row.status = status;
        row.reviewed_at = reviewedAt;
        row.reviewed_by = reviewedBy;
      }
      return {};
    }
    if (s.startsWith("DELETE FROM approved_users")) {
      const email = this.args[0] as string;
      this.db.users = this.db.users.filter((u) => u.email !== email);
      return {};
    }
    if (s.startsWith("INSERT OR REPLACE INTO sessions")) {
      const [sub, email, created_at] = this.args as [string, string, string];
      const existing = this.db.sessions.find((r) => r.sub === sub);
      if (existing) {
        existing.email = email;
        existing.created_at = created_at;
        existing.last_active_at = null;
      } else {
        this.db.sessions.push({
          sub,
          email,
          created_at,
          last_active_at: null,
        });
      }
      return {};
    }
    if (s.startsWith("UPDATE sessions SET last_active_at")) {
      const [last_active_at, sub] = this.args as [string, string];
      const hit = this.db.sessions.find((r) => r.sub === sub);
      if (hit) hit.last_active_at = last_active_at;
      return {};
    }
    if (s.startsWith("DELETE FROM sessions")) {
      const email = this.args[0] as string;
      const before = this.db.sessions.length;
      this.db.sessions = this.db.sessions.filter((r) => r.email !== email);
      return { meta: { changes: before - this.db.sessions.length } };
    }
    if (s.startsWith("INSERT OR IGNORE INTO auto_approve_orgs")) {
      const [organization_id, added_at, added_by, note] = this.args as [
        string,
        string,
        string,
        string | null,
      ];
      if (!this.db.autoApproveOrgs.find((o) => o.organization_id === organization_id)) {
        this.db.autoApproveOrgs.push({
          organization_id,
          added_at,
          added_by,
          note: note ?? null,
        });
      }
      return {};
    }
    if (s.startsWith("DELETE FROM auto_approve_orgs")) {
      const orgId = this.args[0] as string;
      const before = this.db.autoApproveOrgs.length;
      this.db.autoApproveOrgs = this.db.autoApproveOrgs.filter(
        (o) => o.organization_id !== orgId,
      );
      return { meta: { changes: before - this.db.autoApproveOrgs.length } };
    }
    if (s.startsWith("INSERT OR IGNORE INTO signup_rate_limit")) {
      const [ipHash, window] = this.args as [string, string, number];
      if (
        !this.db.rateLimits.find((r) => r.ip_hash === ipHash && r.window === window)
      ) {
        this.db.rateLimits.push({ ip_hash: ipHash, window, count: 0 });
      }
      return {};
    }
    if (s.startsWith("UPDATE signup_rate_limit SET count = count + 1")) {
      const [ipHash, window] = this.args as [string, string];
      const hit = this.db.rateLimits.find(
        (r) => r.ip_hash === ipHash && r.window === window,
      );
      if (hit) hit.count += 1;
      return {};
    }
    throw new Error(`FakeD1.run: unhandled SQL: ${this.sql}`);
  }
}

export function asD1(db: FakeD1): D1Database {
  return db as unknown as D1Database;
}
