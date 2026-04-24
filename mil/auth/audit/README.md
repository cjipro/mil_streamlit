# MIL-65 — Immutable Auth Event Audit Log

Shared library that both `edge-bouncer` and `magic-link` Workers call to
record auth events into a single, append-only, hash-chained D1 table.

## What this buys us

- **Single timeline** of every auth decision: who attempted login, which
  route the bouncer decided on, which callbacks succeeded or failed.
- **Tamper-evidence**: each row's `row_hash` covers its content + the
  prior row's `row_hash`. Any mutation, deletion, or reorder fails
  verification.
- **PII minimisation by construction**: IPs, user agents, and JWT subs
  never land in the table in raw form — only `sha256(value || daily_salt)`
  hashes. Salts rotate per UTC day.

Phase 1 scope. Not signed bundles, not a cryptographic notary. Good
enough to detect in-repo tampering and to power incident review.

## Event taxonomy

| Worker         | event_type                    | Emitted from             |
|----------------|-------------------------------|--------------------------|
| edge-bouncer   | `bouncer.pass.public`         | public allowlist hit     |
| edge-bouncer   | `bouncer.pass.session`        | valid JWT cookie         |
| edge-bouncer   | `bouncer.redirect.missing`    | no cookie present        |
| edge-bouncer   | `bouncer.redirect.invalid`    | JWT present but failed   |
| magic-link     | `magic_link.authorize`        | GET /                    |
| magic-link     | `magic_link.callback.success` | GET /callback (happy)    |
| magic-link     | `magic_link.callback.error`   | GET /callback (failure)  |
| magic-link     | `magic_link.logout`           | GET /logout              |

## Schema

See `schema.sql`. Two tables:

- `auth_events(id, ts, worker, event_type, method, host, path, enforce,
  user_hash, ip_hash, ua_hash, country, reason, detail, prev_hash, row_hash)`
- `audit_salts(date, salt)` — one 32-byte random salt per UTC day,
  written on first use, immutable thereafter.

Invariants are documented in-line in `schema.sql` and enforced in
application code (no `UPDATE`, no `DELETE` — ever).

## Deploy

One-time, from either Worker directory:

```bash
# 1. Create the D1 database (run ONCE — do not re-run from the other Worker dir).
npx wrangler d1 create mil-auth-audit

# 2. Apply schema.
npx wrangler d1 execute mil-auth-audit --remote --file ../audit/schema.sql

# 3. Paste the returned database_id into BOTH wrangler.toml files
#    (edge_bouncer/ and magic_link/) and uncomment the [[d1_databases]]
#    block in each. They MUST share one database_id — the chain is
#    global across both Workers.

# 4. Redeploy both Workers.
( cd ../edge_bouncer && npx wrangler deploy )
( cd ../magic_link   && npx wrangler deploy )
```

Rollback: re-comment both `[[d1_databases]]` blocks and redeploy.
Both Workers no-op audit writes when `env.AUDIT_DB` is undefined;
auth itself keeps flowing.

## Verifying the chain

Dump rows and pipe them through the verifier:

```bash
npx wrangler d1 execute mil-auth-audit --remote --json \
  --command "SELECT * FROM auth_events ORDER BY id ASC" \
  | node --experimental-strip-types src/verify_cli.ts
```

Output is JSON. Exit 0 on clean chain; exit 1 if any row_hash mismatch,
chain-break, or genesis-missing violation is detected.

Run this on a cadence (e.g. weekly + after any incident). A scheduled
agent is the natural home for it — see project routines.

## PII & retention

- **Hashed, never raw**: IP, UA, JWT sub all hash through
  `sha256(value || daily_salt)` before insertion. Daily salts make
  cross-day user correlation require access to every day's salt row.
- **Retention**: Phase 1 is "forever". No automatic purge. If a subject
  access or erasure request ever lands, it's answered by proving the
  hash is not reversible — we never stored the raw value. The daily
  salt itself is the most sensitive row in the database; protect it
  the same way you protect any Cloudflare API token.
- **Cross-border**: D1 data is stored in Cloudflare's primary region.
  Re-check the region contract before onboarding a partner that has
  data-locality requirements; MIL-65's scope is the audit log itself,
  not placement.

## Operational notes

- Writes are fired via `ctx.waitUntil(...)` so they never block the
  user-facing response. A D1 outage degrades to "events lost this
  window" but auth keeps working.
- Two Workers racing to insert can briefly produce two rows with the
  same `prev_hash`. The verifier surfaces this as a `chain-break` —
  a true observation, not a bug. At current traffic this is rare; if
  it becomes common, promote chain writes to a Durable Object (Phase 2).
- The hash chain covers columns that participate in `HASHED_COLUMNS`
  (see `src/types.ts`). If the schema ever grows a new column, update
  that list and migrate old rows out of the verifier's scope with a
  `CHAIN_RESET` marker row (not implemented Phase 1 — file a ticket
  before adding columns).

## File layout

```
mil/auth/audit/
├── README.md              # you are here
├── schema.sql             # D1 DDL + invariants
├── package.json
├── tsconfig.json
├── src/
│   ├── types.ts           # AuthEventType enum, row shape, HASHED_COLUMNS
│   ├── hash.ts            # sha256Hex, canonicalJson, hashRow, recomputeRowHash
│   ├── salt.ts            # utcDateString, d1SaltStore
│   ├── audit.ts           # logAuthEvent (the entry point), extractJwtSub
│   ├── verify.ts          # verifyChain
│   └── verify_cli.ts      # Node CLI around verify.ts
└── test/
    ├── fake_d1.ts         # in-memory D1 fake
    ├── hash.test.ts
    ├── audit.test.ts
    └── verify.test.ts
```

Both Workers import from this directory via relative paths
(`../../audit/src/audit`). esbuild (wrangler's bundler) inlines the
referenced files into each Worker's deployed bundle — no npm
linkage, no monorepo machinery.
