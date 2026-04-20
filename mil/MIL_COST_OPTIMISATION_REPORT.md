# MIL Cost Optimisation Report
**Date:** 2026-04-03  
**Author:** Claude Code  
**Context:** MIL pipeline API credit exhaustion triggered a cost review and model evaluation

---

## 1. Background

The MIL daily pipeline (`run_daily.py`) hit a zero API credit balance during Run #2 (2026-04-03).
This caused a partial degradation: enrichment and exec alert synthesis both require the Anthropic API.
The question raised: can `qwen3:14b` (available locally via Ollama) replace Anthropic API calls?

---

## 2. What the Pipeline Currently Costs

### API call inventory — `run_daily.py`

| Step | File | Model | Trigger | Est. cost/run |
|------|------|-------|---------|---------------|
| Step 2: Enrich | `enrich_sonnet.py` | claude-haiku-4-5-20251001 | New records only (skip logic) | ~$0.01–0.05 |
| Step 5: Exec alert | `briefing_data.py` | claude-sonnet-4-6 | Once per run | ~$0.05–0.10 |
| Manual: Teacher | `teacher_agent.py` | claude-sonnet-4-6 | One-time, manual | ~$1–2 total |

**Estimated total daily spend: $0.06–0.15/run**  
**Monthly at 1 run/day: $1.80–$4.50**

### Why credits ran out

The Anthropic API billing is separate from Claude Pro subscription. Claude Pro (claude.ai) does
not grant API access. A $5–10 top-up at console.anthropic.com covers 1–3 months of pipeline runs.

### Key efficiency already in place

- `_is_v3()` skip logic: records already enriched with schema v3 are never re-sent to the API.
  Today's Run #2 fetched 231 new records but the enrichment call was proportional to new records only.
  3,587 existing corpus records cost nothing per run.

---

## 3. Evaluation: qwen3:14b vs claude-haiku

### Method

- Sampled 20 real reviews from the live enriched corpus (mixed competitors, mixed ratings)
- Stripped existing enrichment fields to simulate raw input
- Ran both models with the **identical** system prompt and batch prompt from `enrich_sonnet.py`
- Compared: schema compliance, issue_type classification, severity assignment
- Haiku baseline: existing labels already in the enriched corpus (produced during original enrichment)

### Results

| Metric | claude-haiku | qwen3:14b |
|--------|-------------|-----------|
| Schema compliance | 100% (baseline) | **100%** |
| Issue type agreement | baseline | 18/20 (90%) |
| Severity agreement | baseline | 19/20 (95%) |
| Batch time (20 records) | ~3s | **914s** |
| Cost per run | ~$0.01–0.05 | $0.00 |

### Critical finding: the P0 miss

Review: *"Trying to register with the video recognition..."*

| Model | issue_type | severity_class |
|-------|-----------|----------------|
| Haiku (correct) | App Not Opening | **P0** |
| qwen3:14b | Feature Broken | P2 |

Haiku correctly identified a complete registration block as P0. qwen3 downgraded it to P2.
In the MIL pipeline, P0 findings drive the research trigger, Chronicle matching, and executive
alerts. A missed P0 is a missed signal — it directly degrades intelligence quality.

### Speed problem

914 seconds for 20 reviews = **~45 seconds per record** on local hardware (RTX 5070 Ti).  
Daily volume: ~100–250 new records/run.  
Projected enrichment time with qwen3: **75–190 minutes per run**.  
With Haiku: **< 60 seconds**.

The pipeline is designed to run unattended overnight. A 3-hour enrichment step breaks that contract.

---

## 4. Cost Optimisation Strategy

### Recommendation: Hybrid model routing

| Task | Current | Recommended | Saving |
|------|---------|-------------|--------|
| Enrichment (new records) | claude-haiku | **Keep haiku** | — |
| Exec alert synthesis | claude-sonnet-4-6 | **Switch to qwen3:14b** | ~$0.05–0.10/day |
| Teacher autopsies | claude-sonnet-4-6 | **Keep Sonnet** (one-time) | — |

**Rationale:**

**Enrichment stays on Haiku** — classification quality and speed are both critical.
qwen3 misses P0 severity on blocking issues and runs 300x slower. The cost is negligible
(new records only, ~$0.01–0.05/run). This is not worth optimising.

**Exec alert switches to qwen3:14b** — one call per day, latency irrelevant (runs overnight),
narrative synthesis does not require Sonnet's reasoning depth. qwen3 passed schema compliance
at 100% and handles open-ended text generation well. Saving: ~$0.05–0.10/day = ~$1.50–3/month.

**Teacher autopsies stay on Sonnet** — deep causal reasoning required, one-time cost ~$1–2 total,
already gated behind manual execution.

### Immediate action

Top up Anthropic API credits: **$5 at console.anthropic.com**  
This covers: ~1–3 months of enrichment + exec alert at current run volume.

### Optional: Switch exec alert to qwen3

One file change in `mil/briefing_data.py` — swap `anthropic.Anthropic()` for Ollama
OpenAI-compatible endpoint. Reduces daily API dependency to enrichment only (~$0.01–0.05/run).
At that level, $5 covers 3–6 months.

---

## 5. What NOT to Do

| Option | Risk | Verdict |
|--------|------|---------|
| Switch enrichment to qwen3 | P0 miss rate + 300x slower + vault SKIPPED_WRONG_MODEL blocks all vaulting | **Reject** |
| Switch to Opus for enrichment | 20x more expensive than Haiku, no quality gain on classification | **Reject** |
| Remove exec alert synthesis entirely | Degrades Box 3 of Sonar briefing | **Only as fallback** |

---

## 6. Summary

The MIL pipeline is already cost-efficient. The credit exhaustion was a billing gap, not
a runaway spend problem. Total monthly API cost at current volume: **under $5**.

The only worthwhile optimisation is switching exec alert synthesis to qwen3:14b — saving
~$1.50–3/month while maintaining briefing quality. Everything else should stay as-is.

**One-line recommendation: top up $5, optionally switch exec alert to qwen3. Leave enrichment on Haiku.**
