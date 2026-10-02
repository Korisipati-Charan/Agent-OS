"""
AgentOS Rootless Docker Sandbox.
Enforces container boundaries, resource quotas (RAM, CPU, PIDs),
read-only root filesystems, and isolated workspace mounts.
"""

from pathlib import Path
import subprocess
from typing import Dict, List, Optional
from agentos.config import SandboxConfig
from agentos.action_space.sandboxes.base import SandboxProvider, SandboxExecResult


class RootlessDockerSandbox(SandboxProvider):
    def __init__(self, config: SandboxConfig, host_workspace_dir: str = "./workspace") -> None:
        self.config = config
        self.host_workspace_dir = Path(host_workspace_dir).resolve()
        self.host_workspace_dir.mkdir(parents=True, exist_ok=True)
        self.container_id: Optional[str] = None

    def start(self) -> None:
        """Starts a persistent background runner container with resource limits."""
        cmd = [
            "docker", "run", "-d",
            "--rm",
            f"--memory={self.config.max_memory_mb}m",
            f"--cpus={self.config.max_cpu_cores}",
            f"--pids-limit={self.config.max_pids}",
            "-v", f"{self.host_workspace_dir}:{self.config.workspace_mount}:rw",
            "-w", self.config.workspace_mount,
        ]
        if self.config.read_only_root:
            cmd.extend(["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m"])

        cmd.extend([self.config.image, "sleep", "infinity"])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.container_id = res.stdout.strip()[:12]
        except Exception:
            # Fall back gracefully if Docker daemon is not active in the current host
            self.container_id = None

    def stop(self) -> None:
        if self.container_id:
            subprocess.run(["docker", "rm", "-f", self.container_id], capture_output=True)
            self.container_id = None

    def execute_command(
        self,
        command: List[str] | str,
        cwd: Optional[str] = None,
        timeout_sec: float = 30.0,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxExecResult:
        if not self.container_id:
            # If Docker daemon is unavailable, return error directing to local sandbox fallback
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr="Docker container is not running. Check docker service or use local fallback.",
            )

        cmd_str = command if isinstance(command, str) else " ".join(command)
        exec_cmd = ["docker", "exec"]
        if env:
            for k, v in env.items():
                exec_cmd.extend(["-e", f"{k}={v}"])

        exec_cmd.extend([self.container_id, "sh", "-c", cmd_str])

        try:
            res = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            return SandboxExecResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr=f"Docker command timed out after {timeout_sec}s.",
                timed_out=True,
            )
        except Exception as e:
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr=f"Docker exec error: {e}",
                timed_out=False,
            )
