# Token Audit — Recording Guide

Purpose: measure whether `CLAUDE.md` size is actually expensive (vs amortized by prompt caching) before slimming. See `C:\Users\hussa\.claude\plans\token-optimzation-quirky-blossom.md` for context.

Append all records to `ops/token_audit.jsonl` (one JSON object per line).

---

## Per-session-start record

Append once at the start of every fresh Claude Code session you measure.

```json
{"ts": "2026-04-25T03:16:00Z", "session_id": "s1", "event": "session_start", "claude_md_bytes": 126663, "session_hook_bytes": 12126, "session_hook_sha256": "<sha256 hex>"}
```

Get the values with:

```bash
# CLAUDE.md size
stat -c '%s' C:/Users/hussa/while-sleeping/CLAUDE.md

# Most-recent SessionStart hook payload (bytes + SHA256)
ls -lt "C:/Users/hussa/.claude/projects/C--Users-hussa-while-sleeping/"*/tool-results/hook-*-additionalContext.txt | head -1
sha256sum "<that file>"
```

Karpathy's question this answers: does the hook payload differ across sessions? If `session_hook_sha256` is the same across `s1`...`s5`, the hook is a stable cacheable prefix. If it changes every session, every fresh session pays a cache-write premium for ~12KB.

---

## Per-turn record

Append after every Claude response. Pull the four numbers from the response's `usage` block (visible in Claude Code's status / debug, or via `/cost`).

```json
{"ts": "2026-04-25T03:20:00Z", "session_id": "s1", "turn": 2, "input_tokens": 1234, "cache_read_input_tokens": 28000, "cache_creation_input_tokens": 0, "output_tokens": 567, "notes": ""}
```

`turn` is 1-indexed within the session. `notes` is optional — use it to flag anomalies (e.g., "compaction fired", "switched models").

---

## Per-session-end record

Append once when you end the session. Compute totals + cost.

```json
{
  "session_id": "s1",
  "event": "session_summary",
  "turns": 12,
  "total_input_tokens": 14000,
  "total_cache_read": 350000,
  "total_cache_creation": 30000,
  "total_output_tokens": 8000,
  "estimated_cost_usd": {
    "input_full": 0.0700,
    "cache_write": 0.1875,
    "cache_read": 0.1750,
    "output": 0.2000,
    "total": 0.6325
  }
}
```

### Cost formulas (Opus 4.7, 5-min TTL cache)

| Component | Rate per 1M tokens | Formula |
|---|---|---|
| Uncached input | $5.00 | `total_input_tokens × 5.00 / 1_000_000` |
| Cache write (5-min TTL) | $6.25 (1.25× premium) | `total_cache_creation × 6.25 / 1_000_000` |
| Cache read | $0.50 (0.1× of input) | `total_cache_read × 0.50 / 1_000_000` |
| Output | $25.00 | `total_output_tokens × 25.00 / 1_000_000` |

Sum the four for `total`.

---

## Stopping rule (when to end the diagnostic)

After **session 1**, compute turn-2 cache hit rate:

```
hit_rate_t2 = cache_read_input_tokens(turn 2) /
              (cache_read_input_tokens(turn 2) + input_tokens(turn 2))
```

- **hit_rate_t2 ≥ 0.80** → STOP. Cache is working. CLAUDE.md is amortized after turn 1. The proposed slim won't save much; the real cost driver is elsewhere (probably the SessionStart hook if its SHA differs across sessions). Record the decision in the plan file under "Diagnostic Results" and skip Stage 2.

- **hit_rate_t2 < 0.80** → continue to s2 ... s5. Something is invalidating the prefix. After s5, look for the invalidator (timestamp interpolated into prompt, hook payload changing, etc.) and fix that *before* slimming CLAUDE.md.

Don't ritual-perform 5 sessions if 1 answers the question.

---

## At end of diagnostic

Edit `C:\Users\hussa\.claude\plans\token-optimzation-quirky-blossom.md` and append a `## Diagnostic Results` section with:

- avg `$/session` across all measured sessions
- avg cache hit rate (turn-2 onwards)
- whether `session_hook_sha256` was stable across sessions
- recommended next action (proceed with Stage 2 / pivot to hook tuning / stop — already optimized)

Then decide whether Stage 2 (slim CLAUDE.md + extract STATE.md/CHANGELOG.md) goes ahead.
