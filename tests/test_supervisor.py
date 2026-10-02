import subprocess

from agentos.config import AgentOSConfig
from agentos.core.supervisor import SafetySupervisor
from agentos.policy.audit_log import AuditLogger


def test_watchdog_stops_without_reentering_supervisor_lock(tmp_path, monkeypatch):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    config.system["supervisor"]["heartbeat_interval_sec"] = 0.01
    config.system["supervisor"]["watchdog_timeout_sec"] = 0
    monkeypatch.setattr(
        SafetySupervisor,
        "_container_runtime_available",
        staticmethod(lambda: False),
    )
    audit = AuditLogger(tmp_path / "audit.jsonl")
    supervisor = SafetySupervisor(config, audit)

    supervisor.start_watchdog()
    supervisor._watchdog_thread.join(timeout=1)

    assert not supervisor._watchdog_thread.is_alive()
    assert supervisor.is_stopped()
    assert supervisor._watchdog_running is False
    assert audit.verify_integrity()[0] is True


def test_container_runtime_requires_a_responsive_runtime(monkeypatch):
    monkeypatch.setattr("agentos.core.supervisor.shutil.which", lambda name: "docker.exe")
    monkeypatch.setattr(
        "agentos.core.supervisor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )

    assert SafetySupervisor._container_runtime_available() is False


def test_container_runtime_detects_a_responsive_runtime(monkeypatch):
    monkeypatch.setattr("agentos.core.supervisor.shutil.which", lambda name: "docker.exe")
    monkeypatch.setattr(
        "agentos.core.supervisor.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0),
    )

    assert SafetySupervisor._container_runtime_available() is True
