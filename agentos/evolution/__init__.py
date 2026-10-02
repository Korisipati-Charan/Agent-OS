"""
AgentOS Guarded Self-Evolution Package.
Quarantine circuit breaker, skill crystallization, and branch-isolated self-patching.
"""

from agentos.evolution.quarantine import ToolQuarantineManager
from agentos.evolution.self_patching import SelfPatchingGuard, SkillCrystallizer

__all__ = ["ToolQuarantineManager", "SelfPatchingGuard", "SkillCrystallizer"]
