# MIL-51 — URL-filter vendor categorisation submissions

Forward-looking insurance for partner reachability. The actual
Barclays block on 2026-04-23 was the Cloudflare Access redirect chain
(phishing-pattern signature), not URL category. That has been
removed. But corp proxies at HSBC / Lloyds / NatWest may still serve
`cjipro.com` as `Uncategorized` or `Newly Observed Domain` until each
upstream URL-filter vendor classifies it. This ticket pre-empts that.

## Status snapshot

| Vendor              | Submitted | Outcome                    |
|---------------------|-----------|----------------------------|
| Cisco Talos         | 2026-04-23 | Submitted, awaiting review |
| Zscaler             | —         | **TODO**                   |
| Palo Alto Networks  | —         | **TODO**                   |
| Forcepoint          | —         | **TODO**                   |
| Symantec / Broadcom | —         | **TODO**                   |

## What we are claiming

`cjipro.com` is the public site of an independent UK market-intelligence
publisher. The public surface (homepage, privacy notice, security.txt,
briefings, sitemap) is open to all — no auth, no ad-tech, no
user-generated content, no AI assistant, no payment processing, no
software download. Trust signals are in place: UK GDPR privacy notice
at `/privacy/`, RFC 9116 `/.well-known/security.txt`, working
`hello@cjipro.com` contact, Cloudflare-fronted GitHub Pages hosting.

Target category in vendor taxonomy (any of these, in order of
preference):
1. **Business and Economy** / **Business / Information**
2. **Computers and Internet** / **Information Technology**
3. **Reference / News and Media** (acceptable fallback)

Categories to actively avoid being placed in:
- `Newly Observed Domain` / `Uncategorized` (default block at most banks)
- `Phishing` / `Suspicious` (the historic Access-redirect-chain
  trigger; now resolved at our end)
- `AI Tools` / `Generative AI` (Barclays and several other UK banks
  block this category outright; the public surface does not host an
  AI tool — Reckoner / Sonar / Pulse are private to alpha partners)
- `Personal Sites and Blogs` (under-categorises us)

## Pre-filled submission copy

Paste this verbatim into the "reason" / "additional context" field of
each vendor form. Adjust the bracketed phrasing per-vendor where the
form asks for the requested category in vendor-specific words.

```
cjipro.com is the public site of CJI, an independent UK-based
market-intelligence publisher serving regulated consumer-service
firms (UK retail banking is the first sector covered). The site
publishes a daily voice-of-customer briefing built from public
signals only — app-store reviews, outage reports, and public
discussion. Public-surface pages (/, /privacy/, /security/,
/.well-known/security.txt, /sitemap.xml, /briefing-v[1-4]) are
open to all visitors with no authentication and no
user-generated content. There is no ad-tech, no AI tool exposed
on the public surface, no payment processing, no downloadable
software. The site is hosted on GitHub Pages behind Cloudflare.
Trust signals: a UK GDPR-compliant privacy notice at /privacy/
identifying the data controller; an RFC 9116 security.txt at
/.well-known/security.txt; a working contact at
hello@cjipro.com.

Requesting categorisation as [Business and Economy] or
[Computers and Internet / Information Technology]. The site
should not be classified as Uncategorized, Newly Observed
Domain, AI Tools, or Personal Blog.
```

## Vendor steps

### 1. Zscaler

- **Portal:** https://csrtool.zscaler.com/submissions
  (Zscaler Cloud Security — "Submit a URL for Categorization").
