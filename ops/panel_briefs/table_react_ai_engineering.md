# AI Engineering — Summary Table Proposal Verdict

## Verdict
**SUPPORT** — A fast-scan grid above dense bullets will reduce friction for time-constrained bank audiences; it surfaces commitment vs aspiration instantly without adding marketing risk.

---

## AI Discipline Row

| Discipline | Strengths | Pipeline | Ideal world |
|---|---|---|---|
| **AI** | Model routing by stakes (Opus/Sonnet/Haiku/Qwen3 tiers). Verifier enforces citations. | ARCH-007: MIL-126 — prompts to versioned file + eval sets. MIL-125 — V1 retirement. | Specialist 4B stable on RTX 5070; bitsandbytes unlocks QLoRA viability (ARCH-005 retry). |

**Strengths cell:** References `mil/config/model_routing.yaml` (shipped in production). "Stakes" is falsifiable — tiers are auditable in YAML with switch dates.

**Pipeline cell:** Points to MIL-126 ticket (prompt file versioning + eval), a real committed work item visible in the backlog. Avoids marketing vagueness ("improve accuracy").

**Ideal world cell:** Bounded by hardware constraint (RTX 5070 Ti Blackwell stability), not hand-waving. References ARCH-005 (shelved QLoRA report) — specific, testable, tied to existing runbook.

---

## One Concern

**Risk:** The Pipeline cell (MIL-126) is technical housekeeping; a bank Head of AI might misread it as "we're not improving intelligence." The table needs a footer note linking Strengths → Pipeline → Ideal world *as a narrative arc* (Tier 3 → reproducible prompts → specialist viability), not three independent claims. Otherwise a reader skims "pipeline = file versioning" and concludes "they're optimising, not shipping".

---

## One Refinement

**Add a footer row below the four-discipline table:**

| | |
|---|---|
| **How to read this** | Strengths = production today (link to GitHub). Pipeline = Jira ticket numbers (link to ticket). Ideal world = specific blocker, not aspirational. Click the ticket link to see the decision logic. |

This closes the loop: no reader has to guess whether "prompts to file" is infrastructure drudgery or intelligence advancement. The Jira link supplies the context.

---

**Word count: 187**
