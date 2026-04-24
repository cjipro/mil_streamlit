// MIL-65 — hashing primitives.
//
// Uses the Web Crypto API (available in Cloudflare Workers, Node 20+,
// and browsers). Returns lowercase hex so D1 TEXT columns stay stable.

import { HASHED_COLUMNS, type AuthEventRow } from "./types";

export async function sha256Hex(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return bufToHex(digest);
}

function bufToHex(buf: ArrayBuffer): string {
  const view = new Uint8Array(buf);
  let out = "";
  for (let i = 0; i < view.length; i++) {
    out += view[i].toString(16).padStart(2, "0");
  }
  return out;
}

// Canonical JSON — keys sorted lexicographically, no whitespace.
// Values that are not plain data (functions, undefined) throw.
//
// We deliberately DO NOT use JSON.stringify's second-arg replacer
// trick because it re-emits in insertion order on older engines;
// explicit sort is unambiguous across runtimes.
export function canonicalJson(obj: Record<string, unknown>): string {
  const keys = Object.keys(obj).sort();
  const parts = keys.map((k) => {
    const v = obj[k];
    return JSON.stringify(k) + ":" + canonicalValue(v);
  });
  return "{" + parts.join(",") + "}";
}

function canonicalValue(v: unknown): string {
  if (v === null) return "null";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) {
      throw new Error(`non-finite number in audit payload: ${v}`);
    }
    return JSON.stringify(v);
  }
  if (typeof v === "string" || typeof v === "boolean") {
    return JSON.stringify(v);
  }
  if (typeof v === "object") {
    // We only expect plain records in audit rows — no arrays, no nested
    // objects. Catch anything else loudly rather than silently
    // stringifying as "[object Object]".
    if (Array.isArray(v)) {
      throw new Error("arrays not permitted in audit payload");
    }
    return canonicalJson(v as Record<string, unknown>);
  }
  throw new Error(`unsupported value type in audit payload: ${typeof v}`);
}

// Compute row_hash for a content record.
// content must contain every HASHED_COLUMNS key (NULLs pass through
// as `null`). prevHash is the row_hash of the prior row, or the
// literal string "genesis" for the first row.
export async function hashRow(
  content: Record<string, unknown>,
  prevHash: string,
): Promise<string> {
  const filtered: Record<string, unknown> = {};
  for (const col of HASHED_COLUMNS) {
    filtered[col] = col in content ? content[col] : null;
  }
  return sha256Hex(canonicalJson(filtered) + "|" + prevHash);
}

// Recompute row_hash for a stored row. Used by the verifier.
export async function recomputeRowHash(row: AuthEventRow): Promise<string> {
  const content: Record<string, unknown> = {};
  for (const col of HASHED_COLUMNS) {
    content[col] = row[col as keyof AuthEventRow] ?? null;
  }
  return hashRow(content, row.prev_hash);
}