- **Account:** Free Zscaler account required. Sign up at
  https://help.zscaler.com/ if you don't already have one
  (Zscaler-managed, not the company's ZIA tenant).
- **Steps:**
  1. Sign in to the CSR tool.
  2. URL: `https://cjipro.com/`.
  3. Existing category will likely show as `Miscellaneous or
     Unknown`. Request re-categorisation.
  4. Suggested category: **Business / Information**.
  5. Paste the pre-filled copy block above into the comments
     field.
  6. Submit.
- **SLA:** Typically 1–3 business days. Outcome arrives by email.
- **Verify after acceptance:** Re-check via
  https://urlcategorization.zscaler.com/ — the public lookup
  should reflect the new category within ~24h of the email.

### 2. Palo Alto Networks (PAN-DB)

- **Portal:** https://urlfiltering.paloaltonetworks.com/
  ("Test A Site" → look up `cjipro.com` → click
  **Request Re-categorization** link on the result page).
- **Account:** No account required for the lookup; the request
  form takes a contact email.
- **Steps:**
  1. Open the lookup page, enter `cjipro.com`, run the test.
  2. Existing category will show. If anything other than
     `business-and-economy` or `computer-and-internet-info`,
     click **Request Change**.
  3. Suggested category: **business-and-economy**
     (computer-and-internet-info acceptable fallback).
  4. Paste the pre-filled copy block above into the
     justification field.
  5. Email: `hello@cjipro.com` (so any follow-up is reachable).
  6. Submit.
- **SLA:** Typically 3–5 business days. Outcome arrives by email
  to the address you provided.
- **Verify after acceptance:** Re-run the lookup at the same
  URL — category should reflect the change.

### 3. Forcepoint

- **Portal:** https://csi.forcepoint.com/  → tab **Web**
  → enter URL → results page has a **Suggest a different
  category** link.
- **Account:** No account required for lookup or submission.
- **Steps:**
  1. Run the lookup on `https://cjipro.com/`.
  2. Existing category will show (Forcepoint taxonomy uses
     names like `Business and Economy`, `Information Technology`,
     `Newsgroups`, etc.).
  3. If existing category is `Uncategorized` or anything that
     could trigger a corp-proxy block, click **Suggest**.
  4. Suggested category: **Business and Economy** (primary) or
     **Information Technology** (fallback).
  5. Paste the pre-filled copy block above into the comments
     field.
  6. Contact email: `hello@cjipro.com`.
  7. Submit.
- **SLA:** 5–10 business days (Forcepoint is the slowest of the
  four).
- **Verify after acceptance:** Re-run the same lookup.

### 4. Symantec / Broadcom (Site Review, formerly Bluecoat)

- **Portal:** https://sitereview.bluecoat.com/
  ("WebPulse Site Review" — Broadcom maintains the Bluecoat
  brand on this tool).
- **Account:** Free Broadcom Symantec ID required for submitting
  re-categorisation. Sign up via the link on the site review
  page.
- **Steps:**
  1. Sign in.
  2. Enter `https://cjipro.com/` in the lookup.
  3. Existing category will show (Symantec taxonomy uses names
     like `Business/Economy`, `Technology/Internet`,
     `Reference`, `Newly Registered Website`, etc.).
  4. Click **Request Review** on the result.
  5. Suggested category: **Business/Economy** (primary) or
     **Technology/Internet** (fallback).
  6. Paste the pre-filled copy block above into the comments
     field.
  7. Submit.
- **SLA:** 2–4 business days.
- **Verify after acceptance:** Re-run the lookup.

## Logging

After each submission, append a row to this table at the top of this
file (Status snapshot) with the date submitted. After each acceptance,
update Outcome to `Accepted as <category>`. Keep the original
submission email (Zscaler, Palo Alto) or screenshot (Forcepoint,
Symantec) in case re-submission is needed.

## What done looks like

All five vendors (Talos + the four above) showing `cjipro.com` in a
business / IT category in their public lookup tools. At that point
MIL-51 closes; the matrix in MIL-62 (corp-proxy reachability test
across Barclays / HSBC / Lloyds / NatWest) can run with one
fewer category-related variable.

## If a vendor rejects

- **Reason: insufficient content.** Add to the form: "The
  briefing pages at /briefing, /briefing-v2, /briefing-v3, and
  /briefing-v4 are public and demonstrate the substantive
  content; please review those pages directly." Re-submit.
- **Reason: AI tool.** This means the reviewer landed on
  `sonar.cjipro.com` (Ask CJI Pro). State explicitly: "The
  cjipro.com public surface does not host an AI tool. The chat
  product is on a separate subdomain and is not part of this
  re-categorisation request." Re-submit with URL `https://cjipro.com/`
  exactly (not the bare apex, not the subdomain).
- **Reason: newly registered.** Ask the reviewer to look at the
  WHOIS / Wayback record (cjipro.com has been resolving since
  early 2026) and at the GitHub Pages commit history of
  `cjipro/mil-briefing` for content tenure evidence.
