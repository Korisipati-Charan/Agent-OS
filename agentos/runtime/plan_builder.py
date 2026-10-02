"""
Deterministic plan templates for goals without an external planner model.
Keeps the CLI run path modular and testable.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List


def build_workspace_task_plan(goal: str, workspace: str = "./workspace") -> List[Dict[str, Any]]:
    """Build a two-step inspect-and-write plan. Tool paths are relative to ``workspace`` root."""
    goal_text = (goal or "Unnamed task").strip()
    if len(goal_text) > 400:
        goal_text = goal_text[:397] + "..."

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact = (
        f"AgentOS task record\n"
        f"Goal: {goal_text}\n"
        f"Completed: {stamp}\n"
    )

    return [
        {
            "id": "inspect_workspace",
            "description": "List workspace contents before writing results",
            "tool_name": "file_read",
            "arguments": {"path": "."},
            "dependencies": [],
        },
        {
            "id": "write_artifact",
            "description": "Write execution summary to the workspace",
            "tool_name": "file_write",
            "arguments": {"path": "output.txt", "content": artifact},
            "dependencies": ["inspect_workspace"],
        },
    ]
