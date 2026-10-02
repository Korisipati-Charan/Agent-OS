"""
AgentOS Prompt Cache Optimizer.
Structures prompt payloads to maximize KV prefix caching hits on LLM providers.
Places stable system prompts, tool schemas, and personas at the prefix,
with volatile conversation turns and runtime context strictly at the end.
Supports lazy tool loading for the current step.
"""

from typing import Any, Dict, List


class PromptCacheOptimizer:
    def __init__(self, system_persona: str) -> None:
        self.system_persona = system_persona

    def build_cached_prompt(
        self,
        active_tool_schemas: List[Dict[str, Any]],
        pinned_context: Dict[str, Any],
        recent_turns: List[Dict[str, Any]],
        current_step_instruction: str,
    ) -> List[Dict[str, Any]]:
        """
        Assembles messages maintaining stable prefix cacheability:
        1. [System Prefix - Stable]: Persona + Global Directives + Invariants
        2. [Tool Definitions - Stable / Step-Scoped]: Active tool JSON schemas
        3. [Pinned Entities - Semi-stable]: Durable project facts
        4. [Volatile Context]: Recent turns and step-specific prompt
        """
        messages: List[Dict[str, Any]] = []

        # 1. System Prefix (Static)
        system_content = (
            f"{self.system_persona}\n"
            "MANDATORY INVARIANTS:\n"
            "- All external actions require preflight authorization.\n"
            "- Postconditions are verified before state is committed.\n"
            "- Return JSON adhering strictly to the requested schema.\n"
        )

        if active_tool_schemas:
            tool_summary = "\n".join(
                f"- {tool.get('name')}: {tool.get('description', '')}"
                for tool in active_tool_schemas
            )
            system_content += f"\nAVAILABLE TOOL SCHEMAS (LAZY LOADED):\n{tool_summary}\n"

        messages.append({"role": "system", "content": system_content})

        # 2. Semi-stable Pinned Entities
        if pinned_context:
            pinned_str = "\n".join(f"{k}: {v}" for k, v in pinned_context.items())
            messages.append({"role": "system", "content": f"PINNED SYSTEM ENTITIES:\n{pinned_str}"})

        # 3. Volatile Turns
        for turn in recent_turns:
            messages.append({"role": turn["role"], "content": turn["content"]})

        # 4. Immediate Step Instruction (Most volatile)
        messages.append({"role": "user", "content": current_step_instruction})

        return messages
