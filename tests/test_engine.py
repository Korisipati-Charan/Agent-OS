import asyncio
import sqlite3
from types import SimpleNamespace

from agentos.action_space.base import BaseTool
from agentos.cognitive.action_gate import PreflightAuthorization
from agentos.cognitive.dag import TaskDAG, TaskNode
from agentos.config import AgentOSConfig
from agentos.core.engine import CognitiveEngine
from agentos.memory.sqlite_store import SQLiteStore
from agentos.policy.audit_log import AuditLogger


class StoppedState:
    def is_stopped(self):
        return False

    def heartbeat(self):
        pass


class OneStepPlanner:
    def compile_plan(self, goal, steps):
        dag = TaskDAG(task_id="task_failure_case", goal=goal)
        dag.add_node(
            TaskNode(
                node_id="read_step",
                description="Read one item",
                tool_name="file_read",
                ethical_concern="Personal data may be exposed.",
            )
        )
        return dag


class AllowAction:
    def evaluate_preflight(self, **kwargs):
        return PreflightAuthorization(authorized=True, reason="allowed")


class UnexpectedTool(BaseTool):
    name = "file_read"
    description = "Raises a controlled error for the engine regression test."

    async def execute(self, arguments, context):
        raise RuntimeError("Bearer private-token-value")


class SuccessfulTool(BaseTool):
    name = "file_read"
    description = "Returns a safe test result."
    executions = 0

    async def execute(self, arguments, context):
        type(self).executions += 1
        return SimpleNamespace(success=True, output="ok", error=None, postcondition_state={})


class EthicalApprovalAction:
    def evaluate_preflight(self, **kwargs):
        if kwargs.get("human_approved"):
            return PreflightAuthorization(authorized=True, reason="approved")
        return PreflightAuthorization(
            authorized=False,
            requires_approval=True,
            approval_can_proceed=True,
            reason="Ethical review requested: personal data may be exposed.",
        )


class ValidPostcondition:
    def verify_action(self, **kwargs):
        return SimpleNamespace(
            is_valid=True,
            reasons=[],
            sanitized_output="ok",
        )


def test_tool_exception_fails_task_and_finishes_audit(tmp_path):
    store = SQLiteStore(tmp_path / "agentos.db")
    audit = AuditLogger(tmp_path / "audit.jsonl")
    engine = CognitiveEngine(
        config=AgentOSConfig.from_yaml("agentos.yaml"),
        supervisor=StoppedState(),
        planner=OneStepPlanner(),
        action_gate=AllowAction(),
        postcondition_gate=None,
        sandbox=type("Sandbox", (), {"workspace_root": str(tmp_path)})(),
        sqlite_store=store,
        audit_logger=audit,
    )
    engine.register_tool(UnexpectedTool())

    result = asyncio.run(engine.execute_task("Read one item", []))

    assert result["status"] == "FAILED"
    assert result["dag"]["nodes"]["read_step"]["status"] == "FAILED"
    assert result["dag"]["nodes"]["read_step"]["error"] == "Tool execution raised RuntimeError."
    assert "private-token-value" not in str(result)

    with sqlite3.connect(store.db_path) as connection:
        task_status = connection.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            ("task_failure_case",),
        ).fetchone()[0]
    assert task_status == "FAILED"
    assert audit.verify_integrity()[0] is True


def test_cli_approval_callback_gates_ethically_flagged_action(tmp_path):
    SuccessfulTool.executions = 0
    store = SQLiteStore(tmp_path / "agentos.db")
    audit = AuditLogger(tmp_path / "audit.jsonl")
    engine = CognitiveEngine(
        config=AgentOSConfig.from_yaml("agentos.yaml"),
        supervisor=StoppedState(),
        planner=OneStepPlanner(),
        action_gate=EthicalApprovalAction(),
        postcondition_gate=ValidPostcondition(),
        sandbox=type("Sandbox", (), {"workspace_root": str(tmp_path)})(),
        sqlite_store=store,
        audit_logger=audit,
    )
    engine.register_tool(SuccessfulTool())
    seen = []

    result = asyncio.run(
        engine.execute_task(
            "Read a private file",
            [],
            approval_callback=lambda request: seen.append(request) or True,
        )
    )

    assert result["status"] == "COMPLETED"
    assert len(seen) == 1
    assert "Ethical review requested" in seen[0]["reason"]
    assert seen[0]["ethical_concern"] == "Personal data may be exposed."
    assert SuccessfulTool.executions == 1


def test_declining_ethical_review_prevents_tool_execution(tmp_path):
    SuccessfulTool.executions = 0
    store = SQLiteStore(tmp_path / "agentos.db")
    audit = AuditLogger(tmp_path / "audit.jsonl")
    engine = CognitiveEngine(
        config=AgentOSConfig.from_yaml("agentos.yaml"),
        supervisor=StoppedState(),
        planner=OneStepPlanner(),
        action_gate=EthicalApprovalAction(),
        postcondition_gate=ValidPostcondition(),
        sandbox=type("Sandbox", (), {"workspace_root": str(tmp_path)})(),
        sqlite_store=store,
        audit_logger=audit,
    )
    engine.register_tool(SuccessfulTool())

    result = asyncio.run(
        engine.execute_task("Read a private file", [], approval_callback=lambda _: False)
    )

    assert result["status"] == "FAILED"
    assert result["dag"]["nodes"]["read_step"]["error"] == "Human approval declined."
    assert SuccessfulTool.executions == 0
