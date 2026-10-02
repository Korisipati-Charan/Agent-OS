"""
AgentOS Built-in File Operations Tools.
Safe file reading and writing within authorized workspace roots.
"""

from pathlib import Path
from typing import Any, Dict
from agentos.action_space.base import BaseTool, ToolExecutionContext, ToolResult
from agentos.security.workspace_paths import resolve_within_workspace


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Safely reads a text file from the authorized workspace."
    is_mutating = False

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        rel_path = arguments.get("path") or arguments.get("filepath")
        if not rel_path:
            return ToolResult(success=False, output=None, error="Missing 'path' argument", exit_code=1)

        ws = Path(context.workspace_path)
        target, scope_err = resolve_within_workspace(ws, rel_path)
        if scope_err or target is None:
            return ToolResult(success=False, output=None, error=scope_err, exit_code=1)

        if not target.exists():
            if target == ws.resolve():
                return ToolResult(
                    success=True,
                    output={"files": [p.name for p in target.iterdir()]},
                    postcondition_state={"path_exists": True},
                )
            return ToolResult(success=False, output=None, error=f"File not found: {target}", exit_code=1)

        if target.is_dir():
            return ToolResult(
                success=True,
                output={"files": [p.name for p in target.iterdir()]},
                postcondition_state={"path_exists": True},
            )

        try:
            content = target.read_text(encoding="utf-8")
            return ToolResult(
                success=True,
                output=content,
                postcondition_state={"bytes_read": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e), exit_code=1)


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Safely writes or creates a file in the authorized workspace."
    is_mutating = True

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        rel_path = arguments.get("path") or arguments.get("filepath")
        content = arguments.get("content", "")

        if not rel_path:
            return ToolResult(success=False, output=None, error="Missing 'path' argument", exit_code=1)

        ws = Path(context.workspace_path)
        target, scope_err = resolve_within_workspace(ws, rel_path)
        if scope_err or target is None:
            return ToolResult(success=False, output=None, error=scope_err, exit_code=1)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output={"path": str(target), "written_bytes": len(content)},
                postcondition_state={"file_created": True, "size": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e), exit_code=1)
