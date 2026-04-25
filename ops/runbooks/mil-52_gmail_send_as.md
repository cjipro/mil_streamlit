# MIL-52 — Gmail Send-as for hello@cjipro.com + SPF update

The MIL-49 partner-facing PDB email currently goes out from
`hussain.marketing@gmail.com` (the SMTP_USER credential in `.env`),
which is fine for end-to-end mail flow but reads as personal in a
partner inbox. This ticket flips the visible From address to
`hello@cjipro.com` via Gmail Send-as, after extending SPF so Google's
relays are authorised to send for `cjipro.com`.

## Current state (verified 2026-04-25)

- **Inbound:** Cloudflare Email Routing live for `hello@cjipro.com`
  → forwards to `hussain.marketing@gmail.com`. MX + DKIM records
  managed by Cloudflare.
- **SPF:** `v=spf1 include:_spf.mx.cloudflare.net ~all`
  (single TXT record on `cjipro.com` apex; covers Cloudflare-relayed
  forwards only).
- **Outbound (today):** `mil/notify/briefing_email.py` → Gmail SMTP
  (`smtp.gmail.com:587`) via `SMTP_USER` + `SMTP_APP_PASSWORD` →
  message header `From: hussain.marketing@gmail.com`.
- **Outbound (target):** same SMTP path, but visible
  `From: CJI <hello@cjipro.com>` after Send-as configuration +
  SPF extension. Reply-To and Return-Path align so partner replies
  reach the same forwarding chain.

## What "done" looks like

A test email sent by `briefing_email.py` from the project box,
arriving at a partner-class inbox (e.g.
`hussain.x.ahmed@barclays.com`), with all of:
- Visible `From: CJI <hello@cjipro.com>`
- Authentication-Results: `spf=pass`, `dkim=pass`, `dmarc=pass`
  (or `dmarc=none` if no DMARC record yet — both are deliverable)
- Reply to the message arrives back in `hussain.marketing@gmail.com`
  via the Cloudflare → Gmail forwarding chain

## Step A — Extend SPF in Cloudflare DNS

The SPF record on `cjipro.com` apex must list every relay that may
emit mail with a `cjipro.com` envelope sender. Today it lists
Cloudflare only; we add Google.

1. Cloudflare dashboard → `cjipro.com` zone → DNS → Records.
2. Find the existing TXT record:
   ```
   Name:    cjipro.com
   Type:    TXT
   Content: v=spf1 include:_spf.mx.cloudflare.net ~all
   ```
3. Edit. Replace Content with:
   ```
   v=spf1 include:_spf.mx.cloudflare.net include:_spf.google.com ~all
   ```
4. TTL: Auto.
5. Save.

**Why these mechanisms and this order:**
- `_spf.mx.cloudflare.net` covers any forward-on-resend that
  Cloudflare Email Routing may emit (e.g. NDRs, forwarded replies).
- `_spf.google.com` covers Gmail SMTP relays that Send-as uses
  when `From: hello@cjipro.com` is set — Google rewrites the
  envelope sender to a `cjipro.com` address, so SPF must permit
  Google's outbound IPs.
- `~all` (soft-fail) keeps deliverability tolerant during the
  cutover. Tighten to `-all` only after 7+ days of clean DMARC
  reports.

**SPF lookup-count check** (the 10-DNS-lookup limit): the new
record costs 2 lookups (Cloudflare include + Google include).
Well under the limit. No flattening required.

**Propagation:** typically 5 minutes for Cloudflare; verify via
`Resolve-DnsName -Type TXT cjipro.com` (Windows) before moving on.

## Step B — Configure Gmail Send-as

1. Sign in to Gmail as `hussain.marketing@gmail.com` (the account
   that already receives Cloudflare's forwards from
   `hello@cjipro.com`).
2. Settings (gear icon) → See all settings → **Accounts and
   Import** tab.
3. **Send mail as:** click **Add another email address**.
4. Dialog 1:
   - Name: `CJI`
   - Email address: `hello@cjipro.com`
   - **Untick "Treat as an alias."** (Treating as alias rewrites
     the From header to your Gmail address on replies — defeats
     the entire point of this ticket. Hold the line on this.)
   - Click Next Step.
5. Dialog 2 (SMTP relay):
   - SMTP Server: `smtp.gmail.com`
   - Port: `587`
   - Username: `hussain.marketing@gmail.com`
   - Password: same Gmail App Password used in `.env` as
     `SMTP_APP_PASSWORD` (16-character app password, NOT your
     real Gmail password). If you don't have one, generate at
     https://myaccount.google.com/apppasswords.
   - Secured connection using TLS (default).
   - Click **Add Account**.
