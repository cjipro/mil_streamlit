# Token Audit — Diagnostic Results

**Generated:** 2026-04-28T10:00Z  
**Recommendation:** INSUFFICIENT DATA

---

## Sessions Analysed

| Metric | Value |
|---|---|
| Session records found | 1 (`s1` — session_start only) |
| Per-turn records found | 0 |
| Session-summary records found | 0 |

## Computed Metrics

| Metric | Value |
|---|---|
| Turn-2 cache hit rate | — (no turn data) |
| Avg cache hit rate (turn 2+) | — (no turn data) |
| Session hook SHA256 distinct values | 1 (`4bbc62b7…`) — stable but only 1 data point |
| Avg $/session | — (no turn data) |

## Decision Matrix Outcome

**INSUFFICIENT DATA** — `ops/token_audit.jsonl` contains only the baseline `session_start` record for `s1`. No per-turn token counts were appended during actual working sessions after the diagnostic was set up on 2026-04-25.

## Recommendation

Extend the measurement window. After the next 1–2 working sessions, append per-turn records to `ops/token_audit.jsonl` using the format in `ops/token_audit_helper.md`:

```json
{"ts": "...", "session_id": "s2", "turn": 1, "input_tokens": X, "cache_read_input_tokens": Y, "cache_creation_input_tokens": Z, "output_tokens": W, "notes": ""}
{"ts": "...", "session_id": "s2", "turn": 2, "input_tokens": X, "cache_read_input_tokens": Y, "cache_creation_input_tokens": Z, "output_tokens": W, "notes": ""}
```

The turn-2 cache hit rate from a single session is sufficient to determine whether CLAUDE.md is being amortized (≥ 80% → STOP; < 80% → investigate prefix invalidator). The diagnostic does not need 5 full sessions — one session with at least 2 turns answered is enough.

**Do not slim CLAUDE.md until at least one session with ≥ 2 per-turn records is measured.**
