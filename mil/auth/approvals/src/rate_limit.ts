// MIL-66b — per-IP hour-window rate limit for POST /request-access.
//
// Simple SQL pattern: upsert with INSERT OR IGNORE, then UPDATE
// count = count+1. Two round-trips, not atomic — two concurrent
// requests from the same IP in the same window could both see
// count=N and both end up writing count=N+1. For an abuse-guard
// this is acceptable (the limit is approximate, not cryptographic).

export interface RateLimitConfig {
  maxPerWindow: number;
  windowFormat: "hour"; // kept as an enum for future "day" support
}

export const DEFAULT_RATE_LIMIT: RateLimitConfig = {
  maxPerWindow: 5,
  windowFormat: "hour",
};

export function windowKey(now: Date, format: "hour" = "hour"): string {
  void format; // only one option today
  const y = now.getUTCFullYear().toString().padStart(4, "0");
  const m = (now.getUTCMonth() + 1).toString().padStart(2, "0");
  const d = now.getUTCDate().toString().padStart(2, "0");
  const h = now.getUTCHours().toString().padStart(2, "0");
  return `${y}-${m}-${d}T${h}`;
}

// Returns true if the request is allowed, false if rate-limited.
// Caller passes an already-hashed ip (so this module doesn't need
// the daily salt). Absent ip_hash (IP couldn't be determined) —
// allow the request rather than blocking; we don't want to deny
// service on a Cloudflare header quirk.
export async function checkAndIncrement(
  db: D1Database,
  ipHash: string | undefined | null,
  now: Date = new Date(),
  cfg: RateLimitConfig = DEFAULT_RATE_LIMIT,
): Promise<boolean> {
  if (!ipHash) return true;
  const win = windowKey(now, cfg.windowFormat);

  await db
    .prepare(
      "INSERT OR IGNORE INTO signup_rate_limit (ip_hash, window, count) VALUES (?, ?, 0)",
    )
    .bind(ipHash, win)
    .run();

  const row = await db
    .prepare(
      "SELECT count FROM signup_rate_limit WHERE ip_hash = ? AND window = ?",
    )
    .bind(ipHash, win)
    .first<{ count: number }>();
  const current = row?.count ?? 0;

  if (current >= cfg.maxPerWindow) {
    return false;
  }

  await db
    .prepare(
      "UPDATE signup_rate_limit SET count = count + 1 WHERE ip_hash = ? AND window = ?",
    )
    .bind(ipHash, win)
    .run();
  return true;
}
