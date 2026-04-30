# Runbook

Day-to-day operations, common failure modes, and recovery patterns. For first-time setup see [`GETTING_STARTED.md`](GETTING_STARTED.md). For internals see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Daily pipeline at a glance

| Step | Component | Critical? | Notes |
|---|---|---|---|
| 1 | Fetch | yes | App Store + Google Play, paginated dedup |
| 2 | Enrich | yes | Sonnet 4.6 default; subdivide-on-failure safety net |
| 3 | Inference | yes | CAC + CHRONICLE-anchored RAG |
| 4a | Research trigger | no | Weak-anchor findings → `research_queue.jsonl` |
| 4b | Vault | no | TCP preflight on port 9871 — skipped if HDFS unreachable |
| 4c | Clark escalation | yes | Runs before publish so V1–V4 see the same tier |
| 4d | Benchmark | yes | 90-day rolling; populates `benchmark_history` |
| 4e | Analytics DB | yes | Full rebuild of `mil_analytics.db` |
| 4f | Drift monitor | no | Silent Wall detector; HIGH escalates via Slack |
| 5 | Publish V1 | yes | Box 1 source — V2/V3/V4 read this HTML |
| 5b | Publish V2 | yes | Vane chart, Inference Cards, Clark, Phase 2 demand |
| 5c | Publish V3 | yes | Intelligence Brief, Commentary, Benchmarks |
| 5d | Publish V4 | yes | Jinja2 + FCA Provenance Chain |
| 5e | Publish Sonar | no | Per-firm `/sonar/{slug}/[date]/` |
| 6 | Log | yes | `daily_run_log.jsonl` + Slack heartbeat |
| 8 | Partner email | no | CLEAN runs only, silent-day guard on weak signal |

A run is **CLEAN** if all critical steps pass, **PARTIAL** if any non-critical step fails, **FAILED** if any critical step fails.

---

## Invocation forms

```bash
py run_daily.py                    # full pipeline
py run_daily.py --dry-run          # fetch + enrich only
py run_daily.py --skip-fetch       # re-run inference + publish on existing data
py run_daily.py --step 5d          # isolated step (no side-effects)
py run_daily.py --step 4,4d,5d     # subset of steps
```

`--step` skips heartbeat, run-log, summary, and partner-email side-effects. Use it freely for hot-fixes — it does not pollute the streak counter or trigger partner sends.

---

## Common failure modes

### HDFS NameNode not reachable (Step 4b)

Symptom: `[vault] HDFS NameNode unreachable on port 9871 — skipping vault step`. Run continues as PARTIAL.

Cause: Docker stack down, or DataNode not yet registered after restart.

Recovery:
```bash
docker-compose up -d mil-namenode mil-datanode
# wait ~30 seconds for DataNode registration
py run_daily.py --step 4b           # vault only
```

If 403 errors appear during vault PUT after a Docker restart, the DataNode hostname rewrite (`mil-datanode:9864 → localhost:9864`) in `mil/storage/hdfs_client.py` handles it on the second attempt.

### `ENRICHMENT_FAILED` records

Symptom: Run row shows `enrichment_failed: N > 0`.

Cause: Provider rate-limit, transient JSON parse failure, or batch-level model refusal.

Recovery: nothing required — these records are re-attempted on every subsequent run. The subdivide-on-failure path in `mil/harvester/enrich_sonnet.py` halves a failing batch recursively to size 1, so true failures are rare. Persistent ENRICHMENT_FAILED on a specific record usually indicates a content-policy refusal at the provider; inspect the raw text and the failing record id in the run log.

### Inference produces zero new findings

Symptom: `findings: 0` in the run log, but `new_records > 0`.

Possible causes:
- All new records below severity gate (P2 only — the P0 cluster minimum is 2)
- All new records below CAC cluster threshold
- CHRONICLE anchor below `sim_threshold` (cosine 0.30)

Diagnostic:
```bash
duckdb mil_analytics.db
> SELECT * FROM unanchored_signals ORDER BY ts DESC LIMIT 20;
```

If unanchored_signals is growing, the corpus is producing patterns the CHRONICLE ledger does not cover — open a CHRONICLE proposal cycle (see below).

### Briefing publish writes but Box 1 is stale

Symptom: V2/V3/V4 render but Box 1 quotes/sentiment show yesterday's data on a fresh run.

Cause: V1 publish failed silently. V2/V3/V4 read V1's `output/index.html` and patch sections on top — if V1 didn't publish, downstream renderers anchor on stale HTML.

