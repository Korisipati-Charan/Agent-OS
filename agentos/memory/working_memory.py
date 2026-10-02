"""
AgentOS Working Memory.
Manages in-memory context window, entity pinning, and rolling conversation history.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PinnedEntity(BaseModel):
    key: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkingMemory:
    def __init__(self, max_turns: int = 20) -> None:
        self.max_turns = max_turns
        self.pinned_entities: Dict[str, PinnedEntity] = {}
        self.turns: List[Dict[str, Any]] = []

    def pin_entity(self, key: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Pins an entity so it is never pruned or lost during summarization."""
        self.pinned_entities[key] = PinnedEntity(
            key=key, content=content, metadata=metadata or {}
        )

    def unpin_entity(self, key: str) -> None:
        self.pinned_entities.pop(key, None)

    def add_turn(self, role: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        turn = {
            "role": role,
            "content": content,
            "tool_calls": tool_calls or [],
        }
        self.turns.append(turn)

    def get_context_snapshot(self) -> Dict[str, Any]:
        return {
            "pinned_entities": {k: v.model_dump() for k, v in self.pinned_entities.items()},
            "turns": self.turns[-self.max_turns:],
            "total_historical_turns": len(self.turns),
        }
