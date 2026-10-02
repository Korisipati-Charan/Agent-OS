"""
AgentOS Task DAG (Directed Acyclic Graph).
Implements Kahn's Algorithm for topological sorting, cycle detection,
dependency resolution, and state checkpoint boundaries.
"""

from collections import deque
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class TaskNode(BaseModel):
    node_id: str
    description: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    ethical_concern: Optional[str] = None  # Planner-provided concern forces a one-action approval.
    dependencies: Set[str] = Field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING
    is_mutating: bool = False
    idempotency_key: Optional[str] = None
    requires_checkpoint: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None


class CycleError(Exception):
    """Raised when circular dependencies exist in the Task DAG."""
    pass


class TaskDAG:
    def __init__(self, task_id: str, goal: str) -> None:
        self.task_id = task_id
        self.goal = goal
        self.nodes: Dict[str, TaskNode] = {}

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.node_id] = node

    def validate_acyclic(self) -> List[str]:
        """
        Uses Kahn's Algorithm (DSA O(V + E)) to detect cycles
        and return a valid topological execution order.
        """
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        adj_list: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes}

        for node_id, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise ValueError(f"Dependency '{dep}' referenced by '{node_id}' does not exist.")
                adj_list[dep].append(node_id)
                in_degree[node_id] += 1

        queue = deque([node_id for node_id, deg in in_degree.items() if deg == 0])
        topological_order: List[str] = []

        while queue:
            curr = queue.popleft()
            topological_order.append(curr)

            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(topological_order) != len(self.nodes):
            unresolved = [k for k, v in in_degree.items() if v > 0]
            raise CycleError(f"Cycle detected in Task DAG involving nodes: {unresolved}")

        return topological_order

    def get_ready_nodes(self) -> List[TaskNode]:
        """Returns all nodes whose dependencies have successfully completed."""
        ready: List[TaskNode] = []
        for node in self.nodes.values():
            if node.status == TaskStatus.PENDING:
                deps_met = all(
                    self.nodes[dep].status == TaskStatus.COMPLETED for dep in node.dependencies
                )
                if deps_met:
                    node.status = TaskStatus.READY
                    ready.append(node)
        return ready

    def mark_completed(self, node_id: str, result: Any) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.COMPLETED
            self.nodes[node_id].result = result

    def mark_failed(self, node_id: str, error: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.FAILED
            self.nodes[node_id].error = error
            # Block dependent downstream nodes
            self._propagate_block(node_id)

    def _propagate_block(self, failed_node_id: str) -> None:
        for node in self.nodes.values():
            if failed_node_id in node.dependencies and node.status in (TaskStatus.PENDING, TaskStatus.READY):
                node.status = TaskStatus.BLOCKED
                self._propagate_block(node.node_id)

    def is_finished(self) -> bool:
        return all(
            node.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED)
            for node in self.nodes.values()
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "nodes": {k: v.model_dump(mode="json") for k, v in self.nodes.items()},
        }
