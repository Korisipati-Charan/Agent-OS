"""
AgentOS Policy Engine.
Enforces Policy-as-Code from agentos.yaml.
Handles write scopes, capability tiers, and human-in-the-loop approval triggers.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel
from agentos.config import AgentOSConfig
from agentos.security.workspace_paths import resolve_in_allowed_workspaces


class PolicyDecision(BaseModel):
    allowed: bool
    tier: str  # read_only | workspace_write | consequential
    requires_approval: bool = False
    reason: str
    target_path_resolved: Optional[str] = None


class PolicyEngine:
    def __init__(self, config: AgentOSConfig) -> None:
        self.config = config
        self.allowed_workspaces = [
            Path(p).resolve() for p in config.write_scopes.allowed_workspaces
        ]
        self.protected_paths = [
            Path(p).resolve() for p in config.write_scopes.protected_paths
        ]

    def evaluate_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        actor: str = "agent",
    ) -> PolicyDecision:
        tier = self._resolve_tier(tool_name)

        # 1. Capability tier check: Consequential actions always trigger approval
        if tier == "consequential":
            return PolicyDecision(
                allowed=True,
                tier=tier,
                requires_approval=True,
                reason=f"Tool '{tool_name}' is classified as consequential and requires human approval.",
            )

        # 2. Workspace write scoping and path traversal protection
        if tier == "workspace_write":
            target_path_str = arguments.get("path") or arguments.get("filepath") or arguments.get("target_path")
            if target_path_str:
                resolved, scope_err = resolve_in_allowed_workspaces(
                    self.allowed_workspaces, target_path_str
                )
                if scope_err or resolved is None:
                    return PolicyDecision(
                        allowed=False,
                        tier=tier,
                        requires_approval=False,
                        reason=scope_err or "Invalid workspace path.",
                    )

                # Check protected paths
                for protected in self.protected_paths:
                    if resolved == protected or protected in resolved.parents:
                        return PolicyDecision(
                            allowed=False,
                            tier=tier,
                            requires_approval=False,
                            reason=f"Access to protected path '{resolved}' is forbidden.",
                            target_path_resolved=str(resolved),
                        )

                return PolicyDecision(
                    allowed=True,
                    tier=tier,
                    requires_approval=False,
                    reason=f"Write operation permitted in authorized workspace.",
                    target_path_resolved=str(resolved),
                )

        # 3. Read-only capability
        if tier == "read_only":
            return PolicyDecision(
                allowed=True,
                tier=tier,
                requires_approval=False,
                reason=f"Tool '{tool_name}' is read-only and within standard policy.",
            )

        # Default fallback: unknown tool requires verification
        return PolicyDecision(
            allowed=False,
            tier="unknown",
            requires_approval=True,
            reason=f"Tool '{tool_name}' is unregistered in capability tiers.",
        )

    def _resolve_tier(self, tool_name: str) -> str:
        if tool_name in self.config.capability_tiers.read_only:
            return "read_only"
        if tool_name in self.config.capability_tiers.workspace_write:
            return "workspace_write"
        if tool_name in self.config.capability_tiers.consequential:
            return "consequential"
        return "unknown"
