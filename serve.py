"""Serve the dashboard at http://localhost:8000 (you can also just double-click frontend/index.html)."""
import functools
import http.server
import socketserver
import webbrowser

from src import config as C

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Disable caching so the browser always reloads the latest app.js / data.js after re-running the pipeline."""
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()


H = functools.partial(NoCacheHandler, directory=str(C.FRONT))
with socketserver.TCPServer(("", 8000), H) as srv:
    print("Dashboard: http://localhost:8000   (Ctrl+C to stop)")
    webbrowser.open("http://localhost:8000")
    srv.serve_forever()
