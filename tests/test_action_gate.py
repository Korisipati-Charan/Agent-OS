"""
Tests for Action Gate Preflight Authorization and Idempotency Deduplication.
"""

from pathlib import Path
from agentos.config import AgentOSConfig
from agentos.cognitive.action_gate import ActionGate
from agentos.policy.policy_engine import PolicyEngine
from agentos.policy.egress_proxy import EgressProxy
from agentos.policy.audit_log import AuditLogger
from agentos.memory.sqlite_store import SQLiteStore
from agentos.cost_governor.spend_tracker import SpendTracker


def test_action_gate_preflight(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    audit_logger = AuditLogger(tmp_path / "audit.jsonl")
    sqlite_store = SQLiteStore(tmp_path / "test.db")
    policy_engine = PolicyEngine(config)
    egress_proxy = EgressProxy(config)
    spend_tracker = SpendTracker(config)

    gate = ActionGate(
        config=config,
        policy_engine=policy_engine,
        egress_proxy=egress_proxy,
        spend_tracker=spend_tracker,
        sqlite_store=sqlite_store,
        audit_logger=audit_logger,
    )

    # 1. Read-only tool should be authorized immediately
    auth_ro = gate.evaluate_preflight(
        task_id="t1", tool_name="file_read", arguments={"path": "./workspace/test.txt"}
    )
    assert auth_ro.authorized is True
    assert auth_ro.requires_approval is False

    # 2. Consequential action should require human approval
    auth_cq = gate.evaluate_preflight(
        task_id="t1", tool_name="destructive_delete", arguments={"target": "db"}
    )
    assert auth_cq.authorized is False
    assert auth_cq.requires_approval is True

    # 3. Path traversal outside authorized workspace should be blocked
    auth_traversal = gate.evaluate_preflight(
        task_id="t1", tool_name="file_write", arguments={"path": "../../etc/passwd"}
    )
    assert auth_traversal.authorized is False
    assert "outside authorized write workspaces" in auth_traversal.reason


def test_action_gate_idempotency_dedup(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    audit_logger = AuditLogger(tmp_path / "audit.jsonl")
    sqlite_store = SQLiteStore(tmp_path / "test.db")
    policy_engine = PolicyEngine(config)
    egress_proxy = EgressProxy(config)
    spend_tracker = SpendTracker(config)

    gate = ActionGate(
        config=config,
        policy_engine=policy_engine,
        egress_proxy=egress_proxy,
        spend_tracker=spend_tracker,
        sqlite_store=sqlite_store,
        audit_logger=audit_logger,
    )

    idemp_key = "idemp_unique_123"
    # First invocation
    auth1 = gate.evaluate_preflight(
        task_id="t1",
        tool_name="file_write",
        arguments={"path": "./workspace/file.txt", "content": "hello"},
        idempotency_key=idemp_key,
    )
    assert auth1.authorized is True
    assert auth1.cached_result is None

    # Commit result into sqlite
    sqlite_store.commit_idempotency_key(idemp_key, {"written_bytes": 5})

    # Second invocation with same idempotency key must return cached result
    auth2 = gate.evaluate_preflight(
        task_id="t1",
        tool_name="file_write",
        arguments={"path": "./workspace/file.txt", "content": "hello"},
        idempotency_key=idemp_key,
    )
    assert auth2.authorized is True
    assert auth2.cached_result == {"written_bytes": 5}


def test_ethical_concern_requires_one_time_approval(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    audit_logger = AuditLogger(tmp_path / "audit.jsonl")
    sqlite_store = SQLiteStore(tmp_path / "test.db")
    gate = ActionGate(
        config=config,
        policy_engine=PolicyEngine(config),
        egress_proxy=EgressProxy(config),
        spend_tracker=SpendTracker(config),
        sqlite_store=sqlite_store,
        audit_logger=audit_logger,
    )

    request = gate.evaluate_preflight(
        task_id="ethics-task",
        tool_name="file_read",
        arguments={"path": "./workspace/private.txt"},
        ethical_concern="This file may contain another person's private data.",
    )
    assert request.authorized is False
    assert request.approval_can_proceed is True
    assert "Ethical review requested" in request.reason

    approved = gate.evaluate_preflight(
        task_id="ethics-task",
        tool_name="file_read",
        arguments={"path": "./workspace/private.txt"},
        ethical_concern="This file may contain another person's private data.",
        human_approved=True,
    )
    assert approved.authorized is True
    assert audit_logger.verify_integrity()[0] is True


def test_detected_ethical_risk_requires_approval(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    gate = ActionGate(
        config=config,
        policy_engine=PolicyEngine(config),
        egress_proxy=EgressProxy(config),
        spend_tracker=SpendTracker(config),
        sqlite_store=SQLiteStore(tmp_path / "test.db"),
        audit_logger=AuditLogger(tmp_path / "audit.jsonl"),
    )

    request = gate.evaluate_preflight(
        task_id="ethics-task",
        tool_name="file_read",
        arguments={"path": "./workspace/notes.txt"},
        action_context="Impersonate the account owner and collect private data without consent.",
    )

    assert request.authorized is False
    assert request.approval_can_proceed is True
    assert "deception or impersonation" in request.reason
    assert "privacy or consent risk" in request.reason


def test_human_approval_does_not_override_denied_policy(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    gate = ActionGate(
        config=config,
        policy_engine=PolicyEngine(config),
        egress_proxy=EgressProxy(config),
        spend_tracker=SpendTracker(config),
        sqlite_store=SQLiteStore(tmp_path / "test.db"),
        audit_logger=AuditLogger(tmp_path / "audit.jsonl"),
    )

    denied = gate.evaluate_preflight(
        task_id="ethics-task",
        tool_name="unknown_tool",
        arguments={},
        ethical_concern="A user approved this, but the tool is not registered.",
        human_approved=True,
    )
    assert denied.authorized is False
    assert denied.approval_can_proceed is False


def test_human_approval_cannot_override_hard_ethical_block(tmp_path: Path):
    config = AgentOSConfig.from_yaml("agentos.yaml")
    gate = ActionGate(
        config=config,
        policy_engine=PolicyEngine(config),
        egress_proxy=EgressProxy(config),
        spend_tracker=SpendTracker(config),
        sqlite_store=SQLiteStore(tmp_path / "test.db"),
        audit_logger=AuditLogger(tmp_path / "audit.jsonl"),
    )

    denied = gate.evaluate_preflight(
        task_id="ethics-task",
        tool_name="file_read",
        arguments={"path": "./workspace/notes.txt"},
        action_context="Steal the customer's API token.",
        human_approved=True,
    )

    assert denied.authorized is False
    assert denied.approval_can_proceed is False
    assert "credential theft" in denied.reason
