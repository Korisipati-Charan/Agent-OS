"""
AgentOS Planner.
Compiles high-level user goals into structured Task DAGs,
automatically identifying prerequisite gates, state-mutating actions,
and injecting durable checkpoints before external boundaries.
"""

import uuid
from typing import Any, Dict, List, Optional
from agentos.cognitive.dag import TaskDAG, TaskNode, TaskStatus
from agentos.config import AgentOSConfig


class Planner:
    def __init__(self, config: AgentOSConfig) -> None:
        self.config = config

    def compile_plan(self, goal: str, steps: List[Dict[str, Any]]) -> TaskDAG:
        """
        Compiles explicit or LLM-generated plan steps into a validated Task DAG.
        Injects checkpoint flags and idempotency requirements for mutating steps.
        """
        task_id = f"task_{uuid.uuid4().hex[:10]}"
        dag = TaskDAG(task_id=task_id, goal=goal)

        for step in steps:
            node_id = step.get("id") or f"node_{uuid.uuid4().hex[:6]}"
            tool_name = step.get("tool_name", "generic_exec")
            args = step.get("arguments", {})
            deps = set(step.get("dependencies", []))

            # Determine if action is mutating
            is_mutating = (
                tool_name in self.config.capability_tiers.workspace_write
                or tool_name in self.config.capability_tiers.consequential
            )

            # Generate idempotency key for mutating external operations
            idempotency_key = None
            if is_mutating:
                idempotency_key = f"idemp_{task_id}_{node_id}"

            node = TaskNode(
                node_id=node_id,
                description=step.get("description", f"Execute {tool_name}"),
                tool_name=tool_name,
                arguments=args,
                ethical_concern=step.get("ethical_concern"),
                dependencies=deps,
                status=TaskStatus.PENDING,
                is_mutating=is_mutating,
                idempotency_key=idempotency_key,
                requires_checkpoint=is_mutating,  # Invariant: checkpoint before mutating/retryable action
            )
            dag.add_node(node)

        # Validate DAG acyclicity using Kahn's algorithm
        dag.validate_acyclic()
        return dag
