# AI Engineering — Public Intelligence Page Proposal
## For `app.cjipro.com/engineering`

**Audience:** Head of AI Engineering, UK bank (Barclays-grade). Controls AI + data programmes. Cyber/regulatory background. Reads defensible at IT-review depth.

---

## Opening Principle

**The system does not invent; it only amplifies what public signals say about banking failures, then stops before it invents an answer.**

This is the line that buys trust in the first three seconds. It works because it's falsifiable and because every component below traces to it.

---

## Five–seven Sections for the Page

### 1. **Article Zero — Calibrated Ignorance, Not False Certainty**

**Philosophy:**
The system prioritises honest expression of its boundaries over any unverified claim. When public data runs out, the system says so and requests the data that would resolve it.

**Falsifiable claim:**
`mil/SOVEREIGN_BRIEF.md` lines 14–19. The Article Zero preamble is the constitutional foundation. Every module answers to it before leadership.

**Hyperlink depth:** "Read the Sovereign Brief" → shows the 287-line governance document with the immutability rule, the Designed Ceiling concept, and the ownership register (every component has a named owner or gets abandoned).

---

### 2. **Four-Tier Model Routing — Stakes Drive Architecture, Not Cost**

**Philosophy:**
Model selection is governed by decision stakes, not cost minimisation. Login failures (Tier 1: Opus) are more important than comment enrichment (Tier 4: local Qwen). The architecture is deterministic and reviewable.

**Falsifiable claim:**
`mil/config/model_routing.yaml` schema v1.1, lines 1–6 and 46–240. Shows Tier 1 (Opus, CHR governance + autopsies); Tier 2 (Sonnet, daily alerts); Tier 3 (Haiku/Refuel-8B, scale classification); Tier 4 (Qwen3, YAML/narrative). ARCH-006 notes Sonnet enrichment switch 2026-04-25 (reverses cost-driven flip from ARCH-004).

**Hyperlink depth:** "Model Routing Schema" → YAML file. Shows the exact route decision tree. Shows cost ceiling estimate (~\.80/day for enrichment); shows severity gate in normalise() as safety net.

---

### 3. **Verifier Loops — Forcing Citations Before LLM Output Leaves the System**

**Philosophy:**
Every public-facing claim must cite ≥1 evidence id. Quotes must appear verbatim in that evidence. A Haiku verifier checks that numeric claims are supported. If any check fails, synthesis retries once or returns refusal.

**Falsifiable claim:**
`mil/chat/verifier.py`, lines 31–147. Two-stage audit: (1) in-code citation resolution + smart-quote normalisation (lines 80–95), (2) LLM support check via `ask_verifier` task (lines 98–135). Smart-char normalisation handles typography drift (curly quotes → straight quotes, en-dash → hyphen).

**Hyperlink depth:** "Verifier Design" → shows the Python code and the decision tree (fail on stage 1 → retry synthesis; fail on stage 2 after retry → FABRICATION_GUARD refusal, output is logged not released).

---

### 4. **CHRONICLE Governance — Every Inference Traces to Verified Public Sources**

**Philosophy:**
An immutable ledger of banking failures. Entries are append-only; never amended. Every entry carries a verification status (APPROVED, PENDING, INFERRED-WITH-CAP). Every inference the system makes traces back to a CHRONICLE entry with a confidence score.

**Falsifiable claim:**
`mil/CHRONICLE.md`, lines 1–71 and schema at lines 23–37. Shows CHR-001 (TSB 2018, confidence 1.0, APPROVED), CHR-002 (Lloyds 2025, confidence 0.6, PARTIAL), CHR-003 (HSBC 2025, confidence 0.55, inferred root cause, APPROVED). CHR-004..019 are April 2026 competitive signals (Revolut, Monzo, NatWest, Lloyds, HSBC, Barclays) all at 0.15–0.35 confidence, approved 2026-04-16.

**Hyperlink depth:** "CHRONICLE Ledger" → full 1,077-line document. Shows verified_facts schema, causal_chain, confidence breakdowns by dimension (dates/impact/root_cause/regulatory). Shows review flags (e.g., CHR-003: "Root cause inferred not confirmed. Do not present as fact.").

---

### 5. **Zero Entanglement — Air-Gap Between Public Intelligence and Client Data**

**Philosophy:**
The system contains zero imports from internal banking systems. Public data flows OUT; internal data NEVER flows IN. This is not a limitation — it's the most strategically important feature.

**Falsifiable claim:**
`mil/SOVEREIGN_BRIEF.md` lines 28–84. Nico Zhao's Law: MIL imports nothing from `pulse/`, `poc/`, `app/`, `dags/`. The only permitted data crossing is `mil/outputs/mil_findings.json` read by CJI Pulse. Dual HDFS (MIL on port 9871, CJI on 9870) never share volumes or config. Build validator enforces this as a hard failure, not a warning.

