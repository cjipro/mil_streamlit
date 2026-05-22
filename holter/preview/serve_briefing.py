"""Serve the MIL-style briefing HTML on localhost:8502 (or PORT env).

Per direction 2026-05-18: port 8502 should serve the MIL briefing template
(Box 0 sidebar + top nav + topbar boxes + ticker + journey row + body +
V3 layer), NOT the earlier Bloomberg-terminal Streamlit (templates_preview.py,
which is now deprecated reference).

This script:
  1. Re-renders dist/preview/index.html via render_mil_briefing.main()
  2. Starts a plain http.server bound to 8502 serving dist/preview/
  3. Stays running until Ctrl-C

Why http.server (not Streamlit): the briefing is a fully self-contained static
HTML page with its own CSS reset. Wrapping it in Streamlit's chrome adds noise
without adding anything. http.server is built into Python (zero deps), serves
the file as-is, and supports the dev loop of "edit render_mil_briefing.py →
rerun this script → hit reload".

Run:    py holter/preview/serve_briefing.py [PORT]
        (default port: 8502)
Reload: edit render_mil_briefing.py, restart this script, hit reload in browser
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SERVE_DIR = REPO / "dist" / "preview"

# Make `holter.preview.render_mil_briefing` importable when this script is
# invoked directly (not via `python -m`).
sys.path.insert(0, str(REPO))

from holter.preview import render_mil_briefing  # noqa: E402


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8502))

    print(f"[serve_briefing] re-rendering {SERVE_DIR}/index.html …")
    render_mil_briefing.main()

    if not SERVE_DIR.exists():
        raise SystemExit(f"render did not produce {SERVE_DIR}")

    # Suppress noisy default access logs; print only our own startup line.
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(SERVE_DIR), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            pass

    with socketserver.TCPServer(("127.0.0.1", port), QuietHandler) as httpd:
        print(f"[serve_briefing] http://localhost:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[serve_briefing] stopped.")


if __name__ == "__main__":
    main()
