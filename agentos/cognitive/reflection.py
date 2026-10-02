"""
AgentOS Postcondition & Reflection Gate.
Implements the Core Invariant: "Verify after side effect".
Validates tool execution output and environmental postconditions
before dependent state is committed or user-facing claims are confirmed.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from agentos.policy.audit_log import AuditLogger
from agentos.policy.injection_defense import InjectionDefense


class VerificationResult(BaseModel):
    is_valid: bool
    sanitized_output: Any
    postcondition_verified: bool
    reasons: List[str] = []
    error_classification: Optional[str] = None  # TRANSIENT | LOGIC_ERROR | SECURITY_VIOLATION


class PostconditionGate:
    def __init__(self, audit_logger: AuditLogger, injection_defense: InjectionDefense) -> None:
        self.audit_logger = audit_logger
        self.injection_defense = injection_defense

    def verify_action(
        self,
        task_id: str,
        tool_name: str,
        is_mutating: bool,
        raw_output: Any,
        expected_postcondition: Optional[Dict[str, Any]] = None,
        observed_postcondition: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Validates output integrity and verifies environmental side-effect assertions.
        """
        reasons: List[str] = []

        # 1. Output Untrusted Data Sanitization & Injection Defense
        output_str = str(raw_output)
        sanitized_str, is_suspicious, warnings = self.injection_defense.sanitize_untrusted_data(output_str)

        if is_suspicious:
            reasons.extend(warnings)
            self.audit_logger.log(
                action_type="POSTCONDITION_SECURITY_WARNING",
                actor="postcondition_gate",
                payload={"tool": tool_name, "warnings": warnings, "task_id": task_id},
            )

        # 2. Mutating Action Postcondition Verification
        postcondition_verified = True
        if is_mutating and expected_postcondition:
            if not observed_postcondition:
                postcondition_verified = False
                reasons.append("Observed postcondition is empty despite mutating action.")
            else:
                for key, expected_val in expected_postcondition.items():
                    actual_val = observed_postcondition.get(key)
                    if actual_val != expected_val:
                        postcondition_verified = False
                        reasons.append(
                            f"Postcondition mismatch for '{key}': expected {expected_val}, got {actual_val}"
                        )

        # 3. Determine Overall Validity
        is_valid = postcondition_verified and (not is_suspicious or not is_mutating)

        error_classification = None
        if not is_valid:
            if is_suspicious:
                error_classification = "SECURITY_VIOLATION"
            elif not postcondition_verified:
                error_classification = "LOGIC_ERROR"

        self.audit_logger.log(
            action_type="POSTCONDITION_VERIFIED" if is_valid else "POSTCONDITION_FAILED",
            actor="postcondition_gate",
            payload={
                "tool": tool_name,
                "is_valid": is_valid,
                "postcondition_verified": postcondition_verified,
                "reasons": reasons,
                "task_id": task_id,
            },
        )

        return VerificationResult(
            is_valid=is_valid,
            sanitized_output=sanitized_str if isinstance(raw_output, str) else raw_output,
            postcondition_verified=postcondition_verified,
            reasons=reasons,
            error_classification=error_classification,
        )
