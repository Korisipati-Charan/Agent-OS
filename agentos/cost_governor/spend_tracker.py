"""
AgentOS Spend Tracker.
Enforces per-task and per-day dollar and token quotas.
Provides auto-downgrade triggers and hard circuit-breaker halting.
"""

from datetime import datetime, timezone
from threading import Lock
from typing import Tuple
from agentos.config import AgentOSConfig, SpendLimitsConfig


class SpendTracker:
    def __init__(self, config: AgentOSConfig) -> None:
        self.config = config
        self.limits: SpendLimitsConfig = config.spend_limits
        self._lock = Lock()
        self.daily_tokens_used = 0
        self.daily_usd_used = 0.0
        self.task_tokens: dict[str, int] = {}
        self.task_usd: dict[str, float] = {}
        self._current_day = datetime.now(timezone.utc).date()

    def _rollover_day_if_needed(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._current_day:
            self._current_day = today
            self.daily_tokens_used = 0
            self.daily_usd_used = 0.0

    def record_usage(self, task_id: str, tokens: int, cost_usd: float) -> None:
        with self._lock:
            self._rollover_day_if_needed()
            self.daily_tokens_used += tokens
            self.daily_usd_used += cost_usd

            self.task_tokens[task_id] = self.task_tokens.get(task_id, 0) + tokens
            self.task_usd[task_id] = self.task_usd.get(task_id, 0.0) + cost_usd

    def can_spend(self, task_id: str = "default") -> Tuple[bool, str]:
        with self._lock:
            self._rollover_day_if_needed()

            # Daily caps
            if self.daily_usd_used >= self.limits.daily_usd:
                return False, f"Daily USD cap reached (${self.daily_usd_used:.2f} >= ${self.limits.daily_usd:.2f})"
            if self.daily_tokens_used >= self.limits.daily_tokens:
                return False, f"Daily token cap reached ({self.daily_tokens_used} >= {self.limits.daily_tokens})"

            # Per-task caps
            t_usd = self.task_usd.get(task_id, 0.0)
            if t_usd >= self.limits.per_task_usd:
                return False, f"Task USD cap reached (${t_usd:.2f} >= ${self.limits.per_task_usd:.2f})"

            t_tok = self.task_tokens.get(task_id, 0)
            if t_tok >= self.limits.per_task_tokens:
                return False, f"Task token cap reached ({t_tok} >= {self.limits.per_task_tokens})"

            return True, "Within budget limits."

    def should_downgrade_model(self, task_id: str = "default") -> bool:
        """Checks if budget threshold exceeded to trigger auto-downgrade to Tier 1 fast model."""
        with self._lock:
            threshold_ratio = self.limits.auto_downgrade_threshold_pct / 100.0
            t_usd = self.task_usd.get(task_id, 0.0)
            if t_usd >= (self.limits.per_task_usd * threshold_ratio):
                return True
            if self.daily_usd_used >= (self.limits.daily_usd * threshold_ratio):
                return True
            return False