Recovery:
```bash
py run_daily.py --step 5            # V1 only
# inspect mil/publish/output/index.html for fresh Box 1 content
py run_daily.py --step 5b,5c,5d,5e  # cascade downstream
```

### Slack webhook not pinging

Symptom: Pipeline completes but no heartbeat appears in Slack.

Diagnostic: check `SLACK_WEBHOOK_URL` is set in `.env`, then test directly:
```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"smoke test"}' "$SLACK_WEBHOOK_URL"
```

If the URL has been rotated, update `.env` — the notifier resolves `${SLACK_WEBHOOK_URL}` via env-var expansion and never bakes the URL into config.

### Daily run streak resets to zero

Symptom: `streak: 0/5` in the run row even though yesterday's run was CLEAN.

Cause: A second invocation overwrote the streak in the same UTC day, or a cloud/cron environment ran without the necessary credentials and logged a FAILED run.

Diagnostic:
```bash
tail -50 mil/data/daily_run_log.jsonl | jq -r '"\(.run) \(.date) \(.status) \(.failed_steps // [])"'
```

If a cloud-cron is firing in addition to the local Task Scheduler, disable it — the engine is not reentrant in cloud environments without HDFS / Ollama / `GITHUB_TOKEN` access.

---

## CHRONICLE governance cycle

When inference produces unanchored P0/P1 findings, the research agent drafts proposed CHRONICLE entries:

```bash
py mil/researcher/research_agent.py
py mil/researcher/research_agent.py --competitor barclays
py mil/researcher/research_agent.py --force        # bypass CHR_COVERAGE skip
```

Output: `mil/data/chr_proposals/{competitor}_{journey}_{ts}.md` plus a summary file. The agent calls Opus (governance tier) to draft the proposed entry — quality bar is high because CHRONICLE entries anchor the CAC formula permanently.

Hussain (or the maintainer) reviews each proposal against the verification standard in [`CHRONICLE_POLICY.md`](CHRONICLE_POLICY.md), then either appends an approved entry to `mil/CHRONICLE.md` or returns the proposal for additional sourcing.

---

## Cadences

| Cadence | What | Trigger |
|---|---|---|
| Daily 06:30 UTC | Full pipeline | Task Scheduler / cron |
| Weekly Friday | CHRONICLE review | Maintainer manually opens proposal queue |
| Fortnightly | Calibration retrospective | Append to `mil/data/calibration_notes.md` — check 3 prior Clark findings against observable outcomes |
| Monthly | Enrichment spot-check | `py mil/tests/enrichment_spot_check.py --sample 50` then label and `--score` |
| Monthly | Cost audit | Inspect token-usage logs in pipeline INFO output; flip enrichment provider if drift |

The fortnightly calibration is the load-bearing one — it is how the engine stays honest. A finding that called CLARK-2 fourteen days ago should be retrospectively scorable: did the predicted journey actually degrade, or was it a false positive? Log both and recalibrate.

---

## Recovering from a bad run

The pipeline is idempotent on its inputs — re-running it on the same day with the same data produces the same output. To recover from a bad run:

1. Identify which step failed (run log `failed_steps` array).
2. Fix the underlying cause (HDFS, API key, config typo, etc.).
3. Re-run the failed step in isolation: `py run_daily.py --step {id}`.
4. If downstream steps depend on the fix, cascade: `--step 4,4d,5d`.
5. If the run log itself is wrong, edit `mil/data/daily_run_log.jsonl` directly — it is append-only by convention but not by enforcement, and the streak counter reads the last N rows.

For full re-publish without re-fetching:
```bash
py run_daily.py --skip-fetch
```

---

## What never to do

- **Do not amend existing CHRONICLE entries.** Append-only is constitutional. Fix-by-amendment in the source is a violation of Article Zero — the failure ledger is the audit trail.
- **Do not bypass the verifier.** The Sonar PDB email's Haiku verifier and the Reckoner ask-mode verifier are not optional. If a verifier fails repeatedly, fix the upstream prompt, do not relax the check.
- **Do not paraphrase customer quotes.** Verbatim is constitutional. The verifier enforces this against generated prose.
- **Do not commit `.env`.** Credentials never enter git. The reference instance's `.env` is gitignored and `.gitignore` enforces it.
- **Do not import internal modules from `mil/`.** Zero Entanglement is a hard build-validator failure, not a warning.

---

## When in doubt

Read `mil/SOVEREIGN_BRIEF.md` — it is the constitutional charter and resolves most ambiguity about scope, masking, and what counts as a publishable finding.
