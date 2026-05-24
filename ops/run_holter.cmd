@echo off
REM Holter front-end — Windows dev launch (Flask dev server on :8600).
REM gunicorn is Unix-only; production (Linux) uses ops/run_holter.sh.
REM See holter\DEPLOY.md.
cd /d "%~dp0\.."
py holter\server.py
