# Cyber Security — Summary Table Proposal Verdict

## Verdict
**SUPPORT** — A fast-scan grid surfaces the immutability + code-enforced-contract posture instantly. Bank CISO reads "hash-chained audit" and "cookie-as-code" in 5 seconds; it's a credibility signal, not marketing.

---

## Security Discipline Row

| Discipline | Strengths | Pipeline | Ideal world |
|---|---|---|---|
| **Security** | Hash-chained immutable audit log (MIL-65). Cookie & state enforced in code (MIL-64, MIL-61). | MIL-74: refresh-token rotation (Durable Object state machine). MIL-72: audit export with hash recompute. | Formal pen test on alpha surface; SOC 2 Type 1 attestation in-house. |

**Strengths cell:** `mil/auth/audit/schema.sql` enforces NOT NULL on hash columns; `mil/auth/magic_link/src/cookie_spec.ts` locks cookie name, flags, domain in TypeScript. Both ship in production and are verifiable in GitHub today.

**Pipeline cell:** MIL-74 is a real backlog item with a specific blocker (Durable Object cost/benefit). MIL-72 is committed work on audit export (falsifiable: endpoint recomputes hashes). Both point to live tickets, not aspirational.

**Ideal world cell:** Pen test and SOC 2 Type 1 are specific, bounded controls — not "better security posture". Both are gated by real constraints (audit selection + budget for pen test; auditor selection for SOC 2). No AICPA overclaim.

---

## One Concern

**Risk:** The Ideal world cell tempts SOC 2 + pen test *claims* that don't exist today. A bank CISO skims the table and assumes the row means "we're attesting SOC 2 readiness." It doesn't. The row must carry a footer caveat: "No attestations held; Ideal world = what would require additional investment." Without it, the table overstates compliance posture.

---

## One Refinement

**Add a legend row or hyperlink note below the four-discipline table:**

"Click Strengths links for GitHub code. Click Pipeline links for Jira ticket + decision logic. Ideal world is future commitment, not current claim. No SOC 2 attestation, no pen test results in this version."

This closes the loop: the bank's compliance reviewer cannot misread the Security row as an attestation. The table is *honest speed*, not *marketing speed*.

---

**Word count: 186**
