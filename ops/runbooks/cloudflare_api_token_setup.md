# Cloudflare API token setup (one-time, ~3 min)

## Why this exists

The in-session Cloudflare MCP server (`mcp__plugin_cloudflare_cloudflare-api`)
authenticates via OAuth and grants a deliberately narrow scope —
DNS read works, Workers Scripts:Edit works, but DNS:Edit and
Email Routing:Edit return `Authentication error: 10000`. To
execute Cloudflare changes from this session without falling back
to the dashboard, generate a Cloudflare API Token with broader
scope and store it in `.env`. From then on `py ops/cloudflare/cf.py`
runs against that token.

The token replaces ad-hoc dashboard clicks for DNS edits, Email
Routing rules, Workers route bindings, and cache purges. Anything
the wrapper doesn't cover, extend `ops/cloudflare/cf.py` instead of
clicking.

## Generate the token

1. Cloudflare dashboard → top-right user menu → **My Profile** → **API Tokens**.
2. **Create Token** → **Custom token** → **Get started**.
3. Configure:
   - **Token name:** `cjipro-mil-cli`
   - **Permissions** (click **+ Add more** between rows):

     | Resource | Permission                  | Level |
     |----------|-----------------------------|-------|
     | Zone     | Zone                        | Read  |
     | Zone     | Zone Settings               | Read  |
     | Zone     | DNS                         | Edit  |
     | Zone     | Email Routing Rules         | Edit  |
     | Zone     | Workers Routes              | Edit  |
     | Zone     | Cache Purge                 | Purge |
     | Account  | Email Routing Addresses     | Edit  |
     | Account  | Workers Scripts             | Edit  |

   - **Zone Resources:** Include — Specific zone — `cjipro.com`
   - **Account Resources:** Include — All accounts (or specific to
     `Hussain.marketing@gmail.com's Account` — id
     `01814bfa785073150141d0901e41b8df`)
   - **Client IP Address Filtering:** leave blank.
   - **TTL:** Start date today. End date 1 year from today (or
     leave open if you prefer).
4. **Continue to summary** → review → **Create Token**.
5. **Copy the token immediately.** Cloudflare shows it once.
   Format: ~40 characters of base64-ish text.

## Install the token

Edit `C:\Users\hussa\while-sleeping\.env` (gitignored — already
holds SMTP creds, GITHUB_TOKEN, etc.) and add:

```
CLOUDFLARE_API_TOKEN=<paste-token-here>
```

Save. No quotes needed; the wrapper strips them either way.

## Verify

From the repo root:

```bash
py ops/cloudflare/cf.py zone-info
```

Expected output:

```
name:    cjipro.com
id:      0da15aa946c4c4e74584371147b934a1
status:  active
plan:    Free Website
ns:      <name servers>
```

If you see `error: CLOUDFLARE_API_TOKEN not set` — the token didn't
land in `.env`. If you see `Authentication error 10000` — the
permissions weren't all granted at token creation time; revoke the
token and create a new one with the full table above.

## What the wrapper exposes today

```bash
# Read
py ops/cloudflare/cf.py zone-info
py ops/cloudflare/cf.py dns-list
py ops/cloudflare/cf.py email-route-list

# DNS write
py ops/cloudflare/cf.py dns-add --type AAAA --name app --content 100:: --proxied --comment "MIL-82 reservation"
py ops/cloudflare/cf.py dns-delete <record-id-from-dns-list>

# Email Routing write
py ops/cloudflare/cf.py email-route-add security hussain.marketing@gmail.com
py ops/cloudflare/cf.py email-route-delete <rule-id>

# Cache + Workers
py ops/cloudflare/cf.py cache-purge --urls https://cjipro.com/ https://cjipro.com/insights/
py ops/cloudflare/cf.py worker-route-add "app.cjipro.com/*" --service app-cjipro
```

## Extend the wrapper

When a new Cloudflare op comes up, add a subcommand to
`ops/cloudflare/cf.py` rather than clicking the dashboard. The
wrapper is stdlib-only, ~250 lines, and extending it is one
function plus an argparse subparser. The discipline matters because
"this is a one-off" is how dashboard-state and code-state diverge.

## Rotate / revoke

Cloudflare dashboard → My Profile → API Tokens → find
`cjipro-mil-cli` → **Roll** (rotate) or **Delete** (revoke). After
rotate, paste the new value over the old one in `.env`.

If a token is exposed (committed by mistake, posted in a chat,
suspected leak), revoke immediately, rotate, and `git log -p .env*`
to confirm it never reached a tracked file.
