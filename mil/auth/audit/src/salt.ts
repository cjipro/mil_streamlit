// MIL-65 — daily salt management.
//
// Each UTC day gets a fresh 32-byte random salt. IP / JWT-sub hashes
// are computed as sha256(value || salt) so correlation across days
// requires access to both salts. Salts are immutable once written.
//
// Concurrency: two Workers might both try to create today's salt
// on the first request of the day. INSERT OR IGNORE makes that safe —
// one wins, the other's insert no-ops, and the subsequent SELECT
// returns the salt that actually landed.

export function utcDateString(d: Date): string {
  // YYYY-MM-DD in UTC. Do NOT use toISOString().slice(0,10) inside
  // tests with fake timers because that depends on Date shape; use
  // explicit getters.
  const y = d.getUTCFullYear().toString().padStart(4, "0");
  const m = (d.getUTCMonth() + 1).toString().padStart(2, "0");
  const day = d.getUTCDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function randomSaltHex(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let out = "";
  for (let i = 0; i < bytes.length; i++) {
    out += bytes[i].toString(16).padStart(2, "0");
  }
  return out;
}

export interface SaltStore {
  // INSERT OR IGNORE into audit_salts; returns the salt for that date
  // (either the newly inserted one or the pre-existing one).
  getOrCreate(date: string): Promise<string>;
}

// Production impl backed by D1.
export function d1SaltStore(db: D1Database): SaltStore {
  return {
    async getOrCreate(date: string): Promise<string> {
      const fresh = randomSaltHex();
      // One batched transaction: insert if absent, then read.
      const [, read] = await db.batch<{ salt: string }>([
        db
          .prepare("INSERT OR IGNORE INTO audit_salts (date, salt) VALUES (?, ?)")
          .bind(date, fresh),
        db.prepare("SELECT salt FROM audit_salts WHERE date = ?").bind(date),
      ]);
      const row = read.results?.[0];
      if (!row) {
        // Shouldn't happen — the insert above guarantees a row exists.
        // Fall back to the freshly generated value to avoid throwing
        // on the hot path; the verifier will flag an unchained event
        // if this ever fires in prod.
        return fresh;
      }
      return row.salt;
    },
  };
}
