// MIL-65 — chain verifier.
//
// Walks auth_events ordered by id and checks:
//   (a) each row's stored row_hash == recomputeRowHash(row)
//   (b) each row's prev_hash == prior row's row_hash
//       (first row must have prev_hash == "genesis")
//
// Returns a structured report. Does NOT throw on violations — the
// caller decides whether to exit non-zero (verify_cli.ts does).

import { recomputeRowHash } from "./hash";
import type { AuthEventRow } from "./types";

export type Violation =
  | { kind: "row-hash-mismatch"; id: number; expected: string; actual: string }
  | { kind: "chain-break"; id: number; expected_prev: string; actual_prev: string }
  | { kind: "genesis-missing"; id: number; actual_prev: string };

export interface VerifyReport {
  total_rows: number;
  violations: Violation[];
  last_id: number | null;
  last_row_hash: string | null;
}

export interface RowReader {
  // Must return rows in ascending id order.
  all(): Promise<AuthEventRow[]>;
}

export function d1RowReader(db: D1Database): RowReader {
  return {
    async all(): Promise<AuthEventRow[]> {
      const res = await db
        .prepare("SELECT * FROM auth_events ORDER BY id ASC")
        .all<AuthEventRow>();
      return res.results ?? [];
    },
  };
}

export async function verifyChain(reader: RowReader): Promise<VerifyReport> {
  const rows = await reader.all();
  const violations: Violation[] = [];
  let expected_prev = "genesis";
  let last_row_hash: string | null = null;
  let last_id: number | null = null;

  for (const row of rows) {
    if (row.prev_hash !== expected_prev) {
      if (expected_prev === "genesis") {
        violations.push({
          kind: "genesis-missing",
          id: row.id,
          actual_prev: row.prev_hash,
        });
      } else {
        violations.push({
          kind: "chain-break",
          id: row.id,
          expected_prev,
          actual_prev: row.prev_hash,
        });
      }
    }
    const recomputed = await recomputeRowHash(row);
    if (recomputed !== row.row_hash) {
      violations.push({
        kind: "row-hash-mismatch",
        id: row.id,
        expected: recomputed,
        actual: row.row_hash,
      });
    }
    expected_prev = row.row_hash;
    last_row_hash = row.row_hash;
    last_id = row.id;
  }

  return {
    total_rows: rows.length,
    violations,
    last_id,
    last_row_hash,
  };
}
