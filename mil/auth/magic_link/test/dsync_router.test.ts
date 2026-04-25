import { beforeEach, describe, expect, test } from "vitest";
import { routeDsyncEvent } from "../src/dsync_router";
import type { WorkosEvent } from "../src/webhooks";

// Minimal D1 fake — only handles the SQL the dsync router emits.
// Reused across tests via beforeEach.
class FakeD1 {
  approved: { email: string }[] = [];
  sessions: { sub: string; email: string }[] = [];
  autoApprove: string[] = [];
  prepare(sql: string) {
    return new FakeStmt(this, sql, []);
  }
}

class FakeStmt {
  constructor(private db: FakeD1, private sql: string, private args: unknown[]) {}
  bind(...args: unknown[]) {
    return new FakeStmt(this.db, this.sql, args);
  }
  async first<T = unknown>() {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("SELECT 1 AS present FROM auto_approve_orgs")) {
      const orgId = this.args[0] as string;
      return this.db.autoApprove.includes(orgId)
        ? ({ present: 1 } as T)
        : null;
    }
    if (s.startsWith("SELECT 1 AS present FROM approved_users")) {
      const email = this.args[0] as string;
      return this.db.approved.find((u) => u.email === email)
        ? ({ present: 1 } as T)
        : null;
    }
    return null;
  }
  async run() {
    const s = this.sql.trim().replace(/\s+/g, " ");
    if (s.startsWith("INSERT OR IGNORE INTO approved_users")) {
      const email = this.args[0] as string;
      if (!this.db.approved.find((u) => u.email === email)) {
        this.db.approved.push({ email });
      }
      return { meta: { changes: 1 } };
    }
    if (s.startsWith("DELETE FROM approved_users")) {
      const email = this.args[0] as string;
      const before = this.db.approved.length;
      this.db.approved = this.db.approved.filter((u) => u.email !== email);
      return { meta: { changes: before - this.db.approved.length } };
    }
    if (s.startsWith("DELETE FROM sessions")) {
      const email = this.args[0] as string;
      const before = this.db.sessions.length;
      this.db.sessions = this.db.sessions.filter((s) => s.email !== email);
      return { meta: { changes: before - this.db.sessions.length } };
    }
    return {};
  }
}

const asD1 = (db: FakeD1) => db as unknown as D1Database;

function ev(eventType: string, data: Record<string, unknown>): WorkosEvent {
  return { id: "evt_test", event: eventType, data };
}

let db: FakeD1;
beforeEach(() => {
  db = new FakeD1();
});

describe("routeDsyncEvent — non-dsync events", () => {
  test("returns null for non-dsync event types", async () => {
    const out = await routeDsyncEvent(asD1(db), ev("user.created", {}));
    expect(out).toBeNull();
  });

  test("returns null for authentication events", async () => {
    const out = await routeDsyncEvent(asD1(db), ev("authentication.success", {}));
    expect(out).toBeNull();
  });
});

describe("routeDsyncEvent — dsync.user.created", () => {
  test("auto-approves when org is in auto_approve_orgs", async () => {
    db.autoApprove.push("org_alpha");
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.created", {
        organization_id: "org_alpha",
        user: { email: "Alice@partnerbank.com" },
      }),
    );
    expect(out?.eventType).toBe("dsync.user.auto_approved");
    expect(out?.email).toBe("Alice@partnerbank.com");
    expect(out?.detail).toBe("org_alpha");
    expect(db.approved).toHaveLength(1);
    expect(db.approved[0].email).toBe("alice@partnerbank.com"); // canonicalised
  });

  test("audit-only when org NOT in auto_approve_orgs", async () => {
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.created", {
        organization_id: "org_unknown",
        user: { email: "alice@partnerbank.com" },
      }),
    );
    expect(out?.eventType).toBe("dsync.user.created");
    expect(out?.detail).toBe("pending:org_unknown");
    expect(db.approved).toHaveLength(0); // safety: no auto-approve
  });

  test("audit-only with detail when no email in payload", async () => {
    db.autoApprove.push("org_alpha");
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.created", {
        organization_id: "org_alpha",
        user: { id: "u_x" },
      }),
    );
    expect(out?.eventType).toBe("dsync.user.created");
    expect(out?.detail).toBe("no-email-in-payload");
    expect(db.approved).toHaveLength(0);
  });

  test("extracts email from emails[].value SCIM shape", async () => {
    db.autoApprove.push("org_alpha");
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.created", {
        organization_id: "org_alpha",
        user: { emails: [{ value: "bob@partnerbank.com", primary: true }] },
      }),
    );
    expect(out?.eventType).toBe("dsync.user.auto_approved");
    expect(db.approved[0].email).toBe("bob@partnerbank.com");
  });
});

describe("routeDsyncEvent — dsync.user.deleted", () => {
  test("revokes approval and force-signs-out", async () => {
    db.approved.push({ email: "alice@partnerbank.com" });
    db.sessions.push({ sub: "u_alice", email: "alice@partnerbank.com" });
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.deleted", {
        user: { email: "Alice@partnerbank.com" },
      }),
    );
    expect(out?.eventType).toBe("dsync.user.auto_revoked");
    expect(out?.email).toBe("Alice@partnerbank.com");
    expect(out?.detail).toContain("revoke:ok");
    expect(out?.detail).toContain("signout:ok");
    expect(db.approved).toHaveLength(0);
    expect(db.sessions).toHaveLength(0);
  });

  test("idempotent when user already gone", async () => {
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.deleted", { user: { email: "ghost@partnerbank.com" } }),
    );
    expect(out?.eventType).toBe("dsync.user.auto_revoked");
    expect(out?.detail).toContain("revoke:not-found");
    expect(out?.detail).toContain("signout:not-found");
  });
});

describe("routeDsyncEvent — other dsync.* events", () => {
  test("dsync.user.updated → audit-only", async () => {
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.user.updated", { user: { email: "alice@x.com" } }),
    );
    expect(out?.eventType).toBe("dsync.user.updated");
  });

  test("dsync.group.user_added → typed audit", async () => {
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.group.user_added", {}),
    );
    expect(out?.eventType).toBe("dsync.group.user_added");
  });

  test("unknown dsync.* → returns null (caller falls back to workos.webhook)", async () => {
    const out = await routeDsyncEvent(
      asD1(db),
      ev("dsync.something.weird", {}),
    );
    expect(out).toBeNull();
  });
});
