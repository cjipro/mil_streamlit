// Minimal D1 fake — just the SELECT pattern the approvals lib uses.

interface ApprovedUserRow {
  email: string;
  approved_at: string;
  approved_by: string;
  note: string | null;
}

export class FakeD1 {
  public users: ApprovedUserRow[] = [];

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
    const s = this.sql.trim();
    if (s.startsWith("SELECT 1 AS present FROM approved_users")) {
      const email = this.args[0] as string;
      const hit = this.db.users.find((u) => u.email === email);
      return hit ? ({ present: 1 } as T) : null;
    }
    throw new Error(`FakeD1: unhandled SQL: ${this.sql}`);
  }
}

export function asD1(db: FakeD1): D1Database {
  return db as unknown as D1Database;
}
