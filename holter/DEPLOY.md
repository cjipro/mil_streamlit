# Holter front-end — running & deploying

The Holter front-end serves the full-page Pulse surfaces (Home / Workspace /
MLOps Console) over HTTP from `holter/server.py`. It's a standard WSGI Flask app
(`holter.server:app`); pages render server-side from in-process decision-pack
data, so there's no database or external service to stand up.

## Run it

### Dev (Windows / Mac / Linux)
Flask's built-in dev server, port 8600:

```
py holter/server.py          # or: ops/run_holter.cmd  (Windows)
```

Picks up code changes only on restart (no reloader). Not for production.

### Production (Linux)
[gunicorn](https://gunicorn.org/) — **Unix-only**, so this path does not run on
Windows (use the dev server there):

```
ops/run_holter.sh
# = gunicorn -c holter/gunicorn.conf.py holter.server:app
```

The front-end binds to loopback by default and is expected to sit **behind a
reverse proxy / tunnel** (like the rest of the stack), not be exposed directly.

## Configuration

`holter/gunicorn.conf.py` reads these env vars (all optional):

| Var | Default | Meaning |
|---|---|---|
| `HOLTER_BIND` | `127.0.0.1:8600` | address:port to bind |
| `HOLTER_WORKERS` | `2*CPU+1` | worker processes |
| `HOLTER_TIMEOUT` | `30` | worker timeout (seconds) |
| `HOLTER_LOGLEVEL` | `info` | gunicorn log level |

Access/error logs go to stdout/stderr for the supervisor or container to capture.

## Cerno (work-machine) deployment — HOL-90

The **Friction** surface (`/cerno`) renders the real Cerno friction pipeline
output — the Stage-C marts + the Step-4 D-014 shortlist — through the Holter
design system. It's the *real-data* half of the "Pulse deploys in two contexts"
model; the Decisions/Intelligence/Verification surfaces stay for the OSS
reference. Real data never leaves the work machine.

| Var | Default | Meaning |
|---|---|---|
| `CERNO_MARTS_DIR` | *(unset → SAMPLE)* | directory holding the real marts. When unset, a synthetic fixture renders and the surface shows a **SAMPLE** badge. Set it on the work machine → **LIVE**. |
| `CERNO_PRIMARY` | *(unset)* | when set (`1`), `/` redirects to `/cerno` so the Friction surface is the landing page. |

**Marts directory contract** (drop any subset; missing pieces fall back to the
sample fixture, per-piece):

| file | what |
|---|---|
| `d014_shortlist.csv` \| `.parquet` | the Step-4 Top-N decision table (drives the feed + drill) |
| `overview.json` | headline stats (sessions, customers, concentration, snapshot/map ids) |
| `c_weak_links.*` / `c_friction_matrix.*` / `c_error_cascades.*` | the Stage-C marts (evidence boxes) |
| `d014_candidate_detail.*` | *(optional)* per-candidate dossier; synthesised from the row if absent |

Column-name remaps for the real marts live in `COLUMN_MAP` / `MART_MAPS` at the
top of `holter/preview/cerno_source.py` — the only module that knows the marts
layout. No real data is committed; the adapter is generic.

Work-machine run:

```
CERNO_MARTS_DIR=/path/to/marts CERNO_PRIMARY=1 gunicorn -c holter/gunicorn.conf.py holter.server:app
# dev: CERNO_MARTS_DIR=/path/to/marts CERNO_PRIMARY=1 py holter/server.py
```

## Health check

`GET /healthz` — liveness **and** light readiness: 200 only if the process is up
*and* the engine can discover decision packs (catches a deploy where
`pulse/decision_packs/` is missing/unreadable). 503 otherwise, so a load balancer
pulls the instance out of rotation.

```json
GET /healthz  →  200
{"status": "ok", "service": "holter", "packs": 12, "surfaces": ["/", "/workspace", "/mlops"]}
```

## Dependencies

`Flask==3.0.3` + `gunicorn==23.0.0` (both on `APPROVED_LIBRARIES.md`) are pinned
in `requirements.txt`. Python is locked to 3.11.
