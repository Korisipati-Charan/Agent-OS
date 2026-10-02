"""
AgentOS Action Gate (Preflight Authorization).
Implements the Core Invariant: "Authorize before side effect".
Evaluates capabilities, write scopes, egress destinations, spend limits,
and idempotency keys before any action is executed.
"""

import hashlib
import json
from typing import Any, Dict, Optional
from pydantic import BaseModel
from agentos.config import AgentOSConfig
from agentos.policy.policy_engine import PolicyEngine, PolicyDecision
from agentos.policy.egress_proxy import EgressProxy
from agentos.policy.audit_log import AuditLogger
from agentos.memory.sqlite_store import SQLiteStore
from agentos.cost_governor.spend_tracker import SpendTracker
from agentos.policy.ethical_review import EthicalRiskAssessor


class PreflightAuthorization(BaseModel):
    authorized: bool
    requires_approval: bool = False
    approval_can_proceed: bool = False
    cached_result: Optional[Dict[str, Any]] = None
    reason: str
    idempotency_key: Optional[str] = None


class ActionGate:
    def __init__(
        self,
        config: AgentOSConfig,
        policy_engine: PolicyEngine,
        egress_proxy: EgressProxy,
        spend_tracker: SpendTracker,
        sqlite_store: SQLiteStore,
        audit_logger: AuditLogger,
    ) -> None:
        self.config = config
        self.policy_engine = policy_engine
        self.egress_proxy = egress_proxy
        self.spend_tracker = spend_tracker
        self.sqlite_store = sqlite_store
        self.audit_logger = audit_logger
        self.ethical_risk_assessor = EthicalRiskAssessor()

    def evaluate_preflight(
        self,
        task_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        actor: str = "agent",
        ethical_concern: Optional[str] = None,
        human_approved: bool = False,
        action_context: str = "",
    ) -> PreflightAuthorization:
        """
        Comprehensive preflight authorization check before any side-effecting action.
        """
        # 1. Spend Limit / Quota Check
        spend_ok, spend_reason = self.spend_tracker.can_spend()
        if not spend_ok:
            self.audit_logger.log(
                action_type="ACTION_GATE_REJECTED",
                actor=actor,
                payload={"tool": tool_name, "reason": spend_reason, "task_id": task_id},
            )
            return PreflightAuthorization(
                authorized=False,
                requires_approval=True,
                reason=f"Spend cap exceeded: {spend_reason}",
            )

        # 2. Policy Engine (Capability tiers, write scopes, protected paths)
        policy_dec: PolicyDecision = self.policy_engine.evaluate_tool_call(
            tool_name=tool_name, arguments=arguments, actor=actor
        )
        if not policy_dec.allowed:
            self.audit_logger.log(
                action_type="ACTION_GATE_REJECTED",
                actor=actor,
                payload={"tool": tool_name, "reason": policy_dec.reason, "task_id": task_id},
            )
            return PreflightAuthorization(
                authorized=False,
                requires_approval=policy_dec.requires_approval,
                reason=policy_dec.reason,
            )

        ethical_context = f"{action_context}\n{ethical_concern or ''}"
        blocked_concerns = self.ethical_risk_assessor.blocked_concerns(ethical_context)
        if blocked_concerns:
            reason = "Action blocked by hard safety policy: " + ", ".join(blocked_concerns)
            self.audit_logger.log(
                action_type="ACTION_GATE_ETHICAL_BLOCKED",
                actor=actor,
                payload={"tool": tool_name, "task_id": task_id, "concerns": blocked_concerns},
            )
            return PreflightAuthorization(authorized=False, reason=reason)

        # 3. Egress Destination Allowlist & SSRF Check (if tool makes outbound network calls)
        target_url = (
            arguments.get("url")
            or arguments.get("endpoint")
            or arguments.get("target_url")
        )
        if target_url:
            egress_ok, egress_msg = self.egress_proxy.validate_destination(target_url)
            if not egress_ok:
                self.audit_logger.log(
                    action_type="ACTION_GATE_EGRESS_BLOCKED",
                    actor=actor,
                    payload={"tool": tool_name, "url": target_url, "reason": egress_msg},
                )
                return PreflightAuthorization(
                    authorized=False,
                    requires_approval=False,
                    reason=egress_msg,
                )

        # 4. Idempotency Key & Deduplication Gate
        if idempotency_key:
            req_hash = hashlib.sha256(
                json.dumps(arguments, sort_keys=True).encode("utf-8")
            ).hexdigest()
            already_done, cached_data = self.sqlite_store.check_or_create_idempotency_key(
                idempotency_key=idempotency_key,
                action_name=tool_name,
                request_hash=req_hash,
            )
            if already_done and cached_data:
                self.audit_logger.log(
                    action_type="ACTION_GATE_IDEMPOTENCY_DEDUP",
                    actor=actor,
                    payload={"idempotency_key": idempotency_key, "tool": tool_name},
                )
                return PreflightAuthorization(
                    authorized=True,
                    cached_result=cached_data,
                    reason="Action already completed; returning cached idempotent result.",
                    idempotency_key=idempotency_key,
                )

        # 5. Check if action requires explicit human approval
        if policy_dec.requires_approval:
            approval_reason = f"Action '{tool_name}' requires human approval."
        else:
            approval_reason = ""

        detected_concerns = self.ethical_risk_assessor.assess(ethical_context)
        concerns = list(dict.fromkeys(
            ([ethical_concern.strip()] if ethical_concern and ethical_concern.strip() else [])
            + detected_concerns
        ))
        if concerns:
            ethical_reason = "Ethical review requested: " + ", ".join(concerns) + "."
            approval_reason = f"{approval_reason} {ethical_reason}".strip()

        if approval_reason and not human_approved:
            self.audit_logger.log(
                action_type="ACTION_GATE_APPROVAL_REQUIRED",
                actor=actor,
                payload={
                    "tool": tool_name,
                    "task_id": task_id,
                    "ethical_concerns": concerns,
                },
            )
            return PreflightAuthorization(
                authorized=False,
                requires_approval=True,
                approval_can_proceed=True,
                reason=approval_reason,
                idempotency_key=idempotency_key,
            )

        if human_approved:
            self.audit_logger.log(
                action_type="ACTION_GATE_APPROVAL_GRANTED",
                actor="human_user",
                payload={"tool": tool_name, "task_id": task_id},
            )

        # 6. Action Authorized
        self.audit_logger.log(
            action_type="ACTION_GATE_AUTHORIZED",
            actor=actor,
            payload={"tool": tool_name, "task_id": task_id, "tier": policy_dec.tier},
        )
        return PreflightAuthorization(
            authorized=True,
            requires_approval=False,
            reason="Preflight checks passed.",
            idempotency_key=idempotency_key,
        )
