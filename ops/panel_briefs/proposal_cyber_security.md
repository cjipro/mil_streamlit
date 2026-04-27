# app.cjipro.com/engineering — Cyber Security Brief

**Opening principle:** Immutable audit from day one; never claimed beyond what's verifiable in code.

---

## 1. Immutable Audit Chain (MIL-65)

**Philosophy:** Every auth decision — login attempt, allow, deny, logout — records to an append-only log with hash-chain tamper evidence. No UPDATE, no DELETE ever.

**Falsifiable claim:** `mil/auth/audit/schema.sql` enforces NOT NULL on `prev_hash` and `row_hash`; `verify_cli.ts` detects reorder/mutation with sha256 chain. Run weekly.

**Drill-down:** `mil/auth/audit/README.md` — deploy procedure, event taxonomy, verification runbook.

---

## 2. Cookie-as-Code Contract (MIL-64)

**Philosophy:** Session cookie attributes are machine-enforced invariants, not aspirational. Name, flags, domain — all locked in code. Drift between magic-link issuer and edge-bouncer validator will break auth.

**Falsifiable claim:** `mil/auth/magic_link/src/cookie_spec.ts` enforces `__Secure-cjipro-session`, HttpOnly, SameSite=Lax, Max-Age from env. Test file validates against spec document.

**Drill-down:** `mil/auth/COOKIE_SPEC.md` — attribute requirements, change procedure, changelog.

---

## 3. Magic-Link State Guard (MIL-61)

**Philosophy:** OAuth state parameter is HMAC-signed with 10-minute TTL and return_to allowlist. Rejects replayed stale states, open-redirect attacks, CSRF.

**Falsifiable claim:** `mil/auth/magic_link/src/state.ts` implements constant-time HMAC compare; `isValidReturnTo` rejects `https://`, `//`, `../`, empty.

**Drill-down:** `mil/auth/magic_link/README.md` — security decisions table, smoke-test procedures.

---

## 4. Forward-Detection (MIL-146)

**Philosophy:** Session issued at IP /24 + UA family baseline. On next use, if both differ, audit-tag (not block). Detects concurrent-access red flags without false-positive denials.

**Falsifiable claim:** `mil/auth/magic_link/src/callback.ts` compares IP /24 prefix and UA family; emits `forward_use` event to audit log with non-blocking status.

**Drill-down:** `mil/auth/magic_link/src/callback.ts` — forwarded-use detection block; audit schema includes `bouncer.forward_use` event type.

---

## 5. Differentiated Deny States (MIL-153)

**Philosophy:** Non-approved user gets one of three deny pages, never a generic 403. In-queue (has pending signup), not-on-allowlist (never requested), or invalid JWT. Each surfaces different remediation to the user.

**Falsifiable claim:** `mil/auth/edge_bouncer/src/index.ts` routes to three separate HTML pages based on state; `hasPendingRequest()` queries the pending_signups table before deciding which denial.

**Drill-down:** Edge Bouncer README — routing table for all four decision paths (public, valid session, in-queue, not-approved).

---

## 6. SCIM Auto-Deprovision with Opt-In Approval (MIL-71)

**Philosophy:** When partner removes user from IdP, WorkOS fires `dsync.user.deleted`; we revoke + force-signout with no admin lag. New user provisioning is audit-only by default (org must opt-in to auto-approve to prevent compromised-IdP attack).

**Falsifiable claim:** `mil/auth/approvals/src/auto_approve.ts` checks `auto_approve_orgs` allowlist before granting access; every org starts in deny-unless-opted-in state. Deprovisioning always fires regardless.

**Drill-down:** `mil/auth/MIL71_SCIM.md` — per-org setup, auto-approve safety threat model, backfill procedure.

---

## 7. Per-Tenant Audit Export with Hash Recompute (MIL-72)

**Philosophy:** Partners' SOC teams pull their own auth events from our audit log, scoped to their organization ID. Endpoint re-hashes sensitive columns with stored salts to prove integrity before handing over to partner.

**Falsifiable claim:** `mil/auth/approvals/src/audit_export.ts` rebuilds user_hash, ip_hash, ua_hash for every row before materialization; partners cannot cross-correlate users across orgs.

**Drill-down:** `mil/auth/MIL72_AUDIT_EXPORT.md` — endpoint spec, dashboard usage, integration with SIEM, curl examples.

---

## Section to CUT: "Security Governance Framework"

A generic "security posture, controls governance, compliance roadmap" page reads as aspirational to this audience. **Drop it.** Your CISO has heard that pitch from every vendor. What survives audit review is:

- Immutable evidence (audit log) you can replay
- Code-enforced invariants (cookie spec, return_to allowlist)
- Deployment runbooks that don't require trust

A governance *narrative* without falsifiable implementation signals risk.

---

## Non-Obvious Claim (Bank CISO Will Notice)

**Firm-slug routing guarded against compromised WorkOS org (MIL-152):**

Even if an attacker compromises your partner's WorkOS account, they cannot spoof firm context. `firm_slug` and `firm_name` are **admin-set only** in the database; users can confirm their own role and contact details but cannot touch firm fields. This blocks a class of attack — compromised IdP + malicious user provisioning → self-assigning rival firm context → accessing competitor briefings.

Smaller vendors often delegate firm assignment to the partner's IdP. You don't.

---

## The One Sentence That Earns Trust or Distrust at First Scan

**"SOC 2 readiness assessment underway; no attestation in this version."**

Or the lie: *"SOC 2 in progress."* (Different meaning to auditors — "in progress" implies a pending attestation report. "Readiness" is honest.) This is the AICPA-verifiability rule. Never claim a control you don't have.

---

## Trade-Off Note

**Refresh-token rotation (MIL-74) deferred.** Current posture: 1-hour access-token TTL + ~10-minute JWT exp is tighter than typical enterprise (4h / 24h), but it's still a drift to flag with the bank's security review board. You chose not to implement server-side session rotation in v1 because the cost (Durable Object state machine) outweighed the benefit (a few minutes of refresh window). Honest tradeoff. A different vendor might claim they have rotation; you admit the gap. Banks notice.

---

*Last reviewed: 2026-04-27. No SOC 2 attestation held. No pen test on alpha surface. DPIA REG-001..004 open (Pulse-side, not MIL public scope).*
