"""
AgentOS Sandbox Base Abstraction.
Defines contracts for rootless Docker, gVisor, and local process isolation.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pydantic import BaseModel


class SandboxExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxProvider(ABC):
    @abstractmethod
    def start(self) -> None:
        """Initialize the sandbox environment."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Tear down and clean up the sandbox."""
        pass

    @abstractmethod
    def execute_command(
        self,
        command: List[str] | str,
        cwd: str,
        timeout_sec: float = 30.0,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxExecResult:
        """Execute command within isolated boundary."""
        pass
