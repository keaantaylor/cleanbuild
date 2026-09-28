"""Minimal webhook receiver for integration tests (stdlib only).

POST /hooks/<name>  stores the request (headers + body) and returns 200,
                    or the status in ?status=NNN to simulate failures.
GET  /deliveries    returns every stored request as JSON.
DELETE /deliveries  clears the store.
GET  /health        liveness.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_LOCK = threading.Lock()
_DELIVERIES: list[dict[str, object]] = []


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, {"ok": True})
        elif path == "/deliveries":
            with _LOCK:
                self._send(200, list(_DELIVERIES))
        else:
            self._send(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        if urlparse(self.path).path == "/deliveries":
            with _LOCK:
                _DELIVERIES.clear()
            self._send(200, {"cleared": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if not url.path.startswith("/hooks/"):
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        status = int(parse_qs(url.query).get("status", ["200"])[0])
        with _LOCK:
            _DELIVERIES.append({"path": url.path, "headers": dict(self.headers), "body": body, "responded": status})
        self._send(status, {"received": True})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - quiet
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()  # noqa: S104  # nosec B104 (inside the test container only)
