"""
mil/chat/api_server.py — MIL-45 companion.

Tiny stdlib HTTP server fronting the Ask CJI Pro pipeline. No third-party
dependencies — built on http.server so it starts instantly on any box
with Python.

Endpoints
---------
GET  /api/health          → {"ok": true, "version": "..."}
POST /api/ask             → body {"query": str, "deep"?: bool, "k_each"?: int}
                            returns full AskResponse as JSON
POST /api/feedback        → body {"trace_id": str, "verdict": "up"|"down"|...,
                                  "note"?: str, "partner_id"?: str}
GET  /api/audit/summary   → last 50 audit rows
GET  /api/feedback/summary → aggregate feedback counts

CORS is enabled for any Origin — behind a Cloudflare Tunnel you can restrict
this via the tunnel config / Cloudflare Access rules instead of in-app.

Run
---
    py -m mil.chat.api_server                # binds 127.0.0.1:8765
    py -m mil.chat.api_server --host 0.0.0.0 --port 8765

Expose publicly
---------------
    cloudflared tunnel --url http://127.0.0.1:8765
Point sonar.cjipro.com/api/* to the tunnel in Cloudflare DNS + Rules.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as _BaseHTTPServer


class ThreadingHTTPServer(_BaseHTTPServer):
    """Refuse to start if another instance is already bound to the port.

    Default stdlib behaviour on Windows allows multiple processes to bind the
    same port (SO_REUSEADDR), which silently produced a zombie-server farm
    during iterative development. Force exclusive binding — better to fail
    loudly on startup than round-robin across stale interpreters.
    """
    allow_reuse_address = False
    allow_reuse_port = False
from pathlib import Path
from typing import Any

from mil.chat import audit, feedback
from mil.chat.pipeline import ask

logger = logging.getLogger(__name__)

API_VERSION = "1.1.0"
_AUDIT_LOG = Path(__file__).parent.parent / "data" / "ask_audit_log.jsonl"
_UI_HTML   = Path(__file__).parent / "ui" / "chat.html"


class _Handler(BaseHTTPRequestHandler):
    server_version = f"AskCJIPro/{API_VERSION}"

    # ── Plumbing ──────────────────────────────────────────────────────────
    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _write_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _partner_id(self) -> str | None:
        """Trusted caller identity from the Cloudflare Access JWT header.

        Returned to the pipeline as ``partner_id`` and stamped into audit +
        feedback rows. The header is injected by Cloudflare only after Access
        verifies the SSO token, so it is the right trust root once the tunnel
        is gated. Returns None in dev (direct-to-127.0.0.1) — the API still
        responds, rows just carry a null partner_id.
        """
        email = self.headers.get("Cf-Access-Authenticated-User-Email")
        return email.strip().lower() if email else None

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # ── Routes ────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        if self.path in ("/", "/chat", "/chat.html", "/index.html"):
            self._serve_ui()
        elif self.path == "/api/health":
            self._write_json(200, {"ok": True, "version": API_VERSION})
        elif self.path == "/api/audit/summary":
            self._write_json(200, self._audit_summary())
        elif self.path == "/api/feedback/summary":
            self._write_json(200, feedback.summary())
        else:
            self._write_json(404, {"error": "not_found", "path": self.path})

    def _serve_ui(self) -> None:
        try:
            body = _UI_HTML.read_bytes()
        except Exception as exc:
            self._write_json(500, {"error": "ui_missing", "detail": str(exc)})
            return
        self._write_html(200, body)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/ask":
                self._route_ask()
            elif self.path == "/api/feedback":
                self._route_feedback()
            else:
                self._write_json(404, {"error": "not_found", "path": self.path})
        except Exception as exc:
            logger.exception("unhandled error")
            self._write_json(500, {"error": "internal", "detail": str(exc),
                                    "trace": traceback.format_exc().splitlines()[-3:]})

    # ── Handlers ──────────────────────────────────────────────────────────
    def _route_ask(self) -> None:
        body = self._read_body()
        query = (body.get("query") or "").strip()
        if not query:
            self._write_json(400, {"error": "missing_query"})
            return
        deep = bool(body.get("deep", False))
        k_each = int(body.get("k_each", 8))
        resp = ask(query, deep=deep, k_each=k_each, partner_id=self._partner_id())
        self._write_json(200, resp.to_dict())

    def _route_feedback(self) -> None:
        body = self._read_body()
        trace_id = (body.get("trace_id") or "").strip()
        verdict = (body.get("verdict") or "").strip()
        if not trace_id or verdict not in ("up", "down", "refusal_wrong", "refusal_right"):
            self._write_json(400, {"error": "bad_feedback",
                                    "hint": "trace_id + verdict in up/down/refusal_* required"})
            return
        feedback.log(feedback.FeedbackEntry(
            trace_id=trace_id,
            verdict=verdict,  # type: ignore[arg-type]
            note=str(body.get("note") or ""),
            partner_id=self._partner_id() or body.get("partner_id"),
        ))
        self._write_json(200, {"ok": True})

    def _audit_summary(self, limit: int = 50) -> dict:
        entries: list[dict] = []
        if not _AUDIT_LOG.exists():
            return {"total": 0, "recent": []}
        try:
            with _AUDIT_LOG.open(encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return {"total": len(lines), "recent": entries}
        except Exception as exc:
            logger.warning("audit summary failed: %s", exc)
            return {"total": 0, "recent": [], "error": str(exc)}


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    httpd = ThreadingHTTPServer((host, port), _Handler)
    logger.info("Ask CJI Pro API listening on http://%s:%d", host, port)
    logger.info("  POST /api/ask        body={\"query\": \"...\", \"deep\": false}")
    logger.info("  POST /api/feedback   body={\"trace_id\": \"...\", \"verdict\": \"up|down\"}")
    logger.info("  GET  /api/health")
    logger.info("  GET  /api/audit/summary")
    logger.info("  GET  /api/feedback/summary")

    # Warm retrievers in a background thread so the first real request is fast.
    threading.Thread(target=_warm_retrievers, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
        httpd.server_close()


def _warm_retrievers() -> None:
    """Prime the BM25 index + embedding cache so first /api/ask is not cold."""
    try:
        from mil.chat.retrievers.bm25 import BM25Retriever
        from mil.chat.retrievers.embedding import EmbeddingRetriever
        BM25Retriever().retrieve("warmup", {}, k=1)
        EmbeddingRetriever().retrieve("warmup", {}, k=1)
        logger.info("retrievers warmed")
    except Exception as exc:
        logger.warning("warmup failed: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask CJI Pro HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(args.host, args.port)
    sys.exit(0)
