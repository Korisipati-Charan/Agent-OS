"""
AgentOS Model Router.
Implements provider-neutral routing via LiteLLM abstractions.
Routes cheap/local models for parsing/summaries and stronger models for planning/risk.
Preserves structured state across model swaps and fallback chains.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from agentos.config import AgentOSConfig, ModelTierConfig
from agentos.cost_governor.spend_tracker import SpendTracker


class RouteSelection(BaseModel):
    tier_name: str
    model: str
    fallback: Optional[str] = None
    temperature: float
    max_tokens: int


class ModelRouter:
    def __init__(self, config: AgentOSConfig, spend_tracker: SpendTracker) -> None:
        self.config = config
        self.spend_tracker = spend_tracker
        self.tiers: Dict[str, ModelTierConfig] = config.model_routing.tiers

    def select_route(self, task_type: str, task_id: str = "default") -> RouteSelection:
        """
        Routes model tier according to task type and spend limits.
        - 'parsing', 'summary', 'extraction', 'ast_check' -> Tier 1 (Fast / Cheap)
        - 'planning', 'high_risk', 'policy_eval', 'code_edit' -> Tier 2 (Reasoning)
        Auto-downgrades to Tier 1 if spend exceeds downgrade threshold.
        """
        fast_tasks = {"parsing", "summary", "extraction", "ast_check", "reflect_readonly"}

        # Check if spend cap warrants auto-downgrade
        forced_downgrade = self.spend_tracker.should_downgrade_model(task_id)

        if task_type in fast_tasks or forced_downgrade:
            tier_config = self.tiers.get("tier1_fast")
            if not tier_config:
                tier_config = ModelTierConfig(
                    model="gpt-4o-mini", purpose="fast fallback", max_tokens=1024, temperature=0.1
                )
            return RouteSelection(
                tier_name="tier1_fast",
                model=tier_config.model,
                fallback=tier_config.fallback,
                temperature=tier_config.temperature,
                max_tokens=tier_config.max_tokens,
            )

        # High-risk / Planning tasks
        tier_config = self.tiers.get("tier2_reasoning")
        if not tier_config:
            tier_config = ModelTierConfig(
                model="gpt-4o",
                fallback="claude-3-5-sonnet",
                purpose="reasoning fallback",
                max_tokens=4096,
                temperature=0.2,
            )
        return RouteSelection(
            tier_name="tier2_reasoning",
            model=tier_config.model,
            fallback=tier_config.fallback,
            temperature=tier_config.temperature,
            max_tokens=tier_config.max_tokens,
        )
