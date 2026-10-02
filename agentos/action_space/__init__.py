"""
AgentOS Action Space.
Provides execution sandboxes, shell PTY supervision, browser automation, and diff-based code editing.
"""

from agentos.action_space.base import BaseTool, ToolExecutionContext, ToolResult
from agentos.action_space.sandboxes import (
    SandboxProvider,
    SandboxExecResult,
    LocalProcessSandbox,
    RootlessDockerSandbox,
)
from agentos.action_space.shell import PTYManager
from agentos.action_space.browser import BrowserTool
from agentos.action_space.code_editor import WorktreeCodeEditor, PatchRequest

__all__ = [
    "BaseTool",
    "ToolExecutionContext",
    "ToolResult",
    "SandboxProvider",
    "SandboxExecResult",
    "LocalProcessSandbox",
    "RootlessDockerSandbox",
    "PTYManager",
    "BrowserTool",
    "WorktreeCodeEditor",
    "PatchRequest",
]
