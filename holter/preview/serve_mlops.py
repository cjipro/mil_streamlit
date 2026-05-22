"""Serve the MLOps Console (HOL-6) design-template HTML on localhost:8506.

Surface map:
  :8502  serve_briefing.py  — MIL briefing (canonical Workspace aesthetic ref)
  :8503  canvas.py          — real_bank Canvas Streamlit (dev tool)
  :8504  serve_holter.py    — HOL-3 Workspace (design-locked 2026-05-19)
  :8505  serve_home.py      — HOL-4 Pulse Home (design-locked 2026-05-19)
  :8506  serve_mlops.py     — HOL-6 MLOps Console (this file)

Run:    py holter/preview/serve_mlops.py [PORT]
        (default port: 8506)
Reload: edit render_mlops.py, restart this script, hit reload in browser
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVE_DIR = REPO / "dist" / "preview" / "mlops"

sys.path.insert(0, str(REPO))

from holter.preview import render_mlops  # noqa: E402


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8506))

    print(f"[serve_mlops] re-rendering {SERVE_DIR}/index.html …")
    render_mlops.main()

    if not SERVE_DIR.exists():
        raise SystemExit(f"render did not produce {SERVE_DIR}")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(SERVE_DIR), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            pass

    with socketserver.TCPServer(("127.0.0.1", port), QuietHandler) as httpd:
        print(f"[serve_mlops] http://localhost:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[serve_mlops] stopped.")


if __name__ == "__main__":
    main()
