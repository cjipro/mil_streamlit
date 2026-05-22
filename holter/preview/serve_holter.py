"""Serve the Holter design-template HTML on localhost:8504 (or PORT env).

Separate from serve_briefing.py (port 8502, the MIL briefing template).
:8504 is the design-stage Holter template with the locked box discipline.

Run:    py holter/preview/serve_holter.py [PORT]
        (default port: 8504)
Reload: edit render_holter.py, restart this script, hit reload in browser
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVE_DIR = REPO / "dist" / "preview" / "holter"

sys.path.insert(0, str(REPO))

from holter.preview import render_holter  # noqa: E402


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8504))

    print(f"[serve_holter] re-rendering {SERVE_DIR}/index.html …")
    render_holter.main()

    if not SERVE_DIR.exists():
        raise SystemExit(f"render did not produce {SERVE_DIR}")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(SERVE_DIR), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            pass

    with socketserver.TCPServer(("127.0.0.1", port), QuietHandler) as httpd:
        print(f"[serve_holter] http://localhost:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[serve_holter] stopped.")


if __name__ == "__main__":
    main()
