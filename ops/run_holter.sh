#!/usr/bin/env bash
# Holter front-end — production launch (Linux). gunicorn is Unix-only.
# Windows dev: run ops/run_holter.cmd (Flask dev server). See holter/DEPLOY.md.
#
# Env (optional): HOLTER_BIND / HOLTER_WORKERS / HOLTER_TIMEOUT / HOLTER_LOGLEVEL
set -euo pipefail
cd "$(dirname "$0")/.."
exec gunicorn -c holter/gunicorn.conf.py holter.server:app
