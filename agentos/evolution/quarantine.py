"""
AgentOS Tool Quarantine & Hot-Patch Manager.
Tracks tool regression failures, isolates failing tool versions,
and activates fallback versions.
Guarantees that safety-critical controls are never silently bypassed.
Enforces task-boundary hot-patch activation (no in-place mutation of in-flight tasks).
"""

from typing import Dict, Optional
from pydantic import BaseModel
from agentos.policy.audit_log import AuditLogger


class ToolVersionMeta(BaseModel):
    tool_name: str
    version: str
    consecutive_failures: int = 0
    is_quarantined: bool = False
    is_safety_critical: bool = False
    fallback_version: Optional[str] = None


class ToolQuarantineManager:
    def __init__(self, audit_logger: AuditLogger, max_failure_threshold: int = 3) -> None:
        self.audit_logger = audit_logger
        self.max_failure_threshold = max_failure_threshold
        self.active_versions: Dict[str, str] = {}  # tool_name -> active_version
        self.registry: Dict[str, ToolVersionMeta] = {}
        self.staged_updates: Dict[str, str] = {}  # updates pending task boundary

    def register_tool_version(
        self,
        tool_name: str,
        version: str,
        is_safety_critical: bool = False,
        fallback_version: Optional[str] = None,
    ) -> None:
        key = f"{tool_name}:{version}"
        self.registry[key] = ToolVersionMeta(
            tool_name=tool_name,
            version=version,
            is_safety_critical=is_safety_critical,
            fallback_version=fallback_version,
        )
        if tool_name not in self.active_versions:
            self.active_versions[tool_name] = version

    def record_failure(self, tool_name: str) -> None:
        active_ver = self.active_versions.get(tool_name)
        if not active_ver:
            return

        key = f"{tool_name}:{active_ver}"
        meta = self.registry.get(key)
        if not meta:
            return

        meta.consecutive_failures += 1
        if meta.consecutive_failures >= self.max_failure_threshold:
            self._quarantine_tool(meta)

    def record_success(self, tool_name: str) -> None:
        active_ver = self.active_versions.get(tool_name)
        if active_ver:
            key = f"{tool_name}:{active_ver}"
            meta = self.registry.get(key)
            if meta:
                meta.consecutive_failures = 0

    def _quarantine_tool(self, meta: ToolVersionMeta) -> None:
        meta.is_quarantined = True
        self.audit_logger.log(
            action_type="TOOL_QUARANTINED",
            actor="quarantine_manager",
            payload={
                "tool_name": meta.tool_name,
                "version": meta.version,
                "failures": meta.consecutive_failures,
                "is_safety_critical": meta.is_safety_critical,
            },
        )

        if meta.fallback_version:
            # Fall back to known-good version
            self.active_versions[meta.tool_name] = meta.fallback_version
            self.audit_logger.log(
                action_type="TOOL_FALLBACK_ACTIVATED",
                actor="quarantine_manager",
                payload={"tool_name": meta.tool_name, "fallback_version": meta.fallback_version},
            )
        elif meta.is_safety_critical:
            # Fail closed: Do NOT silently disable safety control!
            raise RuntimeError(
                f"Safety-critical tool '{meta.tool_name}' failed and has no fallback version. Halting to prevent unsafe operation."
            )

    def stage_hot_patch(self, tool_name: str, new_version: str) -> None:
        """Stages a new tool version to be activated only at the next task boundary."""
        self.staged_updates[tool_name] = new_version

    def apply_staged_patches_at_task_boundary(self) -> List[str]:
        """Activates pending tool updates at a clean task boundary."""
        applied: List[str] = []
        for tool_name, new_ver in list(self.staged_updates.items()):
            self.active_versions[tool_name] = new_ver
            applied.append(f"{tool_name}->{new_ver}")
            del self.staged_updates[tool_name]
        return applied
