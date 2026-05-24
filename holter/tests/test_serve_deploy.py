"""HOL-81 — Holter serve/deploy path.

Covers the deployability surface without needing gunicorn (Unix-only, can't run
on the Windows dev box): the /healthz probe (ok + degraded), the WSGI callable
that gunicorn targets, and the gunicorn config (defaults + env overrides) loaded
as plain Python.

Run:  python -m pytest holter/tests/test_serve_deploy.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import holter.server as S
from holter.server import app

CONF = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"


def _load_conf(env: dict | None = None) -> dict:
    """Execute gunicorn.conf.py in a fresh namespace, with optional env overrides
    applied for the duration, and return its module globals."""
    saved: dict[str, str | None] = {}
    for k, v in (env or {}).items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        ns: dict = {}
        exec(compile(CONF.read_text(encoding="utf-8"), str(CONF), "exec"), ns)
        return ns
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


# ── /healthz ──────────────────────────────────────────────────────────────────

def test_healthz_ok():
    r = app.test_client().get("/healthz")
    assert r.status_code == 200
    assert r.mimetype == "application/json"
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "holter"
    assert data["packs"] >= 1
    assert "/workspace" in data["surfaces"]


def test_healthz_degraded_503_when_engine_cannot_load(monkeypatch):
    def boom():
        raise RuntimeError("decision_packs missing")
    monkeypatch.setattr(S, "discover_packs", boom)
    r = S.app.test_client().get("/healthz")
    assert r.status_code == 503
    body = r.get_json()
    assert body["status"] == "degraded"
    assert "decision_packs missing" in body["error"]


# ── WSGI target ─────────────────────────────────────────────────────────────--

def test_app_is_the_wsgi_callable():
    # gunicorn launches `holter.server:app`
    assert callable(app)


# ── gunicorn config ─────────────────────────────────────────────────────────--

def test_gunicorn_conf_defaults():
    ns = _load_conf()
    assert ns["bind"] == "127.0.0.1:8600"
    assert isinstance(ns["workers"], int) and ns["workers"] >= 1
    assert ns["timeout"] == 30
    assert ns["preload_app"] is True
    assert ns["accesslog"] == "-" and ns["errorlog"] == "-"


def test_gunicorn_conf_env_overrides():
    ns = _load_conf({"HOLTER_BIND": "0.0.0.0:9000",
                     "HOLTER_WORKERS": "3",
                     "HOLTER_TIMEOUT": "45",
                     "HOLTER_LOGLEVEL": "warning"})
    assert ns["bind"] == "0.0.0.0:9000"
    assert ns["workers"] == 3
    assert ns["timeout"] == 45
    assert ns["loglevel"] == "warning"
