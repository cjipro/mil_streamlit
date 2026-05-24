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
