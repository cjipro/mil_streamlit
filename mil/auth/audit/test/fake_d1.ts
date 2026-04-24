// Minimal in-memory D1 fake — just enough to exercise logAuthEvent
// and verifyChain. Only supports the handful of statements our lib
// actually issues.
//
// Not a general-purpose SQL engine; matches raw query strings.

import type { AuthEventRow } from "../src/types";

interface SaltRow {
  date: string;
  salt: string;
}

export class FakeD1 {
  public events: AuthEventRow[] = [];
  public salts: SaltRow[] = [];
  public nextId = 1;

  prepare(sql: string): FakeStatement {
    return new FakeStatement(this, sql, []);
  }

  async batch<T = unknown>(stmts: FakeStatement[]): Promise<{ results?: T[] }[]> {
    const out: { results?: T[] }[] = [];
    for (const s of stmts) out.push(await s._run());
    return out;
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
    const res = await this._run<T>();
    return res.results?.[0] ?? null;
  }

  async all<T = unknown>(): Promise<{ results?: T[] }> {
    return this._run<T>();
  }

  async run(): Promise<{ results?: unknown[] }> {
    return this._run();
  }

  async _run<T = unknown>(): Promise<{ results?: T[] }> {
    const s = this.sql.trim();

    if (s.startsWith("INSERT OR IGNORE INTO audit_salts")) {
      const [date, salt] = this.args as [string, string];
      if (!this.db.salts.find((r) => r.date === date)) {
        this.db.salts.push({ date, salt });
      }
      return { results: [] };
    }

    if (s.startsWith("SELECT salt FROM audit_salts")) {
      const [date] = this.args as [string];
      const row = this.db.salts.find((r) => r.date === date);
      return { results: row ? ([{ salt: row.salt }] as T[]) : [] };
    }

    if (s.startsWith("SELECT row_hash FROM auth_events")) {
      const last = this.db.events[this.db.events.length - 1];
      return { results: last ? ([{ row_hash: last.row_hash }] as T[]) : [] };
    }

    if (s.startsWith("INSERT INTO auth_events")) {
      const row: AuthEventRow = {
        id: this.db.nextId++,
        ts: this.args[0] as string,
        worker: this.args[1] as string,
        event_type: this.args[2] as string,
        method: (this.args[3] as string | null) ?? null,
        host: (this.args[4] as string | null) ?? null,
        path: (this.args[5] as string | null) ?? null,
        enforce: (this.args[6] as number | null) ?? null,
        user_hash: (this.args[7] as string | null) ?? null,
        ip_hash: (this.args[8] as string | null) ?? null,
        ua_hash: (this.args[9] as string | null) ?? null,
        country: (this.args[10] as string | null) ?? null,
        reason: (this.args[11] as string | null) ?? null,
        detail: (this.args[12] as string | null) ?? null,
        prev_hash: this.args[13] as string,
        row_hash: this.args[14] as string,
      };
      this.db.events.push(row);
      return { results: [] };
    }

    if (s.startsWith("SELECT * FROM auth_events")) {
      return { results: [...this.db.events] as T[] };
    }

    throw new Error(`FakeD1: unhandled SQL: ${this.sql}`);
  }
}

// Cast to the real D1Database type at the call site — FakeD1 matches
// enough of the surface area for our lib's calls, and TypeScript
// happily accepts the cast because we only use the subset we emulate.
export function asD1(db: FakeD1): D1Database {
  return db as unknown as D1Database;
}
