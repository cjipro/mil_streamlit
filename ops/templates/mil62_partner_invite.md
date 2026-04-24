# MIL-62 — Alpha tester invitation email template

Use this when asking an alpha partner contact at a bank to run the
corp-proxy test matrix on their work laptop. Customise the three
`{{PLACEHOLDER}}` fields before sending. Keep the overall length
short — partners are doing you a favour, respect their inbox.

One email per bank. Send only after:

- [ ] `ops/runbooks/mil-62_corp_proxy_matrix.md` pre-flight smoke
      passes from your own network.
- [ ] MIL-61 edge-bouncer has accumulated ≥24h of clean shadow-mode
      decision logs (per the Sunday 2026-04-26 agent's go/no-go).
- [ ] `ENFORCE=true` flip has happened — otherwise S3/S6/S7 can't
      fully be tested (briefings serve without gating, partner sees
      no redirect).

---

**Subject:** A small favour — can you test one sign-in flow on your work laptop?

**Body:**

Hi {{FIRST_NAME}},

Would you have ~15 minutes in the next few days to help test a
sign-in flow from your {{BANK_NAME}} laptop? It'd massively de-risk
the alpha rollout and catch any proxy / network issues before I
invite the wider group.

**What you'd do:**

1. Open a fresh InPrivate / Incognito window on your work laptop
   (not a VPN'd personal device — the corp network is the whole
   point of the test).
2. Go to `https://cjipro.com/briefing-v4/`. If you land on the
   briefing directly, good. If you get redirected to a sign-in
   page, enter your work email when prompted.
3. Check your work inbox (junk folder too) for a sign-in link
   email. Click the link from the same corp browser.
4. Confirm you land back on the briefing page.
5. Reply to this email with:
   - Any step where something unexpected happened (proxy block
     page, broken redirect, email didn't arrive, etc.)
   - A screenshot if anything looks wrong
   - Or just "all clean" if the flow worked end-to-end

**What you will NOT be asked to do:**

- Share any passwords or credentials.
- Install anything.
- Bypass any corp security.

The whole point is to confirm our sign-in flow plays nicely with
{{BANK_NAME}}'s network controls. If something blocks, that tells
me what to fix, not you.

If you want a structured runbook to follow instead of the above
narrative, grab `ops/mil62_smoke.ps1` (PowerShell, no install
required) from me and run it — it automates the public-reachability
checks and tells you exactly what to do for the browser steps.

Happy to jump on a 5-minute call before / during if that's
easier.

Thanks,
Hussain

---

## Reviewer checklist (before sending)

- [ ] `{{FIRST_NAME}}` replaced
- [ ] `{{BANK_NAME}}` replaced (both occurrences)
- [ ] Subject matches the body's tone (informal, small ask)
- [ ] No mention of FCA, regulatory, or compliance in the body —
      this is an engineering-test favour, not a compliance exercise.
      Regulated framing goes into the formal alpha onboarding
      document, not the first-test invitation.
- [ ] No internal codes (CLARK, P0/P1/P2, CHR-NNN, MIL-XX) in the
      reader-facing text.

## Follow-up (after response)

1. Fill the partner's results row into
   `ops/runbooks/mil-62_corp_proxy_matrix.md` using either the
   `mil62_smoke.sh/.ps1` output or the reply text.
2. If any scenario failed, open a follow-up task (not a MIL-62
   blocker if only cosmetic; hard block if S1/S3/S6 fail — those
   mean the product literally doesn't reach the partner).
3. Once ≥3 of 4 banks have passed all scenarios, MIL-62 is cleared
   and the alpha invite cohort can go out for real.
