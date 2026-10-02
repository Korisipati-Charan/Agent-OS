"""
Composition root for AgentOS subsystems (dependency injection without a framework).
"""

from dataclasses import dataclass

from agentos.action_space.file_tools import FileReadTool, FileWriteTool
from agentos.action_space.sandboxes.local_sandbox import LocalProcessSandbox
from agentos.cognitive.action_gate import ActionGate
from agentos.cognitive.planner import Planner
from agentos.cognitive.reflection import PostconditionGate
from agentos.config import AgentOSConfig
from agentos.core.engine import CognitiveEngine
from agentos.core.supervisor import SafetySupervisor
from agentos.cost_governor.crc_pipeline import CostGovernor
from agentos.cost_governor.spend_tracker import SpendTracker
from agentos.memory.sqlite_store import SQLiteStore
from agentos.policy.audit_log import AuditLogger
from agentos.policy.egress_proxy import EgressProxy
from agentos.policy.injection_defense import InjectionDefense
from agentos.policy.policy_engine import PolicyEngine


@dataclass(frozen=True)
class AgentRuntime:
    config: AgentOSConfig
    supervisor: SafetySupervisor
    engine: CognitiveEngine
    audit_logger: AuditLogger
    sqlite_store: SQLiteStore
    policy_engine: PolicyEngine
    injection_defense: InjectionDefense
    cost_governor: CostGovernor


def build_runtime(
    config_path: str = "agentos.yaml",
    workspace: str = "./workspace",
    audit_path: str = "data/audit.jsonl",
    db_path: str = "data/agentos.db",
) -> AgentRuntime:
    config = AgentOSConfig.from_yaml(config_path)
    audit_logger = AuditLogger(audit_path)
    sqlite_store = SQLiteStore(db_path)
    policy_engine = PolicyEngine(config)
    egress_proxy = EgressProxy(config)
    injection_defense = InjectionDefense()
    spend_tracker = SpendTracker(config)
    cost_governor = CostGovernor(config, spend_tracker, sqlite_store)

    supervisor = SafetySupervisor(config, audit_logger)
    planner = Planner(config)
    sandbox = LocalProcessSandbox(workspace)

    action_gate = ActionGate(
        config=config,
        policy_engine=policy_engine,
        egress_proxy=egress_proxy,
        spend_tracker=spend_tracker,
        sqlite_store=sqlite_store,
        audit_logger=audit_logger,
    )

    postcondition_gate = PostconditionGate(
        audit_logger=audit_logger,
        injection_defense=injection_defense,
    )

    engine = CognitiveEngine(
        config=config,
        supervisor=supervisor,
        planner=planner,
        action_gate=action_gate,
        postcondition_gate=postcondition_gate,
        sandbox=sandbox,
        sqlite_store=sqlite_store,
        audit_logger=audit_logger,
    )

    engine.register_tool(FileReadTool())
    engine.register_tool(FileWriteTool())

    return AgentRuntime(
        config=config,
        supervisor=supervisor,
        engine=engine,
        audit_logger=audit_logger,
        sqlite_store=sqlite_store,
        policy_engine=policy_engine,
        injection_defense=injection_defense,
        cost_governor=cost_governor,
    )
