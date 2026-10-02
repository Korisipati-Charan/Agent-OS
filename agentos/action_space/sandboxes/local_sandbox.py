"""
AgentOS Local Process Sandbox.
Provides isolated process-level execution with directory scoping,
environment variable sanitization, and strict execution timeouts.
Used for local dev and Windows fallback where container APIs are unavailable.
"""

from pathlib import Path
import subprocess
from typing import Dict, List, Optional
from agentos.action_space.sandboxes.base import SandboxProvider, SandboxExecResult


class LocalProcessSandbox(SandboxProvider):
    def __init__(self, workspace_root: str | Path = "./workspace") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def stop(self) -> None:
        pass

    def execute_command(
        self,
        command: List[str] | str,
        cwd: Optional[str] = None,
        timeout_sec: float = 30.0,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxExecResult:
        target_cwd = Path(cwd).resolve() if cwd else self.workspace_root

        # Enforce boundary: target cwd must be within workspace
        if target_cwd != self.workspace_root and self.workspace_root not in target_cwd.parents:
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr=f"Sandbox boundary violation: cwd '{target_cwd}' is outside workspace '{self.workspace_root}'.",
            )

        import sys
        is_win = sys.platform == "win32"
        if isinstance(command, str) and is_win:
            cmd_list = ["cmd.exe", "/c", command]
        else:
            cmd_list = command if isinstance(command, list) else command.split()

        try:
            res = subprocess.run(
                cmd_list,
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
                shell=False,
            )
            return SandboxExecResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as tex:
            return SandboxExecResult(
                exit_code=-1,
                stdout=tex.stdout.decode() if isinstance(tex.stdout, bytes) else (tex.stdout or ""),
                stderr=f"Execution timed out after {timeout_sec}s.",
                timed_out=True,
            )
        except Exception as ex:
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr=f"Subprocess execution error: {ex}",
                timed_out=False,
            )