6. Gmail sends a verification email to `hello@cjipro.com`. That
   email lands in `hussain.marketing@gmail.com` via Cloudflare
   forwarding. Click the verification link inside.
7. Back in Settings → Accounts and Import → **Send mail as**:
   - You should now see two entries: `hussain.marketing@gmail.com`
     (default) and `CJI <hello@cjipro.com>` (verified).
   - Optional: change **default** to `CJI <hello@cjipro.com>` if
     you want all new outbound to use this address by default. Not
     required for `briefing_email.py` (it sets From explicitly).
   - Set **When replying to a message** to **Reply from the same
     address the message was sent to**.

## Step C — Update `.env` so briefing_email.py uses the new From

`mil/notify/briefing_email.py` reads `SMTP_FROM` and falls back to
`SMTP_USER`. Today `SMTP_FROM` is unset, so messages go from the
Gmail address. Set `SMTP_FROM` so headers carry the new address.

Edit `C:\Users\hussa\while-sleeping\.env` (the project root one,
not committed) — add or update:
```
SMTP_FROM=CJI <hello@cjipro.com>
```
Leave `SMTP_USER` and `SMTP_APP_PASSWORD` as-is (still
`hussain.marketing@gmail.com` and the app password — these are
the SMTP authentication creds, not the visible From).

Why the `Name <addr>` format: Gmail SMTP relays accept the
RFC 5322 display-name format and clients render the friendly
name. Without it, partners see `hello@cjipro.com` only, which
is fine but reads colder.

## Step D — Verify

Run a low-stakes test:
```
py -m mil.notify.briefing_email --ignore-status --clear-cache
```

(`--ignore-status` lets it fire on a non-CLEAN day; `--clear-cache`
forces a fresh lede generation if you want to see end-to-end.)

Check the resulting message in the recipient's inbox (the
distribution.yaml list — currently
`hussain.x.ahmed@barclays.com`). Open the headers (Gmail: ⋮ →
Show original; Outlook: File → Properties).

Required values:
- `From: CJI <hello@cjipro.com>` — display
- `Return-Path: <hussain.marketing@gmail.com>` — Gmail's envelope
  sender after relay (this is correct; SPF passes on Google's IPs)
- `Authentication-Results: ... spf=pass smtp.mailfrom=...gmail.com`
  — SPF check on the Return-Path domain, which is gmail.com,
  passes via Google's own SPF
- `dkim=pass header.d=gmail.com` — Gmail signs with its own
  domain key; this is fine and partners' filters accept it
- (Optional) `dmarc=none` — we have no DMARC record yet; that's
  acceptable. Adding one is **out of scope** for MIL-52; track
  separately if/when partner deliverability needs it.

If `From:` still shows `hussain.marketing@gmail.com`:
- The Send-as alias was added but `briefing_email.py` is not
  emitting the `From:` header you expect. Re-check `SMTP_FROM`
  in `.env` and that the process re-read environment after
  edit.

If `From:` shows `hello@cjipro.com` but the message lands in
spam:
- The most likely cause is SPF still propagating, or the
  recipient's domain has DMARC `p=reject` and our lack of DMARC
  + DKIM-cjipro alignment trips it. Send a second test 30 min
  later. If still in spam after SPF clearly resolves, file a
  deliverability follow-up ticket — DMARC + DKIM-cjipro signing
  is a deeper config (out of MIL-52 scope; would land via
  Cloudflare DKIM + a `cjipro.com` DMARC TXT record).

## Step E — Reply-flow sanity check

Send a reply to the test message from the recipient's inbox.
The reply should:
1. Address `CJI <hello@cjipro.com>`.
2. Land at Cloudflare Email Routing for `hello@cjipro.com`.
3. Forward to `hussain.marketing@gmail.com`.
4. Appear threaded under the original sent message in Gmail.

If the reply does not arrive, the Cloudflare forwarding rule
for `hello@cjipro.com` is the place to check (Cloudflare
dashboard → Email → Email Routing → Routes).

## Backout

If Send-as breaks an active partner thread mid-test:
1. Comment out / remove `SMTP_FROM` from `.env` →
   `briefing_email.py` reverts to sending from
   `hussain.marketing@gmail.com`.
2. Leave the SPF and Gmail Send-as alias in place — they don't
   harm anything passive.
3. Re-fire when ready.

The SPF change is conservative (additive, both `~all`); no
backout planned.

## Once verified

- Update CLAUDE.md MIL-52 row to BUILT with date + headers
  inspected.
- Close the ticket in Jira UI.
- Future-proof: add a one-line note in `mil/notify/briefing_email.py`
  docstring stating the From address comes from `SMTP_FROM` and
  expects the alias to be live.
