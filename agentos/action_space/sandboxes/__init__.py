"""
AgentOS Sandboxes.
"""

from agentos.action_space.sandboxes.base import SandboxProvider, SandboxExecResult
from agentos.action_space.sandboxes.local_sandbox import LocalProcessSandbox
from agentos.action_space.sandboxes.docker_sandbox import RootlessDockerSandbox

__all__ = ["SandboxProvider", "SandboxExecResult", "LocalProcessSandbox", "RootlessDockerSandbox"]
