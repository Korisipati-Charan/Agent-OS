"""
AgentOS Configuration Module.
Loads, validates, and provides access to agentos.yaml policies.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class SupervisorConfig(BaseModel):
    heartbeat_interval_sec: float = 2.0
    watchdog_timeout_sec: float = 15.0
    platform_mode: str = "auto"  # auto | linux_seccomp | windows_host_vm


class SandboxConfig(BaseModel):
    tier: str = "rootless_docker"  # rootless_docker | gvisor | local_process
    image: str = "python:3.11-slim"
    max_memory_mb: int = 2048
    max_cpu_cores: float = 2.0
    max_pids: int = 100
    read_only_root: bool = True
    workspace_mount: str = "/workspace"


class SpendLimitsConfig(BaseModel):
    per_task_usd: float = 2.50
    daily_usd: float = 25.00
    per_task_tokens: int = 150000
    daily_tokens: int = 1500000
    auto_downgrade_threshold_pct: float = 80.0
    halt_on_limit: bool = True


class ModelTierConfig(BaseModel):
    model: str
    api_base: Optional[str] = None
    fallback: Optional[str] = None
    purpose: str
    max_tokens: int = 2048
    temperature: float = 0.2


class ModelRoutingConfig(BaseModel):
    default_provider: str = "litellm"
    tiers: Dict[str, ModelTierConfig]


class EgressAllowlistConfig(BaseModel):
    enforce_proxy: bool = True
    allowed_domains: List[str] = Field(default_factory=list)
    blocked_ip_ranges: List[str] = Field(default_factory=list)


class WriteScopesConfig(BaseModel):
    default_mode: str = "read_only"
    allowed_workspaces: List[str] = Field(default_factory=list)
    protected_paths: List[str] = Field(default_factory=list)


class CapabilityTiersConfig(BaseModel):
    read_only: List[str] = Field(default_factory=list)
    workspace_write: List[str] = Field(default_factory=list)
    consequential: List[str] = Field(default_factory=list)


class ApprovalRulesConfig(BaseModel):
    require_human_approval_for: List[str] = Field(default_factory=list)
    approval_timeout_sec: int = 300


class IdempotencyConfig(BaseModel):
    require_idempotency_keys_for_mutations: bool = True
    checkpoint_before_retryable_action: bool = True
    deduplication_ttl_sec: int = 86400


class AgentOSConfig(BaseModel):
    version: str = "3.0.1"
    system: Dict[str, Any] = Field(default_factory=dict)
    quotas: Dict[str, SpendLimitsConfig] = Field(default_factory=dict)
    model_routing: ModelRoutingConfig
    egress_allowlist: EgressAllowlistConfig
    write_scopes: WriteScopesConfig
    capability_tiers: CapabilityTiersConfig
    approval_rules: ApprovalRulesConfig
    idempotency: IdempotencyConfig

    @classmethod
    def from_yaml(cls, path: str | Path = "agentos.yaml") -> "AgentOSConfig":
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    @property
    def spend_limits(self) -> SpendLimitsConfig:
        return self.quotas.get("spend_limits", SpendLimitsConfig())

    @property
    def supervisor(self) -> SupervisorConfig:
        sup_dict = self.system.get("supervisor", {})
        return SupervisorConfig.model_validate(sup_dict)

    @property
    def sandbox(self) -> SandboxConfig:
        sb_dict = self.system.get("sandbox", {})
        return SandboxConfig.model_validate(sb_dict)
