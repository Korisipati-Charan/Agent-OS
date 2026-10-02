import json
import threading
import urllib.request
from pathlib import Path

from agentos.config import AgentOSConfig
from agentos.core.supervisor import SafetySupervisor
from agentos.memory.sqlite_store import SQLiteStore
from agentos.policy.audit_log import AuditLogger
from agentos.runtime.health_server import HealthServer


def _fetch(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=2) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_health_and_ready_endpoints(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    audit = AuditLogger(tmp_path / "audit.jsonl")
    supervisor = SafetySupervisor(config, audit)
    store = SQLiteStore(tmp_path / "probe.db")

    server = HealthServer("127.0.0.1", 0, supervisor, store)
    # Bind ephemeral port manually
    from http.server import ThreadingHTTPServer
    from agentos.runtime.health_server import _handler_class

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(server._readiness_check))
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        code, body = _fetch(f"http://{host}:{port}/healthz")
        assert code == 200
        assert body["status"] == "alive"

        code, body = _fetch(f"http://{host}:{port}/ready")
        assert code == 200
        assert body["status"] == "ready"
    finally:
        httpd.shutdown()
        httpd.server_close()
