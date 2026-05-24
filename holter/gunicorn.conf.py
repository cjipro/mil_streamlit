"""Gunicorn config for the Holter front-end (HOL-81).

Production / Linux serving of the full-page Pulse surfaces. gunicorn is
Unix-only, so this is the bank/Linux path; on Windows dev use the Flask dev
server (`py holter/server.py`). See holter/DEPLOY.md.

    gunicorn -c holter/gunicorn.conf.py holter.server:app

Tunable via environment (all optional):
    HOLTER_BIND      address:port to bind            (default 127.0.0.1:8600)
    HOLTER_WORKERS   worker processes                (default 2*CPU+1)
    HOLTER_TIMEOUT   worker timeout, seconds         (default 30)
    HOLTER_LOGLEVEL  gunicorn log level              (default info)

Bind defaults to loopback: the front-end is expected to sit behind a reverse
proxy / tunnel (as the rest of the stack does), not be exposed directly.
"""

import multiprocessing
import os

bind = os.environ.get("HOLTER_BIND", "127.0.0.1:8600")

# 0 / unset → derive from CPU count; otherwise honour the explicit value.
_workers_env = os.environ.get("HOLTER_WORKERS", "").strip()
workers = int(_workers_env) if _workers_env.isdigit() and int(_workers_env) > 0 \
    else multiprocessing.cpu_count() * 2 + 1

timeout = int(os.environ.get("HOLTER_TIMEOUT", "30"))
loglevel = os.environ.get("HOLTER_LOGLEVEL", "info")

# Pages render from in-process pack data; import the app once in the master and
# fork workers from it (faster worker boot, shared pages of memory).
preload_app = True

# Log to stdout/stderr so the supervisor / container captures it.
accesslog = "-"
errorlog = "-"

proc_name = "holter"
