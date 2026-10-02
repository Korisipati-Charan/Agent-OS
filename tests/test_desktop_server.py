"""
Tests for AgentOS Desktop Application Backend Server.
Validates REST endpoints, Action Gate intervention lifecycle, telemetry,
and workspace sandboxing boundaries.
"""

import os
from pathlib import Path
from starlette.testclient import TestClient

from agentos.desktop.server import create_desktop_app
from agentos.runtime.bootstrap import build_runtime


def test_desktop_status_endpoint(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["online"] is True
    assert data["version"] == "3.0.1"
    assert "RTX 5060" in data["hardware"]["gpu"]
    assert "Intel" in data["hardware"]["cpu"]
    assert data["supervisor"]["active"] is True
    assert data["supervisor"]["emergency_stop"] is False
    assert "total_spend_usd" in data["cost_governor"]


def test_desktop_metrics_endpoint(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()

    assert "gpu_vram_used_mb" in data
    assert "kv_cache_hit_rate" in data
    assert "doherty_latency_ms" in data
    assert data["doherty_latency_ms"] < 400.0  # Doherty threshold requirement


def test_workspace_files_and_traversal_defense(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    secret_file = tmp_path / "host_secret.txt"
    secret_file.write_text("SUPER_SECRET_KEY")

    workspace_file = ws / "sample.txt"
    workspace_file.write_text("Hello from inside workspace sandbox!")

    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    # 1. List workspace files
    list_resp = client.get("/api/workspace/files")
    assert list_resp.status_code == 200
    files = list_resp.json()
    assert any(f["name"] == "sample.txt" for f in files)

    # 2. Read authorized file
    read_resp = client.get("/api/workspace/file?path=sample.txt")
    assert read_resp.status_code == 200
    assert "Hello from inside workspace" in read_resp.json()["content"]

    # 3. Path traversal attack attempt should be blocked (403)
    traversal_resp = client.get("/api/workspace/file?path=../host_secret.txt")
    assert traversal_resp.status_code == 403


def test_task_submission_and_listing(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    # Submit task
    submit_resp = client.post(
        "/api/tasks",
        json={"goal": "Verify desktop task execution and DAG compilation"},
    )
    assert submit_resp.status_code == 200
    submit_data = submit_resp.json()
    assert submit_data["status"] == "ACCEPTED"
    assert "task_id" in submit_data

    # Verify task appears in task list
    tasks_resp = client.get("/api/tasks")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    assert any(t["task_id"] == submit_data["task_id"] for t in tasks)


def test_supervisor_emergency_stop_lifecycle(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    # 1. Trigger Emergency Stop
    stop_resp = client.post("/api/supervisor/emergency-stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["emergency_stop"] is True

    # 2. Status verifies emergency stop armed
    status_resp = client.get("/api/status")
    assert status_resp.json()["supervisor"]["emergency_stop"] is True

    # 3. New tasks must be blocked while emergency stop is armed
    blocked_resp = client.post("/api/tasks", json={"goal": "Should fail"})
    assert blocked_resp.status_code == 400

    # 4. Resume supervisor
    resume_resp = client.post("/api/supervisor/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["emergency_stop"] is False

    # 5. New task succeeds
    allowed_resp = client.post("/api/tasks", json={"goal": "Allowed after resume"})
    assert allowed_resp.status_code == 200


def test_audit_logs_retrieval(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    runtime.audit_logger.log(
        action_type="TEST_DESKTOP_INIT",
        actor="desktop_suite",
        payload={"module": "desktop_server"},
    )

    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    resp = client.get("/api/audit/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is True
    assert len(data["records"]) >= 1
    assert data["records"][-1]["action_type"] == "TEST_DESKTOP_INIT"


def test_action_gate_decision_not_found(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    resp = client.post(
        "/api/action-gate/decision",
        json={"approval_id": "non_existent_gate", "approved": True},
    )
    assert resp.status_code == 404


def test_static_index_page_serving(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db = tmp_path / "test.db"
    audit = tmp_path / "audit.jsonl"

    runtime = build_runtime(workspace=str(ws), db_path=str(db), audit_path=str(audit))
    app = create_desktop_app(runtime=runtime)
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "AgentOS — Mission Control Studio" in resp.text
