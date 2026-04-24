// MIL-65 — audit chain verifier CLI.
//
// Reads rows as JSON from stdin (or a file), runs verifyChain, prints
// a report, and exits non-zero if any violations were found.
//
// Usage:
//   # From the repo root, dump rows and pipe in:
//   wrangler d1 execute AUDIT_DB --remote --json \
//     --command "SELECT * FROM auth_events ORDER BY id ASC" \
//     | node --experimental-strip-types mil/auth/audit/src/verify_cli.ts
//
//   # Or from a file:
//   node --experimental-strip-types mil/auth/audit/src/verify_cli.ts rows.json

import { readFileSync } from "node:fs";
import { verifyChain, type RowReader } from "./verify";
import type { AuthEventRow } from "./types";

function readInput(argv: string[]): string {
  const fileArg = argv.slice(2)[0];
  if (fileArg) return readFileSync(fileArg, "utf8");
  return readFileSync(0, "utf8"); // fd 0 == stdin
}

function parseRows(raw: string): AuthEventRow[] {
  const parsed = JSON.parse(raw);
  // `wrangler d1 execute --json` wraps results under
  // [{ results: [...], success: true, meta: {...} }]. Accept both
  // shapes so the CLI is kind to operators.
  if (Array.isArray(parsed) && parsed.length > 0 && "results" in parsed[0]) {
    return parsed[0].results as AuthEventRow[];
  }
  if (Array.isArray(parsed)) return parsed as AuthEventRow[];
  throw new Error("input is not a JSON array of rows or a wrangler d1 result");
}

async function main(): Promise<void> {
  const raw = readInput(process.argv);
  const rows = parseRows(raw);
  const reader: RowReader = { all: async () => rows };
  const report = await verifyChain(reader);

  console.log(
    JSON.stringify(
      {
        total_rows: report.total_rows,
        violation_count: report.violations.length,
        last_id: report.last_id,
        last_row_hash: report.last_row_hash,
        violations: report.violations,
      },
      null,
      2,
    ),
  );

  if (report.violations.length > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