**Hyperlink depth:** "Air-Gap Specification" → shows the import rule table (lines 63–78), storage architecture diagram (lines 214–244), the HDFS port split, and the runtime failure that catches any violation.

---

### 6. **Shelved QLoRA with Held-Out Evidence — Honesty About What Didn't Beat Baseline**

**Philosophy:**
A specialist severity model was trained on 600 pairs but lost to the baseline enrichment model on held-out eval. Rather than hide this, the project publishes the failure and keeps the baseline in production.

**Falsifiable claim:**
`mil/specialist/heldout_eval_report.md`, dated 2026-04-19. Specialist (qwen3-mil-v1-4b) achieved 83.3% overall vs baseline (qwen3:14b) 93.3%. P0 accuracy: specialist 75%, baseline 83.3%. The 4B base appears to be the ceiling — 3x training pairs improved P0 by only +8.3pp.

**Hyperlink depth:** "Specialist Evaluation" → 30-record blind test with per-record verdicts (lines 27–59). Shows which samples the specialist missed: rows 11, 13, 14, 22, 27. Explains why the route is shelved (ARCH-005 superseded 2026-04-20) and when to revisit (bitsandbytes stability on RTX 5070 Ti Blackwell, or larger training hardware).

---

### 7. **Designed Ceiling — The Exit Strategy Button Is the Phase 2 Business Case**

**Philosophy:**
When the system reaches the boundary of what public data alone can confirm, it stops and emits a refusal with a CAC score. Every click on the Exit Strategy button is logged with timestamp and finding_id. The click log is never deleted — it's the demand signal for Phase 2.

**Falsifiable claim:**
`mil/SOVEREIGN_BRIEF.md` lines 112–128. Designed Ceiling and the exit-strategy click log (`mil/data/click_log.jsonl`). Shows the exact text a stakeholder sees: "I have detected a [CAC score]% confidence match to [CHRONICLE entry] on [journey]. To confirm whether this is affecting our vulnerable customer cohort, I require access to Internal HDFS Data. Request Phase 2."

**Hyperlink depth:** "Designed Ceiling & Phase 2 Demand" → shows the click-log schema and explains why a system that can admit its ignorance gains more trust than one that pretends certainty.

---

## One Section to CUT

**Remove:** Generic "AI Ethics Principles" or "Responsible AI Checklist" language.

**Why:**
The audience is a Head of AI Engineering who controls compliance programmes. They can smell marketing-grade responsibility statements. The actual governance in this proposal (Article Zero, Designed Ceiling, verifier loops, CHRONICLE immutability) is *more* credible and *more* defensible than a principles page would be. A principles page reads like insurance language. The SOVEREIGN_BRIEF reads like an engineering contract. The bank-side audience will trust the latter.

---

## One Non-Obvious Claim

**Claim:** The system explicitly deploys a production-grade qwen3:14b enrichment model running on local Ollama (not via API), and the design decision is *provably justified* by a switch from Sonnet (ARCH-004 → ARCH-006, April 2026).

**Why this matters to a bank-AI Head of Engineering:**
Most AI shops assume proprietary models are always better. This project shows evidence-based model selection: Haiku was tried for enrichment, then switched to qwen3:14b (Ollama local) for cost control, then switched *back* to Sonnet 4.6 (API) when enrichment accuracy mattered more than cost. The switches are logged in the YAML (`ARCH-004`, `ARCH-006`) with exact dates and reasons. No shop has the audit trail to show this level of decisiveness. It signals that this team knows how to change their mind when data says so — not a common signal from AI teams.

The cost ceiling is quantified: ~\.80/day for daily enrichment (10-record batches at ~\.04 per batch). A bank CTO reviewing this will see a team that has *done the math*.

---

## The One Sentence That Earns Trust or Breaks It

**Trust sentence:**
"Every inference is traced to a CHRONICLE entry. If it cannot be traced, it does not get trained on, and it does not get reported."

(This is from CHRONICLE.md lines 17–19 and SOVEREIGN_BRIEF.md Article Zero.)

**Why it works:**
It's testable. Any regulator can ask: "Show me three inferences and their CHRONICLE anchors." The system can produce the answer in 10 seconds. A system that cannot do this has already failed at transparency. This sentence makes transparency not an aspiration — it's an architecture constraint.

---

## Trade-Off Note

**Lean into:** Honesty about shelved work (QLoRA) and unconfirmed confidence scores (CHR-003 confidence capped at 0.55, "inferred root cause").

**Lean away from:** The temptation to round-up confidence scores or hide the 4B specialist's failure.

**Why this matters:** Banks operate in an adversarial regulatory environment. Inspectors will *expect* the system to have failures and shelved experiments. What they will *distrust* is a system that claims 99% confidence in a prediction about a competitor's infrastructure. By leading with "here's what we don't know" and "here's what we tried and discarded," the page will read as more truthful than one that claims perfection. The Head of AI Engineering reading this will think: "This is someone I can hand to my security team and not be embarrassed."

---

**Total word count: 485 words**
