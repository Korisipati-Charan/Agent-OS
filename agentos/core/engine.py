"""
AgentOS Cognitive Engine.
Coordinates planning, preflight action gating, sandboxed execution,
postcondition verification, durable checkpointing, and audit logging.
"""

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from agentos.config import AgentOSConfig
from agentos.core.supervisor import SafetySupervisor
from agentos.cognitive.planner import Planner
from agentos.cognitive.dag import TaskDAG, TaskNode, TaskStatus
from agentos.cognitive.action_gate import ActionGate, PreflightAuthorization
from agentos.cognitive.reflection import PostconditionGate, VerificationResult
from agentos.action_space.base import BaseTool, ToolExecutionContext, ToolResult
from agentos.action_space.sandboxes.base import SandboxProvider
from agentos.memory.sqlite_store import SQLiteStore
from agentos.policy.audit_log import AuditLogger


class CognitiveEngine:
    def __init__(
        self,
        config: AgentOSConfig,
        supervisor: SafetySupervisor,
        planner: Planner,
        action_gate: ActionGate,
        postcondition_gate: PostconditionGate,
        sandbox: SandboxProvider,
        sqlite_store: SQLiteStore,
        audit_logger: AuditLogger,
    ) -> None:
        self.config = config
        self.supervisor = supervisor
        self.planner = planner
        self.action_gate = action_gate
        self.postcondition_gate = postcondition_gate
        self.sandbox = sandbox
        self.sqlite_store = sqlite_store
        self.audit_logger = audit_logger
        self.registered_tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        self.registered_tools[tool.name] = tool

    async def execute_task(
        self,
        goal: str,
        planned_steps: List[Dict[str, Any]],
        approval_callback: Optional[Callable[[Dict[str, str]], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a planned goal adhering strictly to all v3.0.1 logic invariants:
        1. Compile DAG with Kahn's topological ordering.
        2. Authorize before side effect (Action Gate).
        3. Checkpoint before retryable/mutating action.
        4. Execute within sandbox boundary.
        5. Verify after side effect (Postcondition Gate).
        6. Commit state atomically.
        """
        if self.supervisor.is_stopped():
            return {"status": "FAILED", "reason": "Supervisor emergency stop is active."}

        # 1. Compile Goal into validated Task DAG
        dag = self.planner.compile_plan(goal=goal, steps=planned_steps)
        self.sqlite_store.save_task(task_id=dag.task_id, goal=goal, status="RUNNING")

        self.audit_logger.log(
            action_type="TASK_STARTED",
            actor="cognitive_engine",
            payload={"task_id": dag.task_id, "goal": goal, "node_count": len(dag.nodes)},
        )

        while not dag.is_finished():
            if self.supervisor.is_stopped():
                break

            self.supervisor.heartbeat()
            ready_nodes = dag.get_ready_nodes()

            if not ready_nodes:
                # Pending nodes with no ready dependencies indicate an invalid plan state.
                break

            for node in ready_nodes:
                node.status = TaskStatus.RUNNING

                # 2. Checkpoint state BEFORE mutating action
                if node.requires_checkpoint:
                    self.sqlite_store.save_checkpoint(
                        checkpoint_id=f"chk_{dag.task_id}_{node.node_id}",
                        task_id=dag.task_id,
                        node_id=node.node_id,
                        state=node.model_dump(mode="json"),
                    )

                # 3. Preflight Authorization (Action Gate)
                action_context = "\n".join(
                    (goal, node.description, node.tool_name, str(node.arguments))
                )
                auth: PreflightAuthorization = self.action_gate.evaluate_preflight(
                    task_id=dag.task_id,
                    tool_name=node.tool_name,
                    arguments=node.arguments,
                    idempotency_key=node.idempotency_key,
                    ethical_concern=node.ethical_concern,
                    action_context=action_context,
                )

                if auth.approval_can_proceed and approval_callback is not None:
                    approved = approval_callback(
                        {
                            "tool_name": node.tool_name,
                            "description": node.description,
                            "reason": auth.reason,
                            "ethical_concern": node.ethical_concern or "",
                        }
                    )
                    if approved:
                        auth = self.action_gate.evaluate_preflight(
                            task_id=dag.task_id,
                            tool_name=node.tool_name,
                            arguments=node.arguments,
                            idempotency_key=node.idempotency_key,
                            ethical_concern=node.ethical_concern,
                            human_approved=True,
                            action_context=action_context,
                        )

                if not auth.authorized:
                    if auth.requires_approval:
                        approval_state = (
                            "Human approval declined."
                            if approval_callback is not None and auth.approval_can_proceed
                            else f"Awaiting human approval: {auth.reason}"
                        )
                        dag.mark_failed(
                            node.node_id,
                            error=approval_state,
                        )
                    else:
                        dag.mark_failed(
                            node.node_id,
                            error=f"Preflight authorization denied: {auth.reason}",
                        )
                    continue

                # 4. Idempotency Cache Short-Circuit
                if auth.cached_result:
                    dag.mark_completed(node.node_id, result=auth.cached_result)
                    continue

                # 5. Tool Execution inside Sandbox
                try:
                    tool_result = await self._dispatch_tool_execution(dag.task_id, node)
                except Exception as exc:
                    dag.mark_failed(
                        node.node_id,
                        error=f"Tool execution raised {type(exc).__name__}.",
                    )
                    continue

                if not tool_result.success:
                    dag.mark_failed(
                        node.node_id,
                        error=tool_result.error or "Tool execution failed",
                    )
                    continue

                # 6. Postcondition Verification (Postcondition Gate)
                verification: VerificationResult = self.postcondition_gate.verify_action(
                    task_id=dag.task_id,
                    tool_name=node.tool_name,
                    is_mutating=node.is_mutating,
                    raw_output=tool_result.output,
                    expected_postcondition=node.arguments.get("expected_postcondition"),
                    observed_postcondition=tool_result.postcondition_state,
                )

                if not verification.is_valid:
                    dag.mark_failed(
                        node.node_id,
                        error=f"Postcondition verification failed: {verification.reasons}",
                    )
                    continue

                # 7. Commit State and Idempotency Key
                if node.idempotency_key:
                    self.sqlite_store.commit_idempotency_key(
                        idempotency_key=node.idempotency_key,
                        response_data={"output": verification.sanitized_output},
                    )

                dag.mark_completed(node.node_id, result=verification.sanitized_output)

        all_steps_completed = all(
            node.status == TaskStatus.COMPLETED for node in dag.nodes.values()
        )
        final_status = "COMPLETED" if all_steps_completed else "FAILED"
        self.sqlite_store.save_task(task_id=dag.task_id, goal=goal, status=final_status)

        self.audit_logger.log(
            action_type="TASK_FINISHED",
            actor="cognitive_engine",
            payload={"task_id": dag.task_id, "status": final_status},
        )

        return {
            "task_id": dag.task_id,
            "status": final_status,
            "dag": dag.to_dict(),
        }

    async def _dispatch_tool_execution(self, task_id: str, node: TaskNode) -> ToolResult:
        workspace_path = str(getattr(self.sandbox, "workspace_root", Path("./workspace")))
        context = ToolExecutionContext(
            task_id=task_id,
            node_id=node.node_id,
            workspace_path=workspace_path,
        )

        if node.tool_name in self.registered_tools:
            tool = self.registered_tools[node.tool_name]
            return await tool.execute(node.arguments, context)

        # Fallback to Sandbox generic shell execution
        cmd = node.arguments.get("command") or f"echo Running {node.tool_name}"
        res = self.sandbox.execute_command(command=cmd, cwd=context.workspace_path)
        return ToolResult(
            success=res.exit_code == 0,
            output=res.stdout,
            error=res.stderr if res.exit_code != 0 else None,
            exit_code=res.exit_code,
            postcondition_state={"exit_code": res.exit_code},
        )
