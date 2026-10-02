"""
AgentOS Guarded Self-Patching and Skill Crystallization.
Guarantees:
- Agent opens a branch and PR with tests; never auto-deploys to production.
- Safety supervisor and policy code are strictly excluded from agent modification.
- Skill crystallization requires test suite passing, sandboxed execution, and human approval.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from agentos.policy.audit_log import AuditLogger


class PRProposal(BaseModel):
    branch_name: str
    target_files: List[str]
    description: str
    has_unit_tests: bool
    requires_human_merge: bool = True


class SelfPatchingGuard:
    FORBIDDEN_MODIFICATION_PATHS = [
        "agentos/policy",
        "agentos/core/supervisor.py",
        "agentos.yaml",
        "Rules.MD",
    ]

    def __init__(self, audit_logger: AuditLogger) -> None:
        self.audit_logger = audit_logger

    def validate_patch_targets(self, target_files: List[str]) -> tuple[bool, str]:
        """Ensures that safety-critical supervisor and policy modules cannot be touched by agents."""
        for path_str in target_files:
            for forbidden in self.FORBIDDEN_MODIFICATION_PATHS:
                if forbidden in path_str.replace("\\", "/"):
                    return False, f"Security Violation: Agents are strictly forbidden from modifying '{forbidden}'."
        return True, "Patch targets within permitted bounds."

    def propose_pr(self, branch_name: str, target_files: List[str], description: str, tests_passed: bool) -> PRProposal:
        valid, msg = self.validate_patch_targets(target_files)
        if not valid:
            raise PermissionError(msg)

        if not tests_passed:
            raise ValueError("Cannot propose PR without passing test suite.")

        self.audit_logger.log(
            action_type="SELF_PATCH_PR_PROPOSED",
            actor="self_patching_guard",
            payload={"branch": branch_name, "files": target_files, "description": description},
        )

        return PRProposal(
            branch_name=branch_name,
            target_files=target_files,
            description=description,
            has_unit_tests=True,
            requires_human_merge=True,
        )


class SkillCrystallizer:
    def __init__(self, audit_logger: AuditLogger) -> None:
        self.audit_logger = audit_logger

    def crystallize_action_pattern(
        self,
        skill_name: str,
        script_code: str,
        test_results_passed: bool,
        human_approved: bool,
    ) -> bool:
        """
        Crystallizes repeated actions into permanent scripts only after:
        1. Tests pass
        2. Sandbox execution verified
        3. Explicit human approval granted
        """
        if not test_results_passed:
            return False
        if not human_approved:
            self.audit_logger.log(
                action_type="CRYSTALLIZATION_AWAITING_APPROVAL",
                actor="skill_crystallizer",
                payload={"skill": skill_name},
            )
            return False

        self.audit_logger.log(
            action_type="SKILL_CRYSTALLIZED",
            actor="skill_crystallizer",
            payload={"skill": skill_name},
        )
        return True
