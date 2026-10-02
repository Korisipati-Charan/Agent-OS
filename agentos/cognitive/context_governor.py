"""
AgentOS Context Governor.
Responsible for entity pinning, progressive turn summarization,
full-text turn archival, and on-demand context retrieval.
"""

from typing import Any, Dict, List, Optional
from agentos.memory.working_memory import WorkingMemory


class ContextGovernor:
    def __init__(self, working_memory: WorkingMemory, summary_trigger_turns: int = 15) -> None:
        self.working_memory = working_memory
        self.summary_trigger_turns = summary_trigger_turns
        self.archived_turns: List[Dict[str, Any]] = []
        self.running_summary = ""

    def pin_key_entity(self, key: str, value: str) -> None:
        self.working_memory.pin_entity(key=key, content=value)

    def record_turn(self, role: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        self.working_memory.add_turn(role=role, content=content, tool_calls=tool_calls)
        self.archived_turns.append({"role": role, "content": content, "tool_calls": tool_calls or []})
        self._check_and_summarize()

    def _check_and_summarize(self) -> None:
        if len(self.working_memory.turns) <= self.summary_trigger_turns:
            return
        old_turns = self.working_memory.turns[:-5]
        # Chain-of-Draft style: ~5 words per turn fragment (token-optimization)
        summary_fragments = [self._draft_fragment(t) for t in old_turns]
        self.running_summary = (self.running_summary + " | " + " ".join(summary_fragments)).strip(" |")
        self.working_memory.turns = self.working_memory.turns[-5:]

    @staticmethod
    def _draft_fragment(turn: Dict[str, Any]) -> str:
        role = turn.get("role", "user")
        words = turn.get("content", "").split()
        snippet = " ".join(words[:5])
        return f"{role}:{snippet}"

    def retrieve_archived_context(self, query: str) -> List[Dict[str, Any]]:
        """Simple token-match retrieval from full historical archive."""
        q_lower = query.lower()
        return [
            turn for turn in self.archived_turns
            if q_lower in turn["content"].lower()
        ]
