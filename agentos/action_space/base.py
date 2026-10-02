"""
AgentOS Action Space Base Types and Interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ToolExecutionContext(BaseModel):
    task_id: str
    node_id: str
    workspace_path: str
    env_vars: Dict[str, str] = Field(default_factory=dict)
    timeout_sec: float = 30.0


class ToolResult(BaseModel):
    success: bool
    output: Any
    error: Optional[str] = None
    exit_code: int = 0
    postcondition_state: Optional[Dict[str, Any]] = None


class BaseTool(ABC):
    name: str
    description: str
    is_mutating: bool = False

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        pass
