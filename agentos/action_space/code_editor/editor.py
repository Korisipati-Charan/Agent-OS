"""
AgentOS Code Editor.
Applies diff-based patches in designated worktree environments.
Runs automated pre-commit tests and performs atomic rollback on failure.
"""

from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from agentos.action_space.base import BaseTool, ToolExecutionContext, ToolResult


class PatchRequest(BaseModel):
    filepath: str
    target_content: str
    replacement_content: str
    run_tests: bool = True
    test_command: Optional[str] = None


class WorktreeCodeEditor(BaseTool):
    name = "code_editor"
    description = "Diff-based patch tool with pre-commit testing and atomic rollback."
    is_mutating = True

    def __init__(self, worktree_dir: str = "./workspace") -> None:
        self.worktree_dir = Path(worktree_dir).resolve()
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        rel_path = arguments.get("filepath")
        target_str = arguments.get("target_content")
        replacement_str = arguments.get("replacement_content")
        test_cmd = arguments.get("test_command")

        if not rel_path or target_str is None or replacement_str is None:
            return ToolResult(
                success=False,
                output=None,
                error="Missing required fields: filepath, target_content, replacement_content",
                exit_code=1,
            )

        full_path = (self.worktree_dir / rel_path).resolve()
        if not full_path.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"File not found in worktree: {rel_path}",
                exit_code=1,
            )

        # 1. Create backup for atomic rollback
        backup_path = full_path.with_suffix(full_path.suffix + ".bak")
        shutil.copy2(full_path, backup_path)

        try:
            original_content = full_path.read_text(encoding="utf-8")
            if target_str not in original_content:
                backup_path.unlink(missing_ok=True)
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Target content not found in file: {rel_path}",
                    exit_code=1,
                )

            # 2. Apply patch
            patched_content = original_content.replace(target_str, replacement_str, 1)
            full_path.write_text(patched_content, encoding="utf-8")

            # 3. Pre-commit tests
            if test_cmd:
                test_proc = subprocess.run(
                    test_cmd,
                    shell=True,
                    cwd=str(self.worktree_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if test_proc.returncode != 0:
                    # Rollback on test failure
                    shutil.copy2(backup_path, full_path)
                    backup_path.unlink(missing_ok=True)
                    return ToolResult(
                        success=False,
                        output={"test_stdout": test_proc.stdout, "test_stderr": test_proc.stderr},
                        error=f"Pre-commit tests failed (exit code {test_proc.returncode}). Patch rolled back.",
                        exit_code=test_proc.returncode,
                    )

            # Cleanup backup on success
            backup_path.unlink(missing_ok=True)
            return ToolResult(
                success=True,
                output={"filepath": rel_path, "status": "applied_and_tested"},
                postcondition_state={"file_patched": rel_path, "tests_passed": bool(test_cmd)},
            )
        except Exception as ex:
            # Exception rollback
            if backup_path.exists():
                shutil.copy2(backup_path, full_path)
                backup_path.unlink(missing_ok=True)
            return ToolResult(
                success=False,
                output=None,
                error=f"Exception during patch execution: {ex}. Rolled back.",
                exit_code=1,
            )
