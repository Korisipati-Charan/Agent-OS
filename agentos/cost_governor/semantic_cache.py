"""
Semantic-ish cache for repeated planner/support queries (token-optimization step 2).
Uses normalized query hash; skips volatile task execution paths.
"""

import hashlib
import json
import re
from typing import Any, Dict, Optional

from agentos.memory.sqlite_store import SQLiteStore

_VOLATILE_MARKERS = ("now()", "today", "latest", "current time", "live")


class SemanticCache:
    def __init__(self, store: SQLiteStore, ttl_sec: int = 86400) -> None:
        self._store = store
        self._ttl_sec = ttl_sec

    @staticmethod
    def _normalize(query: str) -> str:
        collapsed = re.sub(r"\s+", " ", query.strip().lower())
        return collapsed

    def _key(self, query: str, task_type: str) -> str:
        payload = f"{task_type}|{self._normalize(query)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_eligible(self, query: str, task_type: str) -> bool:
        if task_type not in {"parsing", "summary", "extraction", "faq", "classification"}:
            return False
        q = query.lower()
        return not any(marker in q for marker in _VOLATILE_MARKERS)

    def lookup(self, query: str, task_type: str) -> Optional[Dict[str, Any]]:
        if not self.is_eligible(query, task_type):
            return None
        return self._store.get_semantic_cache(self._key(query, task_type))

    def store(self, query: str, task_type: str, response: Dict[str, Any]) -> None:
        if not self.is_eligible(query, task_type):
            return
        self._store.set_semantic_cache(
            cache_key=self._key(query, task_type),
            task_type=task_type,
            response_json=json.dumps(response),
            ttl_sec=self._ttl_sec,
        )
