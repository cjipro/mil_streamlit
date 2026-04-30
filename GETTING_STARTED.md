# Getting started

This guide gets a CJI engine running end-to-end against a fresh checkout. The reference instance ships a banking CHRONICLE pack and a six-UK-bank competitor list — change `mil/config/apps_config.yaml`, `mil/config/clients.yaml`, and `mil/CHRONICLE.md` to retarget.

For the system architecture see [`ARCHITECTURE.md`](ARCHITECTURE.md). For day-to-day operations see [`RUNBOOK.md`](RUNBOOK.md).

---

## Prerequisites

| Tool | Version | Required for |
|---|---|---|
| Python | 3.11+ | The engine itself |
| Docker + docker-compose | recent | HDFS sovereign storage (optional — engine runs without it) |
| Ollama | recent | Local Qwen3 / Refuel-8B routes (optional if you stay on cloud-only models) |
| `wrangler` (Cloudflare) | recent | Only if you deploy the Workers — the engine does not require them |

Windows note: the reference environment runs on Windows + Git Bash + the `py` launcher (`py run_daily.py` not `python run_daily.py`). The engine itself is platform-agnostic.

---

## Install

```bash
git clone <your-fork-or-the-canonical-url>
cd while-sleeping
py -m venv .venv
. .venv/Scripts/activate            # or: source .venv/bin/activate on Unix
py -m pip install -r requirements.txt
py -m pip install -r mil/requirements.txt
```

`mil/requirements.txt` carries the heavier deps (sentence-transformers, duckdb, scipy, plotly, jinja2). `requirements.txt` at the repo root carries the shared application surface.

---

## Environment

Create `.env` at the repo root. The reference setup uses these keys; a fork can drop anything it does not need.

```bash
# LLM access (the engine is provider-aware via mil/config/model_routing.yaml)
ANTHROPIC_API_KEY=sk-ant-...

# Optional — local model routes
# OLLAMA_BASE_URL=http://127.0.0.1:11434

# Output destination — the engine writes briefings here
GITHUB_TOKEN=ghp_...                # for the GitHub Pages adapter
PUBLISH_REPO=org/your-pages-repo

# Optional — partner email distribution (MIL-49)
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=hello@yourdomain
# SMTP_APP_PASSWORD=...
# SMTP_FROM=Briefings <hello@yourdomain>

# Optional — operator heartbeat
# SLACK_WEBHOOK_URL=...

# Optional — hosted-reference auth stack only
# WORKOS_API_KEY=sk_test_...
# CLOUDFLARE_API_TOKEN=...
```

The reference instance reads its API tokens from `.env` and never from YAML — credentials never enter version control.

---

## Configure your tenant

Three configuration files determine what the engine watches and reports on.

### `mil/config/apps_config.yaml` — sources and subjects

Active sources, monitored competitors, App Store / Google Play package IDs, trust weights, fetch pagination. Drop competitors you do not care about. Add new ones with their store IDs.

### `mil/config/clients.yaml` — Sonar PDB recipients

YAML list of `{slug, display_name, status, email_domains}` records. `status: subject` enables the per-firm `/sonar/{slug}/` surface. The hosted reference monitors six banks but currently has one paying alpha — your fork sets its own list.

### `mil/CHRONICLE.md` — failure ledger

The anchor corpus for inference. Banking pack ships with CHR-001..019. To monitor a different sector, replace this file with your own ledger entries (see [`CHRONICLE_POLICY.md`](CHRONICLE_POLICY.md) for the schema and the constraints on what counts as a verified entry).

### `mil/config/domain_taxonomy.yaml` — issue types and journeys

Single source of truth for issue types (16 default), customer journeys (9 default), severity gates per issue type. Edit this file rather than hardcoding taxonomy in the pipeline — `mil/config/taxonomy_loader.py` reads it everywhere.

---

## First run

### Smoke test — fetch + enrich only, no publish

```bash
py run_daily.py --dry-run
```

Walks sources, dedups against existing records, enriches new ones. Exits without inference, vault, or publish. Good for confirming network access, API keys, and dedup behaviour.

### Full pipeline — local only

```bash
py run_daily.py
```

Eleven steps: fetch → enrich → inference → research → vault → Clark → benchmark → analytics DB → drift → publish (V1, V2, V3, V4, Sonar) → log. With no `GITHUB_TOKEN` set, the publish step writes to `mil/publish/output/` only.

### Re-run a single step

```bash
py run_daily.py --step 5d         # re-publish V4 only
py run_daily.py --step 4,4d,5d    # inference + benchmark + V4
```

`--step` skips heartbeat, run-log, summary, and partner email side-effects. Use it for hot-fixes and isolated debugging.

### Skip the network

```bash
py run_daily.py --skip-fetch      # use existing raw records, re-run inference + publish
```

---

## Where outputs land

| File | Purpose |
|---|---|
| `mil/data/historical/{source}/{competitor}/*.json` | Raw fetch records, accumulated daily |
| `mil/data/historical/enriched/*.json` | Enriched records (schema v3) |
| `mil/outputs/mil_findings.json` | The canonical inference artefact |
| `mil/publish/output/index.html` | V1 briefing (Box 1 source) |
| `mil/publish/output/index_v{2,3,4}.html` | Layered briefings |
| `mil/publish/output/sonar/{client}/[date]/index.html` | Per-firm Sonar PDB |
| `mil_analytics.db` | DuckDB read-side, rebuilt every run |
| `mil/data/daily_run_log.jsonl` | Run history, one row per pipeline fire |

If `GITHUB_TOKEN` + `PUBLISH_REPO` are set, the publish steps also push to GitHub Pages via the configured `PublishAdapter` (`mil/publish/adapters.py`).

---

## What's optional

The engine is layered so most components can be dropped without breaking the pipeline.

| Component | If omitted | Effect |
|---|---|---|
| HDFS (Docker) | Step 4b skips with TCP preflight warning | Local JSON is source of truth — no impact on inference or briefings |
| Ollama | qwen3-tier tasks fall back to cloud route or skip | Cost goes up; no behavioural change |
| Slack webhook | Heartbeat pings silently no-op | Run still completes; absence of alerting on failure |
| GitHub Pages adapter | Briefings render to `mil/publish/output/` only | Local-only operation, no public surface |
| Cloudflare Workers | No partner-facing auth surface | Engine is unfenced; appropriate for internal use |
| WorkOS | No magic-link or admin dashboard | Run your own auth in front of `app.cjipro.com` equivalent |
| SMTP | Step 8 silent-day's | No partner email distribution; pipeline still completes |

---

## Next

- Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the engine thinks (CAC, CHRONICLE-anchored RAG, four-tier model routing).
- Read [`RUNBOOK.md`](RUNBOOK.md) for daily operations and common failure recovery.
- Read [`CHRONICLE_POLICY.md`](CHRONICLE_POLICY.md) before authoring CHRONICLE entries — the verification standard is high.
