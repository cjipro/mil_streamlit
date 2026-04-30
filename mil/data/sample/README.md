# Sample corpus

100 synthetic enriched review records across six retail-banking subjects and two store sources. Used to bootstrap a fork without requiring a live LLM key for first-run enrichment, or to give CI a deterministic input for end-to-end pipeline tests.

## Contents

| File | Subject | Source | Records |
|---|---|---|---|
| `app_store_barclays_enriched.json` | barclays | App Store | 14 |
| `app_store_natwest_enriched.json` | natwest | App Store | 10 |
| `app_store_lloyds_enriched.json` | lloyds | App Store | 8 |
| `app_store_hsbc_enriched.json` | hsbc | App Store | 6 |
| `app_store_monzo_enriched.json` | monzo | App Store | 6 |
| `app_store_revolut_enriched.json` | revolut | App Store | 6 |
| `google_play_*_enriched.json` | (same 6) | Google Play | 50 total |

Total: 100 records, 50 App Store + 50 Google Play, weighted toward the default subject (Barclays) so Box 1/2/3 have something to render.

## What's in a record

Schema v3 — same shape as `mil/data/historical/enriched/*.json` files. Each record carries:

- `rating` (1-5), `review`/`content` (verbatim text), `date`/`at`, author/userName fields, version
- `issue_type` — one of 16 categories from `mil/config/domain_taxonomy.yaml`
- `customer_journey` — one of 9 categories
- `severity_class` — `P0` / `P1` / `P2`
- `sentiment_score` — float in `[-1.0, 1.0]`
- `reasoning` — single-sentence rationale

The records are **wholly synthetic**. Usernames are anonymous (`Sample User 001`), review text is fabricated from generic complaint patterns, and the corpus carries no real customer voices. There is no copyright or PII concern in shipping this in the public repo.

## How a fork uses this

### Bootstrap a fresh clone

```bash
mkdir -p mil/data/historical/enriched
cp mil/data/sample/*_enriched.json mil/data/historical/enriched/
py run_daily.py --skip-fetch
```

`--skip-fetch` skips the live App Store / Google Play harvest and re-runs inference + benchmark + publish over whatever is in `mil/data/historical/enriched/`. With the sample copied in, you get a complete pipeline run end-to-end: findings rendered, benchmark history populated, V1-V4 briefings written to `mil/publish/output/`.

### CI / end-to-end testing

The fixed seed (`SEED = 20260430` in `generate_sample.py`) means re-running the generator produces byte-identical output. CI can copy the sample into a temp directory and run inference deterministically — useful when the live corpus is moving and you want a stable smoke test.

### Customise for your fork

Edit `generate_sample.py`:
- Change `SUBJECTS` to your monitored firms.
- Change `RECORDS_PER_FILE` for cohort weighting.
- Change `ISSUE_TYPES` if you've retargeted the taxonomy (`mil/config/domain_taxonomy.yaml`).
- Bump `SEED` if you want a different pseudorandom layout.

Then re-run `py mil/data/sample/generate_sample.py` and commit the output.

## What this does NOT do

- Does not exercise the LLM enrichment route — records are pre-enriched. To test the live enrichment pipeline you need real raw fetch records and `ANTHROPIC_API_KEY`.
- Does not exercise the harvester — fetch step is skipped via `--skip-fetch`.
- Does not exercise the partner email or Slack heartbeat surfaces — those run as separate steps and are gated on `.env` configuration.
- Does not include CHRONICLE entries — `mil/CHRONICLE.md` is the canonical ledger; the sample corpus relies on whatever CHRONICLE pack the fork has installed.

## Regenerating

```bash
py mil/data/sample/generate_sample.py
```

The generator is committed alongside the JSON output so a fork can edit and re-emit. The JSON is the source of truth for `run_daily.py`; the generator exists for maintainability.
