"""
Minimal HTTP surface for orchestrator probes (/healthz, /ready).
Uses stdlib only so container images stay small and dependency-light.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from agentos.core.supervisor import SafetySupervisor
from agentos.memory.sqlite_store import SQLiteStore

ReadinessFn = Callable[[], tuple[bool, str]]


def _handler_class(readiness_check: ReadinessFn) -> type[BaseHTTPRequestHandler]:
    class ProbeHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._json(200, {"status": "alive"})
                return

            if self.path == "/ready":
                ready, detail = readiness_check()
                self._json(200 if ready else 503, {"status": "ready" if ready else "not_ready", "detail": detail})
                return

            self._json(404, {"status": "not_found"})

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ProbeHandler


class HealthServer:
    def __init__(
        self,
        host: str,
        port: int,
        supervisor: SafetySupervisor,
        sqlite_store: SQLiteStore,
    ) -> None:
        self._host = host
        self._port = port
        self._readiness_check = self._build_readiness(supervisor, sqlite_store)

    @staticmethod
    def _build_readiness(supervisor: SafetySupervisor, sqlite_store: SQLiteStore) -> ReadinessFn:
        def check() -> tuple[bool, str]:
            if supervisor.is_stopped():
                return False, "supervisor emergency stop active"
            sqlite_store.ping()
            return True, "ok"

        return check

    def run_forever(self) -> None:
        handler = _handler_class(self._readiness_check)
        httpd = ThreadingHTTPServer((self._host, self._port), handler)
        httpd.serve_forever()
