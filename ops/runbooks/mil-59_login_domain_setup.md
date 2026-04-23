# MIL-59 — login.cjipro.com placeholder setup

Runbook for Hussain (Cloudflare dashboard work). Claude wrote the HTML
(`mil/publish/login_site/index.html`); the deploy wiring is below.

## What this accomplishes

1. `login.cjipro.com` resolves with valid TLS and serves a branded
   "coming soon" page.
2. The domain starts aging in corporate-proxy "Newly Observed Domain"
   classifiers now, so by the time real auth traffic lands (MIL-63),
   the corp-proxy test matrix (MIL-62) has the best possible shot at
   passing cleanly.
3. MIL-60 (WorkOS custom-domain mapping) can then point at this same
   host without racing DNS.

## Recommended path: Cloudflare Pages project

Fastest to stand up. Retired later when MIL-61 Worker takes over the
routing.

### Step 1 — create the Pages project

Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** →
**Connect to Git**

- Repo: `cjipro/mil_streamlit`
- Production branch: `main`
- Build command: *(empty — static HTML)*
- Build output directory: `mil/publish/login_site`
- Root directory: *(default)*
- Environment variables: none

Save and deploy. First deploy URL is something like
`login-cji-pro.pages.dev`. Open it to confirm the page renders.

### Step 2 — attach custom domain

Same Pages project → **Custom domains** → **Set up a custom domain** →
enter `login.cjipro.com`.

Cloudflare auto-creates the CNAME record in the cjipro.com zone. Accept
the automatic provisioning.

### Step 3 — verify

- `https://login.cjipro.com/` loads the coming-soon page
- TLS cert valid (Cloudflare issues automatically via ACME)
- Check from a mobile network (off any VPN) to confirm global DNS
  propagation

### Step 4 — record for downstream tickets

Put the Pages project URL (`*.pages.dev` form) somewhere findable —
MIL-60's WorkOS custom-domain setup will want it as a fallback target.

## Alternative path: Cloudflare Worker (static)

Only useful if you want to skip Pages and go straight to MIL-61's
architecture. More setup work for no aging-clock benefit — the clock
starts either way.

If you pick this path instead:

```
wrangler init login-placeholder
# inline the HTML into src/index.ts as a string
# route = login.cjipro.com/*
wrangler deploy
```

MIL-61 will replace it anyway, so it's not recommended for a
placeholder.

## What you are NOT doing in this ticket

- Collecting email addresses — no form yet (MIL-63)
- Accepting magic-link callbacks — no auth logic yet (MIL-61)
- Gating anything else — briefings stay public until MIL-61 ships

## Acceptance

- [ ] Pages project deployed, commit auto-pulls from `main`
- [ ] `login.cjipro.com` resolves with HTTP 200 + the coming-soon page
- [ ] TLS cert valid, no browser warnings
- [ ] Reachable from mobile network (baseline — corp-network tests
      happen in MIL-62 after MIL-61 Worker is live)
- [ ] URL recorded in Jira comment on MIL-60 for pickup

## Updating the page later

Edits to `mil/publish/login_site/index.html` auto-deploy via Pages on
every push to `main`. No extra step.

When MIL-63 makes this the real login page, the same HTML gains:
- an email input field
- a small "check your inbox" confirmation state
- handoff to WorkOS AuthKit for the magic-link email + token exchange

Until then: the page just sits here, ageing nicely.
