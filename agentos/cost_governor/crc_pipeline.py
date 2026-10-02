"""
CRC pipeline facade: Cached, Routed, Compressed (token-optimization skill).
Single entry point for LLM-bound requests inside AgentOS.
"""

from typing import Any, Dict, List, Optional

from agentos.config import AgentOSConfig
from agentos.cost_governor.prompt_cache import PromptCacheOptimizer
from agentos.cost_governor.router import ModelRouter, RouteSelection
from agentos.cost_governor.semantic_cache import SemanticCache
from agentos.cost_governor.spend_tracker import SpendTracker
from agentos.memory.sqlite_store import SQLiteStore
from agentos.persona.loader import load_persona, load_user_notes


class CostGovernor:
    def __init__(
        self,
        config: AgentOSConfig,
        spend_tracker: SpendTracker,
        sqlite_store: SQLiteStore,
    ) -> None:
        persona = load_persona()
        user_notes = load_user_notes()
        if user_notes:
            persona = f"{persona}\n\nUSER CONTEXT:\n{user_notes}"

        self.router = ModelRouter(config, spend_tracker)
        self.prompt_cache = PromptCacheOptimizer(system_persona=persona)
        self.semantic_cache = SemanticCache(sqlite_store)

    def prepare_llm_call(
        self,
        task_type: str,
        instruction: str,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        pinned_context: Optional[Dict[str, Any]] = None,
        recent_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        cached = self.semantic_cache.lookup(instruction, task_type)
        if cached is not None:
            return {
                "cache_hit": True,
                "route": None,
                "messages": [],
                "cached_response": cached,
            }

        route: RouteSelection = self.router.select_route(task_type)
        messages = self.prompt_cache.build_cached_prompt(
            active_tool_schemas=tool_schemas or [],
            pinned_context=pinned_context or {},
            recent_turns=recent_turns or [],
            current_step_instruction=instruction,
        )
        return {
            "cache_hit": False,
            "route": route,
            "messages": messages,
            "cached_response": None,
        }

    def record_llm_response(self, task_type: str, instruction: str, response: Dict[str, Any]) -> None:
        self.semantic_cache.store(instruction, task_type, response)
